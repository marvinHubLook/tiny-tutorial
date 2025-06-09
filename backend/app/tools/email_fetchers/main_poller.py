import json
from typing import Dict, Any, Type, Optional, List, Iterator
from datetime import datetime
import queue
from dataclasses import dataclass
import threading
from threading import Event, Thread

from app.tools.email_fetchers.base_fetcher import AbstractEmailFetcher, EmailMessage
from app.tools.email_fetchers.imap_fetcher import ImapEmailFetcher
from app.tools.email_fetchers.gmail_api_fetcher import GmailAPIFetcher
from app.tools.email_fetchers.outlook_graph_fetcher import OutlookGraphAPIFetcher
from app.tools.email_fetchers.outlook_imap_fetcher import OutlookImapEmailFetcher
from app.utils.logger import getLogger

logger = getLogger(__name__)

FETCHER_MAPPING: Dict[str, Type[AbstractEmailFetcher]] = {
    "imap": ImapEmailFetcher,
    "gmail_api": GmailAPIFetcher,
    "outlook_graph": OutlookGraphAPIFetcher,
    "outlook_imap": OutlookImapEmailFetcher
}


@dataclass
class PollingConfig:
    """轮询配置"""
    max_poll_count: int = 10  # 最大轮询次数
    poll_interval: int = 60  # 轮询间隔（秒）
    max_emails_per_poll: int = 100  # 每次轮询最大邮件数


class EmailMessageQueue:
    """简化的邮件消息队列"""

    def __init__(self):
        self._queue = queue.Queue()
        self._stats = {
            'total_messages': 0,
            'last_message_time': None
        }

    def put_message(self, message: EmailMessage) -> None:
        """添加消息到队列"""
        self._queue.put(message)
        self._stats['total_messages'] += 1
        self._stats['last_message_time'] = datetime.now()

    def get_message(self) -> Optional[EmailMessage]:
        """获取消息"""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def clear(self) -> None:
        """清空队列"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self._stats.copy()
        if stats['last_message_time']:
            stats['last_message_time'] = stats['last_message_time'].isoformat()
        return stats


class EmailPoller:
    """简化的邮件轮询器，一次处理一个账号"""

    def __init__(self, config_path: str = "config.json", polling_config: Optional[PollingConfig] = None):
        """初始化邮件轮询器"""
        self.config_path = config_path
        self.accounts_config = self._load_config()
        self.message_queue = EmailMessageQueue()
        self.current_account_index = -1
        self.enabled_accounts = self._get_enabled_accounts()

        # 邮件去重集合
        self._processed_email_ids = set()
        # 轮询配置
        self.polling_config = polling_config or PollingConfig()

        # 线程控制
        self._worker_thread: Optional[Thread] = None
        self._stop_event = Event()
        self._processing_event = Event()
        self._is_processing = False
        self._worker_lock = threading.Lock()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Configuration loaded successfully from {self.config_path}")
            return config
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self.config_path}")
            raise
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {self.config_path}")
            raise

    def _get_enabled_accounts(self) -> List[Dict[str, Any]]:
        """获取已启用的账号列表"""
        return [
            acc for acc in self.accounts_config.get("accounts", [])
            if acc.get("enabled", False)
        ]

    def process_email(self, email: EmailMessage, account_id: str):
        """处理单个邮件"""
        logger.info(
            f"[{account_id} ({email.account_email})] Received Email: "
            f"ID='{email.id}', From='{email.sender}', Subject='{email.subject}'"
        )
        if email.attachments:
            logger.info(f"  Attachments: {[att.filename for att in email.attachments]}")
        self.message_queue.put_message(email)

    def _poll_account(self, account_config: Dict[str, Any]) -> None:
        """轮询单个账号的邮件"""
        account_id = account_config.get("id", "UnknownAccount")
        fetcher_type_name = account_config.get("type")
        fetcher_config = account_config.get("config", {})
        fetch_criteria = account_config.get("fetch_criteria", {})
        mark_as_read = fetch_criteria.get("mark_as_read_after_fetch", False)

        # 获取账号特定的轮询配置，如果没有则使用默认配置
        poll_config = account_config.get("polling_config", {})
        max_poll_count = poll_config.get("max_poll_count", self.polling_config.max_poll_count)
        poll_interval = poll_config.get("poll_interval", self.polling_config.poll_interval)
        max_emails = poll_config.get("max_emails_per_poll", self.polling_config.max_emails_per_poll)

        if "email_address" not in fetcher_config and "email_address" in account_config:
            fetcher_config["email_address"] = account_config["email_address"]

        FetcherClass = FETCHER_MAPPING.get(fetcher_type_name)
        if not FetcherClass:
            logger.error(f"[{account_id}] Unknown fetcher type: {fetcher_type_name}. Skipping.")
            return

        poll_count = 0
        while not self._stop_event.is_set() and poll_count < max_poll_count:
            try:
                logger.info(f"[{account_id}] Attempting to fetch emails (attempt {poll_count + 1}/{max_poll_count})...")

                with FetcherClass(fetcher_config) as fetcher:
                    # 更新获取条件，限制邮件数量
                    fetch_criteria["max_emails"] = max_emails
                    new_emails = fetcher.fetch_emails(criteria=fetch_criteria)

                    if new_emails:
                        logger.info(f"[{account_id}] Fetched {len(new_emails)} new email(s).")
                        email_ids_to_mark_read = []
                        processed_count = 0

                        for email in new_emails:
                            # 邮件去重处理
                            if email.id in self._processed_email_ids:
                                logger.debug(f"[{account_id}] Skipping duplicate email: {email.id}")
                                continue

                            try:
                                self.process_email(email, account_id)
                                self._processed_email_ids.add(email.id)
                                processed_count += 1

                                if mark_as_read:
                                    email_ids_to_mark_read.append(email.id)
                            except Exception as e_proc:
                                logger.error(f"[{account_id}] Error processing email ID {email.id}: {e_proc}")

                        if mark_as_read and email_ids_to_mark_read:
                            try:
                                fetcher.mark_as_read(email_ids_to_mark_read)
                                logger.info(f"[{account_id}] Marked {len(email_ids_to_mark_read)} emails as read.")
                            except Exception as e_mark:
                                logger.error(f"[{account_id}] Error marking emails as read: {e_mark}")

                        logger.info(f"[{account_id}] Processed {processed_count} new emails.")
                    else:
                        logger.info(f"[{account_id}] No new emails found.")

            except Exception as e:
                logger.error(f"[{account_id}] Error polling account: {e}")

            poll_count += 1
            if poll_count < max_poll_count:
                logger.debug(f"[{account_id}] Waiting {poll_interval} seconds before next poll...")
                # 使用 stop_event 作为等待条件，这样可以及时响应停止信号
                if self._stop_event.wait(timeout=poll_interval):
                    break

    def _worker_run(self):
        """工作线程运行函数"""
        while not self._stop_event.is_set():
            # 等待处理信号
            self._processing_event.wait()
            if self._stop_event.is_set():
                break

            with self._worker_lock:
                if self.current_account_index >= 0 and self.current_account_index < len(self.enabled_accounts):
                    current_account = self.enabled_accounts[self.current_account_index]
                    logger.info(f"Processing account: {current_account.get('email_address', 'Unknown')}")
                    self._is_processing = True
                    try:
                        self._poll_account(current_account)
                    finally:
                        self._is_processing = False
                        self._processing_event.clear()
                else:
                    logger.warning("No valid account to process, resetting worker state.")
                    self._is_processing = False
                    self._processing_event.clear()

    def start(self,auto_flag:bool = True):
        """启动工作线程"""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = Thread(target=self._worker_run, daemon=True)
            self._worker_thread.start()
            logger.info("Email poller worker thread started")
            if auto_flag:
                self.next()

    def stop(self):
        """停止工作线程"""
        if self._worker_thread and self._worker_thread.is_alive():
            self._stop_event.set()
            self._processing_event.set()  # 唤醒工作线程
            self._worker_thread.join(timeout=5)
            logger.info("Email poller worker thread stopped")

    def next(self) -> bool:
        """处理下一个账号，返回是否还有更多账号"""
        # 清空当前环境
        self.message_queue.clear()

        with self._worker_lock:
            self.current_account_index += 1
            if self.current_account_index >= len(self.enabled_accounts):
                self.current_account_index = -1  # 重置索引
                return False

            # 触发工作线程处理
            self._processing_event.set()
            return True

    def is_processing(self) -> bool:
        """检查是否正在处理账号"""
        return self._is_processing


    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """等待当前账号处理完成"""
        start_time = datetime.now()
        while self.is_processing():
            if timeout is not None:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed >= timeout:
                    logger.info(f"wait time exceeded {datetime.now() - start_time} seconds, stopping wait")
                    return False
            threading.Event().wait(0.5)  # 短暂休眠避免CPU过度使用
        return True

    def reset(self) -> None:
        """重置轮询器状态"""
        with self._worker_lock:
            self.current_account_index = -1
            self.message_queue.clear()
            self.enabled_accounts = self._get_enabled_accounts()
            self._processing_event.clear()
            self._processed_email_ids.clear()  # 清空去重集合

    def get_message(self) -> Optional[EmailMessage]:
        """从队列获取单个消息"""
        return self.message_queue.get_message()

    def get_last_message(self) -> Optional[EmailMessage]:
        """获取队列中的最后一条消息"""
        last_message = None
        while not self.message_queue._queue.empty():
            last_message = self.message_queue.get_message()
        return last_message

    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        return self.message_queue.get_stats()

    def get_current_account(self) -> Optional[Dict[str, Any]]:
        """获取当前处理的账号配置"""
        if self.current_account_index >= 0 and self.current_account_index < len(self.enabled_accounts):
            return self.enabled_accounts[self.current_account_index]
        return None


def test_main():
    import os,time
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, "config/email_config.json")
    print(f"Using configuration file: {config_path}")
    poller = EmailPoller(config_path, PollingConfig(
        max_poll_count= 2,
        poll_interval= 30,  # seconds
        max_emails_per_poll= 2,  # seconds
    ))
    poller.start()
    time.sleep(3)
    try:
        count_flag =True
        while count_flag:
            while not poller.wait_for_completion(10):
                email:EmailMessage = poller.get_message()
                while email is not None:
                    email = poller.get_message()
                logger.info("Polling completed, waiting for next poll...")
            count_flag = poller.next()
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        logger.exception(e)
    finally:
        poller.stop()
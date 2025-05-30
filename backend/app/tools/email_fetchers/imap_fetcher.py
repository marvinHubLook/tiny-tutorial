from .base_fetcher import AbstractEmailFetcher, EmailMessage, Attachment
from app.utils.logger import getLogger
from typing import Dict, Any
from email.header import decode_header
from email.utils import parsedate_to_datetime
import imaplib
import email
from typing import List, Optional
from datetime import datetime

# 获取当前模块的logger
logger = getLogger(__name__)


class ImapEmailFetcher(AbstractEmailFetcher):
    """IMAP邮件获取器，用于从IMAP服务器获取邮件"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化IMAP邮件获取器

        Args:
            config: 配置字典，包含以下字段：
                - server: IMAP服务器地址
                - port: 服务器端口（默认993）
                - username: 用户名
                - password: 密码
                - mailbox: 邮箱文件夹（默认INBOX）
                - use_ssl: 是否使用SSL连接（默认True）
        """
        super().__init__(config)
        self.server = config.get("server")
        self.port = config.get("port", 993)
        self.username = config.get("username")
        self.password = config.get("password")
        self.mailbox = config.get("mailbox", "INBOX")
        self.use_ssl = config.get("use_ssl", True)
        self.imap = None

    def connect(self):
        try:
            if self.use_ssl:
                self.imap = imaplib.IMAP4_SSL(self.server, self.port)
            else:
                self.imap = imaplib.IMAP4(self.server, self.port)
            self.imap.login(self.username, self.password)
            logger.info(f"IMAP: Successfully connected to {self.server} for user {self.username}")
        except Exception as e:
            logger.error(f"Failed to connect to {self.server}:{self.port}")
            raise e

    def _decode_header(self, header: str) -> str:
        if not header:
            return ""
        decoded_parts = []
        for part, charset in decode_header(header):
            if isinstance(part, bytes):
                try:
                    decoded_parts.append(part.decode(charset or 'utf-8', errors='replace'))
                except LookupError:  # Unknown encoding
                    decoded_parts.append(part.decode('utf-8', errors='replace'))  # Fallback
            else:
                decoded_parts.append(part)
        return "".join(decoded_parts)

    def _parse_email(self, msg_data, email_id_bytes: bytes) -> Optional[EmailMessage]:
        """
        解析原始邮件数据为EmailMessage对象

        处理以下内容：
        - 主题、发件人、收件人
        - 纯文本和HTML正文
        - 附件
        - 日期时间
        - 消息ID等元数据
        """
        if not msg_data or not msg_data[0]:
            return None

        raw_email_bytes = msg_data[0][1]
        msg = email.message_from_bytes(raw_email_bytes)

        subject = self._decode_header(msg.get("Subject"))
        sender = self._decode_header(msg.get("From"))
        to_recipients = [self._decode_header(r) for r in (msg.get_all("To") or [])]
        cc_recipients = [self._decode_header(r) for r in (msg.get_all("Cc") or [])]
        message_id_header = msg.get("Message-ID")

        body_text = None
        body_html = None
        attachments_list = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if "attachment" not in content_disposition:
                    if content_type == "text/plain" and body_text is None:
                        try:
                            body_text = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8',
                                                                             errors='replace')
                        except Exception:
                            body_text = part.get_payload(decode=True).decode('latin-1', errors='replace')  # Fallback
                    elif content_type == "text/html" and body_html is None:
                        try:
                            body_html = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8',
                                                                             errors='replace')
                        except Exception:
                            body_html = part.get_payload(decode=True).decode('latin-1', errors='replace')  # Fallback
                else:  # Attachment
                    filename = part.get_filename()
                    if filename:
                        filename = self._decode_header(filename)
                        attachments_list.append(
                            Attachment(
                                filename=filename,
                                content_type=content_type,
                                content=part.get_payload(decode=True)
                            )
                        )
        else:  # Not multipart
            content_type = msg.get_content_type()
            if content_type == "text/plain":
                try:
                    body_text = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8',
                                                                    errors='replace')
                except Exception:
                    body_text = msg.get_payload(decode=True).decode('latin-1', errors='replace')  # Fallback
            elif content_type == "text/html":
                try:
                    body_html = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8',
                                                                    errors='replace')
                except Exception:
                    body_html = msg.get_payload(decode=True).decode('latin-1', errors='replace')  # Fallback

        received_date_str = msg.get("Date")
        received_dt = None
        if received_date_str:
            try:
                received_dt = parsedate_to_datetime(received_date_str)
            except Exception as e:
                logger.warning(f"Could not parse date string '{received_date_str}': {e}")

        email_id_str = email_id_bytes.decode('utf-8')  # IMAP IDs are typically numbers as strings

        return EmailMessage(
            id=email_id_str,
            message_id_header=message_id_header,
            subject=subject,
            sender=sender,
            recipients_to=to_recipients,
            recipients_cc=cc_recipients,
            body_text=body_text,
            body_html=body_html,
            received_date=received_dt,
            attachments=attachments_list,
            raw=msg,  # Store the raw email.message.Message object
            provider_type="imap",
            account_email=self.account_email
        )

    def fetch_emails(self, criteria: Optional[Dict[str, Any]] = None) -> List[EmailMessage]:
        """
        根据指定条件获取邮件

        Args:
            criteria: 搜索条件字典，可包含：
                - search_string: IMAP搜索字符串
                - since_date: 起始日期
                - mark_as_read_after_fetch: 是否标记为已读

        Returns:
            EmailMessage对象列表
        """
        if not self.imap:
            raise ConnectionError("Not connected to IMAP server.")

        fetched_emails: List[EmailMessage] = []
        try:
            status, _ = self.imap.select(self.mailbox, readonly=(
                        criteria is None or not criteria.get('mark_as_read_after_fetch',
                                                             False)))  # readonly if not marking as read here
            if status != 'OK':
                logger.error(f"IMAP: Failed to select mailbox {self.mailbox}")
                return []

            search_criteria = "UNSEEN"  # Default
            if criteria and "search_string" in criteria:
                search_criteria = criteria["search_string"]
            elif criteria and "since_date" in criteria:  # Example: datetime object
                try:
                    since_date = datetime.strptime(criteria["since_date"], "%Y-%m-%d")
                except ValueError:
                    raise ValueError("日期格式应为 'YYYY-MM-DD'")
                date_str = since_date.strftime("%d-%b-%Y")
                search_criteria = f'(SINCE {date_str})'

            logger.debug(f"IMAP: Searching with criteria: {search_criteria}")
            typ, data = self.imap.search(None, search_criteria)
            if typ != 'OK':
                logger.error(f"IMAP: Error searching emails: {data}")
                return []

            email_ids_to_fetch = data[0].split()
            if not email_ids_to_fetch:
                logger.info(f"IMAP: No emails found for criteria '{search_criteria}' in {self.mailbox}")
                return []

            logger.info(f"IMAP: Found {len(email_ids_to_fetch)} emails matching criteria.")

            for email_id_bytes in email_ids_to_fetch:
                # Fetch the email by ID
                # RFC822 gets the full message (headers + body)
                typ, msg_data = self.imap.fetch(email_id_bytes, '(RFC822)')
                if typ == 'OK':
                    parsed_email = self._parse_email(msg_data, email_id_bytes)
                    if parsed_email:
                        fetched_emails.append(parsed_email)
                else:
                    logger.error(f"IMAP: Error fetching email ID {email_id_bytes.decode()}: {msg_data}")

            return fetched_emails

        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP: Error during email fetching for {self.username}: {e}")
            # Attempt to reconnect or raise
            self.disconnect()  # Close broken connection
            raise
        except Exception as e:
            logger.error(f"IMAP: Unexpected error during email fetching for {self.username}: {e}")
            raise

    def mark_as_read(self, email_ids: List[str]) -> None:
        """
        将指定邮件标记为已读

        Args:
            email_ids: 要标记的邮件ID列表
        """
        if not self.imap:
            raise ConnectionError("Not connected to IMAP server.")
        if not email_ids:
            return

        # IMAP IDs are typically numbers, join them as a comma-separated string
        ids_str = ",".join(email_ids)
        try:
            # Select mailbox in read-write mode if not already
            status, _ = self.imap.select(self.mailbox, readonly=False)
            if status != 'OK':
                logger.error(f"IMAP: Failed to select mailbox {self.mailbox} for marking as read.")
                return

            logger.info(f"IMAP: Marking emails as read: {ids_str}")
            self.imap.store(ids_str.encode(), '+FLAGS', '\\Seen')
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP: Error marking emails as read: {e}")

    def disconnect(self) -> None:
        """
        断开与IMAP服务器的连接
        - 关闭当前选择的邮箱
        - 登出服务器
        - 清理连接状态
        """
        if self.imap:
            try:
                self.imap.close()
                self.imap.logout()
                logger.info(f"IMAP: Successfully disconnected from {self.server} for user {self.username}")
            except imaplib.IMAP4.error as e:
                logger.warning(f"IMAP: Error during disconnect for {self.username}: {e}")
            finally:
                self.imap = None
import requests
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
import imaplib
from email.utils import parsedate_to_datetime
from email.header import decode_header
import os
import json

from app.tools.email_fetchers.base_fetcher import AbstractEmailFetcher, EmailMessage, Attachment
from app.utils.logger import getLogger
import email

logger = getLogger(__name__)


class OutlookImapEmailFetcher(AbstractEmailFetcher):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.username = config.get("username")
        self.password = config.get("password", "")
        self.client_id = config.get("client_id")
        self.refresh_token = config.get("refresh_token")
        self.mailbox = config.get("mailbox", "INBOX")  # #选择收件箱  Junk: 选择垃圾箱
        # 代理设置
        self.proxy = config.get("proxy")
        # current path
        current_path = os.path.dirname(os.path.abspath(__file__))
        self.token_cache_file = config.get("token_cache_file", os.path.join(current_path, "outlook_token_cache.json"))

        self.access_token = None
        self.imap_client = None
        self.proxies = None
        if self.proxy:
            self.proxies = {
                "http": self.proxy,
                "https": self.proxy
            }
            logger.info(f"已配置代理: {self.proxy}")

        self._load_token_from_cache()

    def _load_token_from_cache(self):
        """
        从缓存文件加载令牌
        """
        if not self.token_cache_file:
            return

        try:
            if os.path.exists(self.token_cache_file):
                with open(self.token_cache_file, 'r') as f:
                    token_data = json.load(f)

                # 检查是否有相关的令牌缓存
                if self.username in token_data:
                    user_tokens = token_data[self.username]
                    # 检查令牌是否过期
                    current_time = datetime.now(timezone.utc).timestamp()
                    if user_tokens.get('expires_at', 0) < current_time:
                        logger.warning(f"令牌已过期，用户: {self.username}")
                        self.access_token = None
                    else:
                        self.access_token = user_tokens.get('access_token')
                        self.refresh_token = user_tokens.get('refresh_token')
                        self.token_expires_at = user_tokens.get('expires_at', 0)

                    logger.info(f"从缓存文件加载了令牌，用户: {self.username}")
        except Exception as e:
            logger.warning(f"从缓存加载令牌失败: {str(e)}")

    def _save_token_to_cache(self):
        """
        将令牌保存到缓存文件
        """
        if not self.token_cache_file or not self.refresh_token:
            return

        try:
            # 读取现有缓存
            token_data = {}
            if os.path.exists(self.token_cache_file):
                with open(self.token_cache_file, 'r') as f:
                    token_data = json.load(f)

            # 更新当前用户的令牌
            token_data[self.username] = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'expires_at': self.token_expires_at
            }

            # 保存回文件
            with open(self.token_cache_file, 'w') as f:
                json.dump(token_data, f)

            logger.info(f"令牌已保存到缓存文件，用户: {self.username}")
        except Exception as e:
            logger.warning(f"保存令牌到缓存失败: {str(e)}")

    def _get_access_token(self):
        if not self.access_token:
            data = {
                'client_id': self.client_id,
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token
            }
            token_url = 'https://login.microsoftonline.com/consumers/oauth2/v2.0/token'
            response = requests.post(token_url, data=data, proxies=self.proxies)
            response.raise_for_status()
            self.access_token = response.json().get('access_token')
            self.token_expires_at = datetime.now(timezone.utc).timestamp() + response.json().get('expires_in', 3600)
            self._save_token_to_cache()


    def generate_auth_string(self, user, access_token):
        return f"user={user}\1auth=Bearer {access_token}\1\1".encode('utf-8')

    def connect(self) -> None:
        #     获取访问令牌
        if not self.access_token:
            logger.info("Fetching access token...")
            self._get_access_token()

        if not self.access_token:
            raise ValueError("Access token could not be retrieved.")
        try:
            imap_host = 'outlook.live.com'
            auth_string = self.generate_auth_string(self.username, self.access_token)
            self.imap_client = imaplib.IMAP4_SSL(imap_host)
            self.imap_client.authenticate('XOAUTH2', lambda x: auth_string);
            logger.info(f"IMAP connection established for {self.username} at {imap_host}")
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP authentication failed: {e}")
            raise ValueError("IMAP authentication failed. Check your credentials and access token.")
        except Exception as e:
            logger.error(f"An error occurred while connecting to IMAP: {e}")
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
        if not self.imap_client:
            self.connect()
        if not self.imap_client:
            raise ValueError("IMAP client is not connected.")

        fetched_emails: List[EmailMessage] = []
        try:
            status, _ = self.imap_client.select(self.mailbox, readonly=(
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
            typ, data = self.imap_client.search(None, search_criteria)
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
                typ, msg_data = self.imap_client.fetch(email_id_bytes, '(RFC822)')
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
        if not self.imap_client:
            self.connect()
        if not self.imap_client:
            raise ValueError("IMAP client is not connected.")

        try:
            self.imap_client.select(self.mailbox, readonly=False)  # Set to writable
            for email_id in email_ids:
                logger.info(f"IMAP: Marking email ID {email_id} as read.")
                self.imap_client.store(email_id, '+FLAGS', '\\Seen')
            logger.info(f"IMAP: Successfully marked {len(email_ids)} emails as read.")
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP: Error marking emails as read: {e}")
            raise
        except Exception as e:
            logger.error(f"IMAP: Unexpected error marking emails as read: {e}")
            raise

    def disconnect(self) -> None:
        if self.imap_client:
            try:
                self.imap_client.logout()
                logger.info(f"IMAP: Disconnected from {self.username}'s mailbox.")
            except imaplib.IMAP4.error as e:
                logger.error(f"IMAP: Error during disconnect: {e}")
            finally:
                self.imap_client = None
        else:
            logger.warning("IMAP: No active connection to disconnect.")

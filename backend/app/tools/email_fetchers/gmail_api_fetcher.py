import base64
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

# pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import os.path

from .base_fetcher import AbstractEmailFetcher, EmailMessage, Attachment
from app.utils.logger import getLogger

logger = getLogger(__name__)

# If modifying these SCOPES, delete token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/gmail.modify']  # modify for marking as read


class GmailAPIFetcher(AbstractEmailFetcher):

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.credentials_file = config.get("credentials_json_path",
                                           "credentials.json")  # Path to your credentials.json
        self.token_file = config.get("token_json_path",
                                     f"token_{self.account_email.replace('@', '_').replace('.', '_')}.json")  # Unique token per account
        self.service = None

    def _get_credentials(self):
        creds = None
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Gmail API: Failed to refresh token for {self.account_email}: {e}")
                    # May need to re-authenticate manually
                    creds = None  # Force re-authentication
            if not creds:  # creds is still None if refresh failed or no token.json
                if not os.path.exists(self.credentials_file):
                    msg = f"Gmail API: credentials.json not found at {self.credentials_file}. Please download it from Google Cloud Console."
                    logger.error(msg)
                    raise FileNotFoundError(msg)
                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                # Run authorization flow in console
                # For non-interactive environments, you'd use a service account or a different OAuth flow
                creds = flow.run_local_server(port=0)  # Or flow.run_console()
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        return creds

    def connect(self) -> None:
        try:
            creds = self._get_credentials()
            self.service = build('gmail', 'v1', credentials=creds)
            logger.info(f"Gmail API: Successfully connected for user {self.account_email or 'default'}")
        except Exception as e:
            logger.error(f"Gmail API: Connection failed for {self.account_email or 'default'}: {e}")
            raise ConnectionError(f"Gmail API connection failed: {e}")

    def _parse_part(self, part, email_obj: EmailMessage):
        """Helper to parse parts of a Gmail message payload."""
        mime_type = part.get('mimeType')
        body = part.get('body')
        filename = part.get('filename')
        data = body.get('data')
        attachment_id = body.get('attachmentId')  # For large attachments

        if data:
            decoded_data = base64.urlsafe_b64decode(data.encode('UTF-8'))
            if filename:  # It's an attachment
                email_obj.attachments.append(
                    Attachment(filename=filename, content_type=mime_type, data=decoded_data)
                )
            elif mime_type == 'text/plain' and email_obj.body_text is None:
                email_obj.body_text = decoded_data.decode('utf-8', errors='replace')
            elif mime_type == 'text/html' and email_obj.body_html is None:
                email_obj.body_html = decoded_data.decode('utf-8', errors='replace')
        elif attachment_id and filename:  # Large attachment, fetch separately
            try:
                att_data = self.service.users().messages().attachments().get(
                    userId='me', messageId=email_obj.id, id=attachment_id).execute()
                decoded_data = base64.urlsafe_b64decode(att_data['data'].encode('UTF-8'))
                email_obj.attachments.append(
                    Attachment(filename=filename, content_type=mime_type, data=decoded_data)
                )
            except Exception as e:
                logger.error(f"Gmail API: Failed to fetch large attachment {filename} for email {email_obj.id}: {e}")

        if 'parts' in part:
            for sub_part in part['parts']:
                self._parse_part(sub_part, email_obj)

    def fetch_emails(self, criteria: Optional[Dict[str, Any]] = None) -> List[EmailMessage]:
        if not self.service:
            raise ConnectionError("Not connected to Gmail API.")

        fetched_emails: List[EmailMessage] = []
        query = 'is:unread'  # Default
        if criteria and "query_string" in criteria:  # e.g., "is:unread from:someone@example.com"
            query = criteria["query_string"]
        elif criteria and "since_date" in criteria:  # datetime object
            # Gmail query format for date: after:YYYY/MM/DD
            date_str = criteria["since_date"].strftime("%Y/%m/%d")
            query = f'is:unread after:{date_str}'  # Example combining

        try:
            logger.debug(f"Gmail API: Fetching emails with query: {query}")
            results = self.service.users().messages().list(userId='me', q=query).execute()
            messages_info = results.get('messages', [])

            if not messages_info:
                logger.info(f"Gmail API: No emails found for query '{query}'")
                return []

            logger.info(f"Gmail API: Found {len(messages_info)} emails matching query.")

            for msg_info in messages_info:
                msg_id = msg_info['id']
                # Get the full message. 'format': 'full' or 'metadata' or 'raw'
                # 'full' gives parsed payload, headers, etc.
                # 'raw' gives RFC 2822 string (base64url encoded)
                msg = self.service.users().messages().get(userId='me', id=msg_id, format='full').execute()

                payload = msg.get('payload', {})
                headers = payload.get('headers', [])

                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), None)
                sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), None)
                to_recipients = [h['value'] for h in headers if h['name'].lower() == 'to']
                cc_recipients = [h['value'] for h in headers if h['name'].lower() == 'cc']
                message_id_header = next((h['value'] for h in headers if h['name'].lower() == 'message-id'), None)

                received_timestamp_ms = int(msg.get('internalDate', 0))
                received_dt = datetime.fromtimestamp(received_timestamp_ms / 1000.0) if received_timestamp_ms else None

                email_obj = EmailMessage(
                    id=msg_id,
                    message_id_header=message_id_header,
                    subject=subject,
                    sender=sender,
                    recipients_to=to_recipients,
                    recipients_cc=cc_recipients,
                    body_text=None,  # Will be populated by _parse_part
                    body_html=None,  # Will be populated by _parse_part
                    received_date=received_dt,
                    attachments=[],
                    raw=msg,  # Store the raw API response
                    provider_type="gmail_api",
                    account_email=self.account_email
                )

                self._parse_part(payload, email_obj)
                fetched_emails.append(email_obj)

            return fetched_emails

        except Exception as e:
            logger.error(f"Gmail API: Error during email fetching for {self.account_email}: {e}")
            raise

    def mark_as_read(self, email_ids: List[str]) -> None:
        if not self.service:
            raise ConnectionError("Not connected to Gmail API.")
        if not email_ids:
            return

        # Gmail API allows batch modification
        # To mark as read, we remove the 'UNREAD' label
        body = {'ids': email_ids, 'removeLabelIds': ['UNREAD']}
        try:
            logger.info(f"Gmail API: Marking emails as read: {email_ids}")
            self.service.users().messages().batchModify(userId='me', body=body).execute()
        except Exception as e:
            logger.error(f"Gmail API: Error marking emails {email_ids} as read: {e}")

    def disconnect(self) -> None:
        # For Gmail API with google-api-python-client, there isn't an explicit disconnect.
        # The service object will be garbage collected.
        self.service = None
        logger.info(f"Gmail API: 'Disconnected' (service object cleared) for user {self.account_email or 'default'}")
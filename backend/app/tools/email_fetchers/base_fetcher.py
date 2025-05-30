from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import List, Optional, Any, Dict
import datetime

@dataclass
class Attachment:
    filename: str
    content_type: str
    content: bytes

@dataclass
class EmailMessage:
    id: str  # Provider-specific ID
    message_id_header: Optional[str]  # Standard Message-ID header
    subject: Optional[str]
    sender: Optional[str]
    body_text: Optional[str]
    body_html: Optional[str]
    received_date: Optional[datetime.datetime]
    recipients_to: List[str] = field(default_factory=list)
    recipients_cc: List[str] = field(default_factory=list)
    recipients_bcc: List[str] = field(default_factory=list)
    attachments: List[Attachment] = field(default_factory=list)
    raw: Any = None  # Raw message object from the library, for debugging or advanced use
    provider_type: Optional[str] = None  # e.g., "gmail_api", "outlook_graph", "imap"
    account_email: Optional[str] = None  # The email address of the account this was fetched from


class AbstractEmailFetcher(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.account_email = config.get("email_address") # Useful for tagging messages

    @abstractmethod
    def connect(self) -> None:
        """Connects to the email server/service."""
        pass

    @abstractmethod
    def fetch_emails(self, criteria: Optional[Dict[str, Any]] = None) -> List[EmailMessage]:
        """
        Fetches emails based on criteria.
        Criteria could include: 'UNSEEN', 'SINCE date', 'FROM sender', etc.
        Returns a list of EmailMessage objects.
        """
        pass

    @abstractmethod
    def mark_as_read(self, email_ids: List[str]) -> None:
        """Marks specified emails as read on the server."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnects from the email server/service."""
        pass

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
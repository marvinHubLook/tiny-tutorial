import json
import time
import logging
import threading
from typing import Dict, Any, Type

from app.tools.email_fetchers.base_fetcher import AbstractEmailFetcher, EmailMessage
from app.tools.email_fetchers.imap_fetcher import ImapEmailFetcher
from app.tools.email_fetchers.gmail_api_fetcher import GmailAPIFetcher
from app.tools.email_fetchers.outlook_graph_fetcher import OutlookGraphAPIFetcher
from app.utils.logger import getLogger

logger = getLogger(__name__)

FETCHER_MAPPING: Dict[str, Type[AbstractEmailFetcher]] = {
    "imap": ImapEmailFetcher,
    "gmail_api": GmailAPIFetcher,
    "outlook_graph": OutlookGraphAPIFetcher,
    # Add other mappings here
}


class EmailPoller:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.accounts_config = self._load_config()
        self.threads = []
        self._stop_event = threading.Event()

    def _load_config(self) -> Dict[str, Any]:
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

    def process_email(self, email: EmailMessage, account_id: str):
        """
        This is where you'd put your logic to handle a new email.
        For example, save to database, trigger an alert, etc.
        """
        logger.info(
            f"[{account_id} ({email.account_email})] Received Email: "
            f"ID='{email.id}', From='{email.sender}', Subject='{email.subject}'"
        )
        if email.attachments:
            logger.info(f"  Attachments: {[att.filename for att in email.attachments]}")
        # Example: print body
        # logger.debug(f"  Body Text: {email.body_text[:200] if email.body_text else 'N/A'}...")

    def _poll_account(self, account_config: Dict[str, Any]):
        account_id = account_config.get("id", "UnknownAccount")
        fetcher_type_name = account_config.get("type")
        fetcher_config = account_config.get("config", {})
        fetch_interval = account_config.get("fetch_interval_seconds", 300)
        fetch_criteria = account_config.get("fetch_criteria", {})
        mark_as_read = fetch_criteria.get("mark_as_read_after_fetch", False)

        if not account_config.get("enabled", False):
            logger.info(f"Account '{account_id}' is disabled. Skipping.")
            return

        FetcherClass = FETCHER_MAPPING.get(fetcher_type_name)
        if not FetcherClass:
            logger.error(f"[{account_id}] Unknown fetcher type: {fetcher_type_name}. Skipping.")
            return

        # Add email_address to fetcher_config if not already there, for token file naming etc.
        if "email_address" not in fetcher_config and "email_address" in account_config:
            fetcher_config["email_address"] = account_config["email_address"]

        logger.info(f"[{account_id}] Starting poller thread with interval {fetch_interval}s")

        while not self._stop_event.is_set():
            try:
                logger.info(f"[{account_id}] Attempting to fetch emails...")
                with FetcherClass(fetcher_config) as fetcher:  # Uses __enter__ and __exit__ for connect/disconnect
                    new_emails = fetcher.fetch_emails(criteria=fetch_criteria)

                    if new_emails:
                        logger.info(f"[{account_id}] Fetched {len(new_emails)} new email(s).")
                        email_ids_to_mark_read = []
                        for email in new_emails:
                            try:
                                self.process_email(email, account_id)
                                if mark_as_read:
                                    email_ids_to_mark_read.append(email.id)
                            except Exception as e_proc:
                                logger.error(f"[{account_id}] Error processing email ID {email.id}: {e_proc}",
                                             exc_info=True)

                        if mark_as_read and email_ids_to_mark_read:
                            try:
                                fetcher.mark_as_read(email_ids_to_mark_read)
                                logger.info(f"[{account_id}] Marked {len(email_ids_to_mark_read)} emails as read.")
                            except Exception as e_mark:
                                logger.error(f"[{account_id}] Error marking emails as read: {e_mark}", exc_info=True)
                    else:
                        logger.info(f"[{account_id}] No new emails found.")

            except ConnectionError as e_conn:
                logger.error(f"[{account_id}] Connection error: {e_conn}. Will retry after interval.",
                             exc_info=False)  # exc_info=False as error is already logged by fetcher
            except Exception as e:
                logger.error(f"[{account_id}] Unexpected error in polling loop: {e}", exc_info=True)

            # Wait for the next interval or until stop event is set
            self._stop_event.wait(fetch_interval)

    def start(self):
        logger.info("Starting email poller service...")
        if not self.accounts_config or not self.accounts_config.get("accounts"):
            logger.warning("No accounts configured or configuration is empty. Poller will not start any fetchers.")
            return

        for acc_conf in self.accounts_config.get("accounts", []):
            if acc_conf.get("enabled", False):
                thread = threading.Thread(target=self._poll_account, args=(acc_conf,),
                                          name=f"Poller-{acc_conf.get('id', 'Unnamed')}")
                thread.daemon = True  # Allows main program to exit even if threads are running
                self.threads.append(thread)
                thread.start()
            else:
                logger.info(f"Account '{acc_conf.get('id', 'Unnamed')}' is disabled in config.")

        if not self.threads:
            logger.info("No enabled accounts found to poll.")

    def stop(self):
        logger.info("Stopping email poller service...")
        self._stop_event.set()
        for thread in self.threads:
            logger.info(f"Waiting for thread {thread.name} to finish...")
            thread.join(timeout=10)  # Give threads some time to finish current iteration
            if thread.is_alive():
                logger.warning(f"Thread {thread.name} did not finish in time.")
        logger.info("Email poller service stopped.")
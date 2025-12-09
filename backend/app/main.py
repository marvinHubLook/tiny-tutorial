import os
import sys
import time

from app.tools.email_fetchers.base_fetcher import EmailMessage
from app.tools.email_fetchers.main_poller import EmailPoller,PollingConfig

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app.utils.logger import getLogger

logger = getLogger(__name__)


def main():
    import re

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
                    data = email.body_text
                    if data is not None:
                        matcher = re.search(r'(\d(?:\s*\d){5})', data)
                        if matcher is not None:
                            verify_code = matcher.group(0)
                            # regex replace \s*
                            verify_code = re.sub(r'\s*', '', verify_code)
                            logger.info(f"====> Email from {email.sender} with verification code: {verify_code}")
                    email = poller.get_message()
                    
                logger.info("Polling completed, waiting for next poll...")
            count_flag = poller.next()
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        logger.exception(e)
    finally:
        poller.stop()


if __name__ == "__main__":
    sys.exit(main())

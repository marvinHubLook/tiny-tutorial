import os
import sys
import time
from app.tools.email_fetchers.main_poller import EmailPoller

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app.utils.logger import getLogger

logger = getLogger(__name__)


def main():
    config_path = os.path.join(current_dir, "config/email_config.json")
    print(f"Using configuration file: {config_path}")
    poller = EmailPoller(config_path)
    poller.start()

    try:
        while True:
            # Keep main thread alive until Ctrl+C
            # Check if any poller threads are still alive
            if not any(t.is_alive() for t in poller.threads if t is not None):
                logger.info("All poller threads have unexpectedly stopped.")
                break
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Ctrl+C received, shutting down...")
    finally:
        poller.stop()


if __name__ == "__main__":
    sys.exit(main())

import os
import csv
import time

import hydra
from datetime import datetime
from omegaconf import OmegaConf, DictConfig
from DrissionPage import ChromiumOptions, Chromium

from helper.cursor_register import CursorRegister
from app.tools.email_fetchers.main_poller import EmailPoller
from app.tools.email_fetchers.main_poller import PollingConfig
from app.utils.logger import getLogger

logger = getLogger(__name__)



hide_account_info = os.getenv('HIDE_ACCOUNT_INFO', 'false').lower() == 'true'
enable_headless = os.getenv('ENABLE_HEADLESS', 'false').lower() == 'true'
enable_browser_log = os.getenv('ENABLE_BROWSER_LOG', 'true').lower() == 'true' or not enable_headless


def register_cursor_core(register_config, options,email_poller: EmailPoller = None):
    try:
        browser = Chromium(options)
    except Exception as e:
        print(e)
        return None
    try:
        register = CursorRegister(browser, email_poller)
        account = email_poller.get_current_account()
        email_address = account['config']['username']

        tab_signup, status = register.sign_in(email_address)
        # tab_signup, status = register.sign_up(email_address)
        token = register.get_cursor_cookie(tab_signup)
        userId , accessToken = register.get_cursor_session_token(tab=tab_signup)
        logger.info(f"[Register] UserId: {userId}, AccessToken: {accessToken}")

        if token is not None:
            user_id = token.split("%3A%3A")[0]
            delete_low_balance_account = register_config.delete_low_balance_account
            if register_config.email_server.name == "imap_email_server" and delete_low_balance_account:
                delete_low_balance_account_threshold = register_config.delete_low_balance_account_threshold

                usage = register.get_usage(user_id)
                balance = usage["gpt-4"]["maxRequestUsage"] - usage["gpt-4"]["numRequests"]
                if balance < delete_low_balance_account_threshold:
                    register.delete_account()
                    tab_signin, status = register.sign_in(email_address)
                    token = register.get_cursor_cookie(tab_signin)

        if status and not enable_browser_log:
            register.browser.quit(force=True, del_data=True)

        if status and not hide_account_info:
            print(f"[Register] Cursor Email: {email_address}")
            print(f"[Register] Cursor Token: {token}")

        ret = {
            "username": email_address,
            "token": token,
            "user_id": userId,
            'auth_token': accessToken,
        }
        return ret
    finally:
        if browser:
            try:
                browser.quit(force=True, del_data=True)
            except Exception as e:
                print(f"[Register] Error closing browser: {e}")




def fake_chrome_options(options: ChromiumOptions):
    # Anti-detection arguments
    # options.set_argument("--no-sandbox")
    # options.set_argument("--disable-blink-features=AutomationControlled")
    #
    # options.set_argument("--disable-plugins-discovery")
    # options.set_argument("--disable-web-security")
    # options.set_argument("--disable-features=VizDisplayCompositor")
    # options.set_argument("--disable-ipc-flooding-protection")
    #
    # # Performance and stability
    # options.set_argument("--no-first-run")
    # options.set_argument("--no-default-browser-check")
    # options.set_argument("--disable-background-timer-throttling")
    # options.set_argument("--disable-renderer-backgrounding")
    # options.set_argument("--disable-backgrounding-occluded-windows")
    # options.set_argument("--disable-client-side-phishing-detection")
    # options.set_argument("--disable-component-update")
    # options.set_argument("--disable-default-apps")
    # options.set_argument("--disable-domain-reliability")
    # options.set_argument("--disable-background-networking")
    # options.set_argument("--disable-sync")
    #
    # # Memory and resource management
    # options.set_argument("--max_old_space_size=4096")
    # options.set_argument("--disable-dev-shm-usage")
    # options.set_argument("--disable-gpu")
    # options.set_argument("--remote-debugging-port=9222")

    # Language and locale settings
    # options.set_argument("--lang=en-US")
    # options.set_argument("--accept-lang=en-US,en;q=0.9")
    #
    # # Additional stealth features
    # # options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # # options.add_experimental_option("useAutomationExtension", False)
    # # options.add_experimental_option("detach", True)
    #
    # # Preferences to make it more browser-like
    # prefs = {
    #     "profile.default_content_setting_values": {
    #         "notifications": 2,  # Block notifications
    #         "geolocation": 2,  # Block location sharing
    #         "media_stream": 2,  # Block camera/microphone
    #     },
    #     "profile.managed_default_content_settings": {
    #         "images": 1
    #     },
    #     "profile.default_content_settings": {
    #         "popups": 0
    #     },
    #     "managed.default_content_settings": {
    #         "images": 1
    #     },
    #     "profile.password_manager_enabled": False,
    #     "profile.default_content_setting_values.notifications": 2,
    #     "credentials_enable_service": False,
    #     "password_manager_enabled": False,
    #     # Hardware acceleration
    #     "hardware_acceleration_mode_enabled": True,
    #     # WebGL
    #     "webgl_enabled": True,
    #     "webgl2_enabled": True,
    #     # Plugins
    #     "plugins.run_all_flash_in_allow_mode": True,
    #     "plugins.plugins_disabled": [],
    #     # Network prediction
    #     "net.network_prediction_options": 2,
    #     # Privacy settings
    #     "profile.default_content_setting_values.cookies": 1,
    #     "profile.block_third_party_cookies": False,
    #     "profile.cookie_controls_mode": 0,
    # }
    #
    # options.set_pref("prefs", prefs)
    #
    # # Set realistic screen properties
    # options.set_argument("--screen-size=1920x1080")
    # options.set_argument("--force-device-scale-factor=1")
    return

def register_cursor(register_config):
    options = ChromiumOptions()
    options.auto_port()
    options.new_env()
    # Use turnstilePatch from https://github.com/TheFalloutOf76/CDP-bug-MouseEvent-.screenX-.screenY-patcher
    turnstile_patch_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "turnstilePatch"))
    options.add_extension(turnstile_patch_path)

    # If fail to pass the cloudflare in headless mode, try to align the user agent with your real browser
    if enable_headless:
        from platform import platform
        if platform == "linux" or platform == "linux2":
            platformIdentifier = "X11; Linux x86_64"
        elif platform == "darwin":
            platformIdentifier = "Macintosh; Intel Mac OS X 10_15_7"
        elif platform == "win32":
            platformIdentifier = "Windows NT 10.0; Win64; x64"
        # Please align version with your Chrome
        chrome_version = "131.0.0.0"
        options.set_user_agent(
            f"Mozilla/5.0 ({platformIdentifier}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36")
        options.headless()

    options.set_argument("--disable-extensions-except=" + turnstile_patch_path)
    options.set_argument("--hide-crash-restore-bubble")
    options.set_proxy("socks5://192.168.1.100:7890")

    fake_chrome_options(options)

    number = register_config.number
    max_workers = register_config.max_workers
    print(f"[Register] Start to register {number} accounts in {max_workers} threads")


    current_dir = '/home/bingo/PycharmProjects/tiny-tutorial/backend/app'
    config_path = os.path.join(current_dir, "config/email_config.json")
    email_poller = EmailPoller(config_path,PollingConfig(
        max_poll_count=6,
        poll_interval=30,
        max_emails_per_poll=100,
    ))
    email_poller.start(auto_flag=False)
    results = []
    while email_poller.next():
        time.sleep(3)
        result = register_cursor_core(register_config,options,email_poller);
        if result is not None:
            logger.info(f"[Register] Register account: {result['username']}")
            results.append(result)
    email_poller.stop()

    results = [result for result in results if result["token"] is not None]
    if len(results) > 0:
        formatted_date = datetime.now().strftime("%Y-%m-%d")

        fieldnames = results[0].keys()
        # Write username, token into a csv file
        with open(f"./output_{formatted_date}.csv", 'a', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writerows(results)
        # Only write token to csv file, without header
        tokens = [{'token': row['token']} for row in results]
        with open(f"./token_{formatted_date}.csv", 'a', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=['token'])
            writer.writerows(tokens)

    return results


@hydra.main(config_path="config", config_name="config", version_base=None)
def main(config: DictConfig):
    OmegaConf.set_struct(config, False)
    account_infos = register_cursor(config.register)
    tokens = list(set([row['token'] for row in account_infos]))
    print(f"[Register] Register {len(tokens)} accounts successfully")


if __name__ == "__main__":
    main()

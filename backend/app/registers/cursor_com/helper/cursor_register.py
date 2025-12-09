import re
import uuid
import queue
import hashlib
import base64
import secrets
import requests
import threading
from faker import Faker
from DrissionPage import Chromium
import time
from typing import Optional, Tuple
from app.utils.logger import getLogger
from app.tools.email_fetchers.main_poller import EmailPoller

logger = getLogger(__name__)

enable_register_log = True


class CursorRegister:
    CURSOR_URL = "https://www.cursor.com/"
    CURSOR_SIGNIN_URL = "https://authenticator.cursor.sh"
    CURSOR_PASSWORD_URL = "https://authenticator.cursor.sh/password"
    CURSOR_MAGAIC_CODE_URL = "https://authenticator.cursor.sh/magic-code"
    CURSOR_SIGNUP_URL = "https://authenticator.cursor.sh/sign-up"
    CURSOR_SIGNUP_PASSWORD_URL = "https://authenticator.cursor.sh/sign-up/password"
    CURSOR_EMAIL_VERIFICATION_URL = "https://authenticator.cursor.sh/email-verification"
    CURSOR_SETTING_URL = "https://www.cursor.com/settings"
    CURSOR_USAGE_URL = "https://www.cursor.com/api/usage"

    CURSOR_SMS_VERIFICATION_URL = "https://authenticator.cursor.sh/radar-challenge/send"

    def __init__(self, browser: Chromium, email_poller: EmailPoller = None):
        self.browser = browser
        self.email_poller = email_poller
        self.retry_times = 5
        self.thread_id = threading.get_ident()


    def _match_verification_code(self,data):
        if data is not None:
            matcher = re.search(r'(\d(?:\s*\d){5})', data)
            if matcher is not None:
                verify_code = matcher.group(0)
                return re.sub(r'\s*', '', verify_code)
        return None


    def sign_in(self, email, password=None):

        assert any(x is not None for x in
                   (self.email_poller, password)), "Should provide email server or password. At least one of them."

        tab = self.browser.new_tab(self.CURSOR_SIGNIN_URL)
        # Input email
        for retry in range(self.retry_times):
            try:
                if enable_register_log: print(f"[Register][{self.thread_id}][{retry}] Input email")
                tab.ele("xpath=//input[@name='email']").input(email, clear=True)
                tab.ele("@type=submit").click()

                # If not in password page, try pass turnstile page
                if not tab.wait.url_change(self.CURSOR_PASSWORD_URL, timeout=3) and self.CURSOR_SIGNIN_URL in tab.url:
                    if enable_register_log: print(
                        f"[Register][{self.thread_id}][{retry}] Try pass Turnstile for email page")
                    self._cursor_turnstile(tab)

            except Exception as e:
                print(f"[Register][{self.thread_id}] Exception when handlding email page.")
                print(e)

            # In password page or data is validated, continue to next page
            if tab.wait.url_change(self.CURSOR_PASSWORD_URL, timeout=5):
                print(f"[Register][{self.thread_id}] Continue to password page")
                break

            tab.refresh()
            # Kill the function since time out
            if retry == self.retry_times - 1:
                print(f"[Register][{self.thread_id}] Timeout when inputing email address")
                return tab, False
        # sleep for 5 seconds
        time.sleep(3)
        # Use email sign-in code in password page
        for retry in range(self.retry_times):
            try:
                if enable_register_log: print(f"[Register][{self.thread_id}][{retry}] Input password")
                if password is None:
                    tab.ele("xpath=//button[@value='magic-code']").click()

                # If not in verification code page, try pass turnstile page
                if not tab.wait.url_change(self.CURSOR_MAGAIC_CODE_URL,
                                           timeout=3) and self.CURSOR_PASSWORD_URL in tab.url:
                    if enable_register_log: print(
                        f"[Register][{self.thread_id}][{retry}] Try pass Turnstile for password page")
                    self._cursor_turnstile(tab)

            except Exception as e:
                print(f"[Register][{self.thread_id}] Exception when handling password page.")
                print(e)

            # In code verification page or data is validated, continue to next page
            if tab.wait.url_change(self.CURSOR_MAGAIC_CODE_URL, timeout=5):
                print(f"[Register][{self.thread_id}] Continue to email code page")
                break

            if tab.wait.eles_loaded("xpath=//p[contains(text(), 'Authentication blocked, please contact your admin')]",
                                    timeout=3):
                print(f"[Register][{self.thread_id}][Error] Authentication blocked, please contact your admin.")
                return tab, False

            if tab.wait.eles_loaded("xpath=//div[contains(text(), 'Sign up is restricted.')]", timeout=3):
                print(f"[Register][{self.thread_id}][Error] Sign up is restricted.")
                return tab, False

            tab.refresh()
            # Kill the function since time out
            if retry == self.retry_times - 1:
                if enable_register_log: print(f"[Register][{self.thread_id}] Timeout when inputing password")
                return tab, False

        time.sleep(3)

        # Get email verification code
        try:
            verify_code = None
            wait_flag = True
            while wait_flag and self.email_poller.wait_for_completion(timeout=10) is False:
                email = self.email_poller.get_message()
                while email is not None:
                    data = email.body_text
                    verify_code = self._match_verification_code(data)
                    if verify_code is not None:
                        wait_flag = False
                        break
                    email = self.email_poller.get_message()
            assert verify_code is not None, "Fail to parse code from email."
        except Exception as e:
            print(f"[Register][{self.thread_id}] Fail to get code from email.")
            return tab, False

        # Input email verification code
        for retry in range(self.retry_times):
            try:
                if enable_register_log: print(f"[Register][{self.thread_id}][{retry}] Input email verification code")

                for idx, digit in enumerate(verify_code, start=0):
                    tab.ele(f"xpath=//input[@data-index={idx}]").input(digit, clear=True)
                    tab.wait(0.1, 0.3)
                tab.wait(0.5, 1.5)

                if not tab.wait.url_change(self.CURSOR_URL, timeout=3) and self.CURSOR_MAGAIC_CODE_URL in tab.url:
                    if enable_register_log: print(
                        f"[Register][{self.thread_id}][{retry}] Try pass Turnstile for email code page.")
                    self._cursor_turnstile(tab)

            except Exception as e:
                print(f"[Register][{self.thread_id}] Exception when handling email code page.")
                print(e)

            if tab.wait.url_change(self.CURSOR_URL, timeout=3):
                break

            tab.refresh()
            # Kill the function since time out
            if retry == self.retry_times - 1:
                if enable_register_log: print(
                    f"[Register][{self.thread_id}] Timeout when inputing email verification code")
                return tab, False

        return tab, True

    def sign_up(self, email, password=None):

        assert self.email_poller is not None, "Should provide email server."

        if password is None:
            fake = Faker()
            password = fake.password(length=12, special_chars=True, digits=True, upper_case=True, lower_case=True)

        tab = self.browser.new_tab(self.CURSOR_SIGNUP_URL)
        # Input email
        for retry in range(self.retry_times):
            try:
                if enable_register_log: print(f"[Register][{self.thread_id}][{retry}] Input email")
                tab.ele("xpath=//input[@name='email']").input(email, clear=True)
                tab.ele("@type=submit").click()

                # If not in password page, try pass turnstile page
                if not tab.wait.url_change(self.CURSOR_SIGNUP_PASSWORD_URL,
                                           timeout=3) and self.CURSOR_SIGNUP_URL in tab.url:
                    if enable_register_log: print(
                        f"[Register][{self.thread_id}][{retry}] Try pass Turnstile for email page")
                    self._cursor_turnstile(tab)

            except Exception as e:
                print(f"[Register][{self.thread_id}] Exception when handlding email page.")
                print(e)

            # In password page or data is validated, continue to next page
            if tab.wait.url_change(self.CURSOR_SIGNUP_PASSWORD_URL, timeout=5):
                print(f"[Register][{self.thread_id}] Continue to password page")
                break

            tab.refresh()
            # Kill the function since time out
            if retry == self.retry_times - 1:
                print(f"[Register][{self.thread_id}] Timeout when inputing email address")
                return tab, False

        # Use email sign-in code in password page
        # for retry in range(self.retry_times):
        try:
            if enable_register_log: print(f"[Register][{self.thread_id}][{retry}] Input password")
            tab.ele("xpath=//input[@name='password']").input(password, clear=True)
            tab.ele('@type=submit').click()

            # If not in verification code page, try pass turnstile page
            if not tab.wait.url_change(self.CURSOR_EMAIL_VERIFICATION_URL,
                                       timeout=3) and self.CURSOR_SIGNUP_PASSWORD_URL in tab.url:
                if enable_register_log: print(
                    f"[Register][{self.thread_id}][{retry}] Try pass Turnstile for password page")
                self._cursor_turnstile(tab)

        except Exception as e:
            print(f"[Register][{self.thread_id}] Exception when handling password page.")
            print(e)

        # In code verification page or data is validated, continue to next page
        if tab.wait.url_change(self.CURSOR_EMAIL_VERIFICATION_URL, timeout=5):
            print(f"[Register][{self.thread_id}] Continue to email code page")

        if tab.wait.eles_loaded("xpath=//div[contains(text(), 'Sign up is restricted.')]", timeout=3):
            print(f"[Register][{self.thread_id}][Error] Sign up is restricted.")
            return tab, False

        if tab.wait.eles_loaded("xpath=//div[contains(text(), 'This email is not available.')]", timeout=3):
            print(f"[Register][{self.thread_id}][Error] This email is not available.")
            return tab, False
            # tab.refresh()
            # # Kill the function since time out
            # if retry == self.retry_times - 1:
            #     if enable_register_log: print(f"[Register][{self.thread_id}] Timeout when inputing password")
            #     return tab, False

        # Get email verification code
        try:
            verify_code = None
            wait_flag = True
            while wait_flag and self.email_poller.wait_for_completion(timeout=30) is False:
                email = self.email_poller.get_message()
                while email is not None:
                    data = email.body_text
                    verify_code = self._match_verification_code(data)
                    if verify_code is not None:
                        wait_flag = False
                        break
                    email = self.email_poller.get_message()

            assert verify_code is not None, "Fail to get code from email."

        except Exception as e:
            print(f"[Register][{self.thread_id}] Fail to get code from email.")
            return tab, False

        # Input email verification code
        for retry in range(self.retry_times):
            try:
                if enable_register_log: print(f"[Register][{self.thread_id}][{retry}] Input email verification code")

                for idx, digit in enumerate(verify_code, start=0):
                    tab.ele(f"xpath=//input[@data-index={idx}]").input(digit, clear=True)
                    tab.wait(0.1, 0.3)
                tab.wait(0.5, 1.5)

                if not tab.wait.url_change(self.CURSOR_URL,
                                           timeout=3) and self.CURSOR_EMAIL_VERIFICATION_URL in tab.url:
                    if enable_register_log: print(
                        f"[Register][{self.thread_id}][{retry}] Try pass Turnstile for email code page.")
                    self._cursor_turnstile(tab)

            except Exception as e:
                print(f"[Register][{self.thread_id}] Exception when handling email code page.")
                print(e)

            if tab.wait.url_change(self.CURSOR_URL, timeout=3):
                break

            tab.refresh()
            # Kill the function since time out
            if retry == self.retry_times - 1:
                if enable_register_log: print(
                    f"[Register][{self.thread_id}] Timeout when inputing email verification code")
                return tab, False
        return tab, True

    def get_usage(self, user_id):
        tab = self.browser.new_tab(f"{self.CURSOR_USAGE_URL}?user={user_id}")
        return tab.json

    # tab: A tab has signed in
    def delete_account(self):
        tab = self.browser.new_tab(self.CURSOR_SETTING_URL)
        tab.ele("xpath=//div[contains(text(), 'Advanced')]").click()
        tab.ele("xpath=//button[contains(text(), 'Delete Account')]").click()
        tab.ele("""xpath=//input[@placeholder="Type 'Delete' to confirm"]""").input("Delete", clear=True)
        tab.ele("xpath=//span[contains(text(), 'Delete')]").click()
        return tab

    def parse_cursor_verification_code(self, email_data):
        message = ""
        verify_code = None

        if "content" in email_data:
            message = email_data["content"]
            message = message.replace(" ", "")
            verify_code = re.search(r'(?:\r?\n)(\d{6})(?:\r?\n)', message).group(1)
        elif "text" in email_data:
            message = email_data["text"]
            message = message.replace(" ", "")
            verify_code = re.search(r'(?:\r?\n)(\d{6})(?:\r?\n)', message).group(1)

        return verify_code

    def get_cursor_cookie(self, tab):
        def _generate_pkce_pair():
            code_verifier = secrets.token_urlsafe(43)
            code_challenge_digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
            code_challenge = base64.urlsafe_b64encode(code_challenge_digest).decode('utf-8').rstrip('=')
            return code_verifier, code_challenge

        try:

            verifier, challenge = _generate_pkce_pair()
            id = uuid.uuid4()
            client_login_url = f"https://www.cursor.com/cn/loginDeepControl?challenge={challenge}&uuid={id}&mode=login"
            tab.get(client_login_url)
            tab.ele("xpath=//span[contains(text(), 'Yes, Log In')]").click()

            auth_pooll_url = f"https://api2.cursor.sh/auth/poll?uuid={id}&verifier={verifier}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Cursor/0.48.6 Chrome/132.0.6834.210 Electron/34.3.4 Safari/537.36",
                "Accept": "*/*"
            }
            response = requests.get(auth_pooll_url, headers=headers, timeout=5)
            data = response.json()
            accessToken = data.get("accessToken", None)
            authId = data.get("authId", "")
            if len(authId.split("|")) > 1:
                userId = authId.split("|")[1]
                token = f"{userId}%3A%3A{accessToken}"
            else:
                token = accessToken
        except:
            print(f"[Register][{self.thread_id}] Fail to get cookie.")
            return None

        if enable_register_log:
            if token is not None:
                print(f"[Register][{self.thread_id}] Get Account Cookie Successfully.")
            else:
                print(f"[Register][{self.thread_id}] Get Account Cookie Failed.")
        return token

    def get_cursor_session_token(self,tab, max_attempts: int = 3, retry_interval: int = 2) -> Optional[Tuple[str, str]]:
        """
        获取Cursor会话token

        Args:
            tab: 浏览器标签页对象
            max_attempts: 最大尝试次数
            retry_interval: 重试间隔(秒)

        Returns:
            Tuple[str, str] | None: 成功返回(userId, accessToken)元组，失败返回None
        """
        logger.info("开始获取会话令牌")

        # 首先尝试使用UUID深度登录方式
        logger.info("尝试使用深度登录方式获取token")

        def _generate_pkce_pair():
            """生成PKCE验证对"""
            code_verifier = secrets.token_urlsafe(43)
            code_challenge_digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
            code_challenge = base64.urlsafe_b64encode(code_challenge_digest).decode('utf-8').rstrip('=')
            return code_verifier, code_challenge

        attempts = 0
        while attempts < max_attempts:
            try:
                verifier, challenge = _generate_pkce_pair()
                id = uuid.uuid4()
                client_login_url = f"https://www.cursor.com/cn/loginDeepControl?challenge={challenge}&uuid={id}&mode=login"

                logger.info(f"访问深度登录URL: {client_login_url}")
                tab.get(client_login_url)
                # save_screenshot(tab, f"deeplogin_attempt_{attempts}")

                if tab.ele("xpath=//span[contains(text(), 'Yes, Log In')]", timeout=5):
                    logger.info("点击确认登录按钮")
                    tab.ele("xpath=//span[contains(text(), 'Yes, Log In')]").click()
                    time.sleep(1.5)

                    auth_poll_url = f"https://api2.cursor.sh/auth/poll?uuid={id}&verifier={verifier}"
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Cursor/0.48.6 Chrome/132.0.6834.210 Electron/34.3.4 Safari/537.36",
                        "Accept": "*/*"
                    }

                    logger.info(f"轮询认证状态: {auth_poll_url}")
                    response = requests.get(auth_poll_url, headers=headers, timeout=5)

                    if response.status_code == 200:
                        data = response.json()
                        accessToken = data.get("accessToken", None)
                        authId = data.get("authId", "")

                        if accessToken:
                            userId = ""
                            if len(authId.split("|")) > 1:
                                userId = authId.split("|")[1]

                            logger.info("成功获取账号token和userId")
                            return userId, accessToken
                    else:
                        logger.error(f"API请求失败，状态码: {response.status_code}")
                else:
                    logger.warning("未找到登录确认按钮")

                attempts += 1
                if attempts < max_attempts:
                    wait_time = retry_interval * attempts  # 逐步增加等待时间
                    logger.warning(f"第 {attempts} 次尝试未获取到token，{wait_time}秒后重试...")
                    # save_screenshot(tab, f"token_attempt_{attempts}")
                    time.sleep(wait_time)

            except Exception as e:
                logger.error(f"深度登录获取token失败: {str(e)}")
                attempts += 1
                # save_screenshot(tab, f"token_error_{attempts}")
                if attempts < max_attempts:
                    wait_time = retry_interval * attempts
                    logger.warning(f"将在 {wait_time} 秒后重试...")
                    time.sleep(wait_time)

    def _cursor_turnstile(self, tab, retry_times=5):
        for retry in range(retry_times):  # Retry times
            try:
                if enable_register_log: print(f"[Register][{self.thread_id}][{retry}] Passing Turnstile")
                challenge_shadow_root = tab.ele('@id=cf-turnstile').child().shadow_root
                challenge_shadow_button = challenge_shadow_root.ele("tag:iframe", timeout=30).ele("tag:body").sr(
                    "xpath=//input[@type='checkbox']")
                if challenge_shadow_button:
                    challenge_shadow_button.click()
                    break
            except:
                pass
            if retry == retry_times - 1:
                print("[Register] Timeout when passing turnstile")

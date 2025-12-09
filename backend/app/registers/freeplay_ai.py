import json
import logging
import uuid
from typing import Dict, List, Optional

import requests
from faker import Faker
from tqdm import tqdm

from app.utils.logger import getLogger
import random

logger = getLogger(__name__)

class FreeplayClient:
    def __init__(self, proxy_config: str = None, user_agent: str = None):
        self.proxies = (
            {"http": proxy_config, "https": proxy_config} if proxy_config else None
        )
        self.user_agent = (
            user_agent if user_agent is not None else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/237.84.2.178 Safari/537.36"
        )
        self.faker = Faker()

    def check_balance(self, session_id: str) -> float:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        cookies = {"session": session_id}
        try:
            response = requests.get(
                "https://app.freeplay.ai/app_data/settings/billing",
                headers=headers,
                cookies=cookies,
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                for feature in data.get("feature_usage", []):
                    if feature.get("feature_name") == "Freeplay credits":
                        return feature.get("usage_limit", 0) - feature.get(
                            "usage_value", 0
                        )
            return 0.0
        except Exception as e:
            logging.warning(
                f"Failed to check balance for session_id ending in ...{session_id[-4:]}: {e}"
            )
            return 0.0

    def generate_random_email(self) -> str:
        """生成随机邮箱"""
        # random_str = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        name_parts = [self.faker.first_name().lower(), self.faker.last_name().lower()]
        random.shuffle(name_parts)
        username = "".join(name_parts)
        if random.choice([True, False]):
            username += str(random.randint(1, 99))
        domains = ["gmail.com", "outlook.com"]
        domain = random.choice(domains)
        return f"{username}@{domain}"

    def register(self) -> Optional[Dict]:
        url = "https://app.freeplay.ai/app_data/auth/signup"
        payload = {
            "email": self.generate_random_email(),
            "password": f"{uuid.uuid4().hex[:8]}fpA1!",
            "account_name": self.faker.name(),
            "first_name": self.faker.first_name(),
            "last_name": self.faker.last_name(),
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "origin": "https://app.freeplay.ai",
            "referer": "https://app.freeplay.ai/signup",
        }
        try:
            response = requests.post(
                url,
                data=json.dumps(payload),
                headers=headers,
                proxies=self.proxies,
                timeout=20,
            )
            response.raise_for_status()
            project_id = response.json()["project_id"]
            session = response.cookies.get("session")
            if project_id and session:
                return {
                    "email": payload["email"],
                    "password": payload["password"],
                    "session_id": session,
                    "project_id": project_id,
                    "balance": 5.0,  # 新注册账号默认5刀
                }
        except Exception as e:
            # logging.error(f"Account registration failed: {e}")
            return self.register()

    def chat(
            self,
            session_id: str,
            project_id: str,
            model_config: Dict,
            messages: List[Dict],
            params: Dict,
    ) -> requests.Response:
        url = f"https://app.freeplay.ai/app_data/projects/{project_id}/llm-completions"
        headers = {
            "accept": "*/*",
            "origin": "https://app.freeplay.ai",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        }
        cookies = {"session": session_id}

        # 兼容 system message
        system_prompt = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                user_messages.append(msg)

        if system_prompt:
            # 将 system prompt 插入到第一个 user message 前
            if user_messages:
                user_messages[0][
                    "content"
                ] = f"{system_prompt}\n\nUser: {user_messages[0]['content']}"

        json_payload = {
            "messages": user_messages,
            "params": [
                {
                    "name": "max_tokens",
                    "value": params.get("max_tokens", model_config["max_tokens"]),
                    "type": "integer",
                },
                {
                    "name": "temperature",
                    "value": params.get("temperature", 0.5),
                    "type": "float",
                },
                {"name": "top_p", "value": params.get("top_p", 1.0), "type": "float"},
            ],
            "model_id": model_config["model_id"],
            "variables": {},
            "history": None,
            "asset_references": {},
        }
        files = {"json_data": (None, json.dumps(json_payload))}
        return requests.post(
            url, headers=headers, cookies=cookies, files=files, stream=True
        )


if __name__ == "__main__":
    # load proxy config
    with open("../config/proxies.txt", "r", encoding="utf-8") as f:
        proxies = [line.strip() for line in f]
    # load ua config
    with open("../config/ua.txt", "r", encoding="utf-8") as f:
        uas = [line.strip() for line in f]
    nums = 100
    # write to file, format: email----password----session_id----project_id, and tqdm to show progress
    with open("../config/freeplay_ai.txt", "a", encoding="utf-8") as f:
        for i in tqdm(range(nums)):
            proxy = proxies[i % len(proxies)]
            agent = FreeplayClient(proxy_config=proxy)
            res = agent.register()
            if res:
                f.write(
                    f"{res['email']}----{res['password']}----{res['session_id']}----{res['project_id']}----{res['balance']}\n"
                )
                if random.random() < 0.3:
                    balance = agent.check_balance(res["session_id"])
                    logger.info(f"email: {res['email']} balance: {balance}")
            else:
                print("register failed")
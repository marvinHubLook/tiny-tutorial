import argparse
import concurrent.futures
import json
import logging
import os
import random
import string
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from faker import Faker

# ================== 配置区 ==================
# 请求头配置
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
COMMON_HEADERS = {
    "User-Agent": USER_AGENT,
    "Content-Type": "application/json",
    "accept-language": "en",
    "origin": "https://cloud.browser-use.com",
    "priority": "u=1, i",
    "referer": "https://cloud.browser-use.com/",
    "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "Windows",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
}

# 特殊请求头
STACK_AUTH_HEADERS = {
    "x-stack-access-type": "client",
    "x-stack-client-version": "js @stackframe/stack@2.8.3",
    "x-stack-override-error-status": "true",
    "x-stack-project-id": "2397ef60-a33e-4efb-ad9b-300da67ee29e",
    "x-stack-publishable-client-key": "pck_k3cdtpv9yasqz13p4rg13br6nwh2zg9d2ghcw25bnnkg8",
    "x-stack-random-nonce": "95d90g0vbpcx7gmw6ma45cbpqvhb531q7wb7m109qb718",
    "x-stack-refresh-token": "ahfx5854zqtfn3hs3pr6724ahbtdadjemm84e531enja0",
}

# API 端点
REGISTER_URL = "https://api.stack-auth.com/api/v1/auth/password/sign-up"
CREATE_ORDER_URL = "https://api.browser-use.com/payments/create-one-time-purchase"
CREATE_KEY_URL = "https://api.browser-use.com/api/key"
GET_BALANCE_URL = "https://api.browser-use.com/api/v1/balance"

# 输出文件
ORDER_URLS_FILE = "browser_use_orders.txt"
ACCOUNTS_FILE = "browser_use_accounts.json"
KEYS_FILE = "browser_use_keys.json"

# 请求配置
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2  # 单位：秒
# ===========================================

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

fake = Faker()  # Initialize Faker



def get_proxy_url():
    """获取代理URL"""
    proxy_url = "http://127.0.0.1:10808"
    return proxy_url

def generate_random_email() -> str:
    """生成随机邮箱"""
    # random_str = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    name_parts = [fake.first_name().lower(), fake.last_name().lower()]
    random.shuffle(name_parts)
    username = "".join(name_parts)
    if random.choice([True, False]):
        username += str(random.randint(1, 99))

    domains = ["gmail.com", "outlook.com"]
    domain = random.choice(domains)
    return f"{username}@{domain}"


def register_account(
    email: Optional[str] = None,
    password: str = "a123123123.",
    proxy: Optional[str] = None,
) -> Dict:
    """
    注册一个新账号

    参数:
        email: 可选，如果不提供则随机生成
        password: 密码，默认使用固定密码
        proxy: 代理URL

    返回:
        包含access_token, refresh_token, user_id的字典
    """
    if email is None:
        email = generate_random_email()

    payload = {
        "email": email,
        "password": password,
        "verification_callback_url": "https://cloud.browser-use.com/handler/email-verification?after_auth_return_to=%2Fhandler%2Fsign-in",
    }

    headers = {**COMMON_HEADERS, **STACK_AUTH_HEADERS}

    for attempt in range(MAX_RETRIES):
        try:
            client_kwargs: Dict[str, Any] = {}
            client_kwargs["timeout"] = REQUEST_TIMEOUT
            client_kwargs["verify"] = False  # Disable SSL verification
            if proxy:
                client_kwargs["proxy"] = proxy

            with httpx.Client(**client_kwargs) as client:
                response = client.post(REGISTER_URL, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()

                account_info = {
                    "email": email,
                    "password": password,
                    "access_token": result.get("access_token"),
                    "refresh_token": result.get("refresh_token"),
                    "user_id": result.get("user_id"),
                    "register_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

                save_account(account_info)

                logger.info(f"账号注册成功: {email}")
                return account_info

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP错误: {e.response.status_code} - {e.response.text}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"注册失败: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

    raise Exception(f"注册账号失败，已重试{MAX_RETRIES}次")


def create_order(
    access_token: str, amount: int = 10000, proxy: Optional[str] = None
) -> Dict:
    """
    创建订单

    参数:
        access_token: 认证令牌
        amount: 订单金额（单位：美分）
        proxy: 代理URL

    返回:
        包含checkout_url的字典
    """
    payload = {"amount": amount}

    headers = {**COMMON_HEADERS, "authorization": f"Bearer {access_token}"}
    headers["sec-fetch-site"] = "same-site"

    for attempt in range(MAX_RETRIES):
        try:
            client_kwargs: Dict[str, Any] = {}
            client_kwargs["timeout"] = REQUEST_TIMEOUT
            client_kwargs["verify"] = False  # Disable SSL verification
            if proxy:
                client_kwargs["proxy"] = proxy

            with httpx.Client(**client_kwargs) as client:
                response = client.post(CREATE_ORDER_URL, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()

                # 保存订单URL
                if "checkout_url" in result:
                    save_order_url(result["checkout_url"])
                    logger.info(f"订单创建成功，结算URL: {result['checkout_url']}")

                return result

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP错误: {e.response.status_code} - {e.response.text}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"创建订单失败: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

    raise Exception(f"创建订单失败，已重试{MAX_RETRIES}次")


def create_key(
    access_token: str, label: Optional[str] = None, proxy: Optional[str] = None
) -> Dict:
    """
    创建API密钥

    参数:
        access_token: 认证令牌
        label: 密钥标签，如果不提供则随机生成
        proxy: 代理URL

    返回:
        包含key信息的字典
    """
    if label is None:
        label = "".join(random.choices(string.ascii_lowercase, k=3))

    payload = {"label": label}

    headers = {**COMMON_HEADERS, "authorization": f"Bearer {access_token}"}
    headers["sec-fetch-site"] = "same-site"

    for attempt in range(MAX_RETRIES):
        try:
            client_kwargs: Dict[str, Any] = {}
            client_kwargs["timeout"] = REQUEST_TIMEOUT
            client_kwargs["verify"] = False  # Disable SSL verification
            if proxy:
                client_kwargs["proxy"] = proxy

            with httpx.Client(**client_kwargs) as client:
                response = client.post(CREATE_KEY_URL, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                api_key_value = result.get("key")

                if not api_key_value:
                    logger.error(f"API响应中未找到密钥 (label: {label})")
                    raise Exception("创建密钥后未从API响应中获取到key")

                key_info = {
                    "label": label,
                    "key": api_key_value,
                    "id": result.get("id"),
                    "created_at": result.get("created_at"),
                }

                logger.info(
                    f"密钥元数据准备成功 (label: {label}, key: {api_key_value[:8]}...)"
                )
                return key_info

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP错误: {e.response.status_code} - {e.response.text}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"创建密钥失败: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

    raise Exception(f"创建密钥失败，已重试{MAX_RETRIES}次")


def get_balance(api_key: str, proxy: Optional[str] = None) -> Dict:
    """
    获取账户余额

    参数:
        api_key: API密钥
        proxy: 代理URL

    返回:
        包含balance的字典
    """
    headers = {"Authorization": f"Bearer {api_key}"}

    for attempt in range(MAX_RETRIES):
        try:
            client_kwargs: Dict[str, Any] = {"timeout": REQUEST_TIMEOUT}
            client_kwargs["verify"] = False  # Disable SSL verification
            if proxy:
                client_kwargs["proxy"] = proxy

            with httpx.Client(**client_kwargs) as client:
                response = client.get(GET_BALANCE_URL, headers=headers)
                response.raise_for_status()
                result = response.json()

                logger.info(f"余额查询成功: {result.get('balance', 0)}")
                return result

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP错误: {e.response.status_code} - {e.response.text}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"获取余额失败: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

    raise Exception(f"获取余额失败，已重试{MAX_RETRIES}次")


def save_order_url(url: str) -> None:
    """保存订单URL到文件"""
    with open(ORDER_URLS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{url}\n")


def save_account(account_info: Dict) -> None:
    """保存账号信息到JSON文件"""
    # 创建一个线程锁，确保多线程环境下原子操作
    lock = threading.Lock()

    with lock:
        accounts = []

        # 读取现有账号
        if os.path.exists(ACCOUNTS_FILE):
            try:
                with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    accounts = json.load(f)
            except json.JSONDecodeError:
                accounts = []

        # 检查是否有重复的账号（避免并发时的重复添加）
        is_duplicate = False
        if "email" in account_info:
            for existing_account in accounts:
                if existing_account.get("email") == account_info["email"]:
                    is_duplicate = True
                    break

        # 只有不是重复的账号才添加
        if not is_duplicate:
            # 添加新账号
            accounts.append(account_info)

            # 写入文件
            with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                json.dump(accounts, f, ensure_ascii=False, indent=2)


def save_key(key_info: Dict) -> None:
    """保存密钥信息到JSON文件"""
    # 创建一个线程锁，确保多线程环境下原子操作
    lock = threading.Lock()

    with lock:
        keys = []

        # 读取现有密钥
        if os.path.exists(KEYS_FILE):
            try:
                with open(KEYS_FILE, "r", encoding="utf-8") as f:
                    keys = json.load(f)
            except json.JSONDecodeError:
                keys = []

        # 检查是否有重复的密钥（避免并发时的重复添加）
        is_duplicate = False
        if "key" in key_info:
            for existing_key in keys:
                if existing_key.get("key") == key_info["key"]:
                    is_duplicate = True
                    break

        # 只有不是重复的密钥才添加
        if not is_duplicate:
            # 添加新密钥
            keys.append(key_info)

            # 写入文件
            with open(KEYS_FILE, "w", encoding="utf-8") as f:
                json.dump(keys, f, ensure_ascii=False, indent=2)


def load_accounts() -> List[Dict]:
    """从文件加载账号信息"""
    if not os.path.exists(ACCOUNTS_FILE):
        return []

    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error(f"解析{ACCOUNTS_FILE}失败")
        return []


def load_keys() -> List[Dict]:
    """从文件加载密钥信息"""
    if not os.path.exists(KEYS_FILE):
        return []

    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error(f"解析{KEYS_FILE}失败")
        return []


def _register_and_create_order_worker(
    i: int, count: int, use_proxy: bool = False
) -> Dict:
    """
    注册账号并创建订单的工作函数 (供并发使用)

    参数:
        i: 当前处理的账号索引
        count: 总共要创建的账号数量
        use_proxy: 是否使用代理

    返回:
        包含处理结果的字典
    """
    try:
        logger.info(f"正在处理第{i + 1}/{count}个账号...")
        result = {"index": i, "success": False}

        proxy = None
        if use_proxy:
            try:
                proxy = get_proxy_url()
                logger.info(f"线程 {i + 1}: 使用代理: {proxy}")
            except Exception as e:
                logger.error(f"线程 {i + 1}: 获取代理失败: {e}")
                result["error"] = f"获取代理失败: {e}"
                return result

        # 注册账号
        register_result = register_account(proxy=proxy)
        access_token = register_result.get("access_token")

        if not access_token:
            logger.error(f"线程 {i + 1}: 注册成功但未获取到access_token，跳过创建订单")
            result["error"] = "注册成功但未获取到access_token"
            return result

        # 创建订单
        order_result = create_order(access_token, proxy=proxy)
        result["success"] = True
        result["register_result"] = register_result
        result["order_result"] = order_result
        logger.info(f"线程 {i + 1}: 第{i + 1}/{count}个账号处理完成")
        return result

    except Exception as e:
        logger.error(f"线程 {i + 1}: 处理第{i + 1}个账号时发生错误: {e}")
        return {"index": i, "success": False, "error": str(e)}


def mode_register_and_create_order(
    count: int = 1, use_proxy: bool = False, max_workers: int = 5
) -> None:
    """
    模式1：注册账号并创建订单 (并发版本)

    参数:
        count: 要创建的账号数量
        use_proxy: 是否使用代理
        max_workers: 最大并发数
    """
    logger.info(
        f"开始执行注册并创建订单，计划创建{count}个账号，最大并发数: {max_workers}"
    )

    actual_workers = min(max_workers, count)

    successful = 0
    failed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_workers) as executor:
        # 提交所有任务
        future_to_index = {
            executor.submit(_register_and_create_order_worker, i, count, use_proxy): i
            for i in range(count)
        }

        # 处理完成的任务
        for future in concurrent.futures.as_completed(future_to_index):
            i = future_to_index[future]
            try:
                result = future.result()
                if result["success"]:
                    successful += 1
                else:
                    failed += 1
                    logger.error(
                        f"第 {i + 1} 个账号处理失败: {result.get('error', '未知错误')}"
                    )
            except Exception as e:
                failed += 1
                logger.error(f"处理第 {i + 1} 个账号的任务发生异常: {e}")

    logger.info(
        f"注册并创建订单完成，成功: {successful}，失败: {failed}，总计: {count}"
    )
    logger.info(f"订单URL已保存到: {ORDER_URLS_FILE}")
    logger.info(f"账号信息已保存到: {ACCOUNTS_FILE}")


def _process_account_worker(
    account: Dict, existing_key_emails: set, use_proxy: bool = False
) -> Dict:
    """
    处理单个账户的工作函数

    参数:
        account: 要处理的账户信息
        existing_key_emails: 已存在密钥的邮箱集合
        use_proxy: 是否使用代理

    返回:
        包含处理结果的字典
    """
    account_email = account.get("email")
    access_token = account.get("access_token")
    result = {
        "email": account_email,
        "success": False,
    }

    logger.info(f"正在处理账户: {account_email or '未知邮箱'}")

    # 检查是否有access_token
    if not access_token:
        logger.warning(f"账户 {account_email or '未知邮箱'} 缺少access_token，跳过。")
        result["error"] = "missing_access_token"
        return result

    # 检查邮箱是否已有密钥
    if account_email and account_email in existing_key_emails:
        logger.info(f"账户 {account_email} 的密钥已存在，跳过。")
        result["error"] = "key_already_exists"
        return result

    # 获取代理
    proxy = None
    if use_proxy:
        try:
            proxy = get_proxy_url()
            logger.info(f"账户 {account_email or '未知邮箱'}: 使用代理: {proxy}")
        except Exception as e:
            logger.error(f"账户 {account_email or '未知邮箱'}: 获取代理失败: {e}")
            result["error"] = f"获取代理失败: {e}"
            return result

    try:
        # 创建密钥
        logger.info(f"正在为账户 {account_email or '未知邮箱'} 准备API密钥元数据...")
        key_details = create_key(access_token, proxy=proxy)
        api_key = key_details.get("key")

        if not api_key:
            logger.error(
                f"为账户 {account_email or '未知邮箱'} 创建密钥失败，未从API获取到密钥。"
            )
            result["error"] = "failed_to_create_key"
            return result

        # 查询余额
        logger.info(
            f"正在为账户 {account_email or '未知邮箱'} 查询余额 (API Key: {api_key[:8]}...)."
        )
        balance_result = get_balance(api_key, proxy=proxy)
        current_balance = balance_result.get("balance", 0)

        key_details["balance"] = current_balance
        if account_email:
            key_details["email"] = account_email

        save_key(key_details)

        logger.info(
            f"账户 {account_email or '未知邮箱'} 处理成功: API密钥 {key_details.get('key')} (标签: {key_details.get('label')}) 已创建并保存, 余额: {current_balance}"
        )

        result["success"] = True
        result["key_details"] = key_details
        result["balance"] = current_balance
        return result

    except Exception as e:
        logger.error(f"处理账户 {account_email or '未知邮箱'} 时发生错误: {e}")
        result["error"] = str(e)
        return result


def mode_process_registered_accounts(
    use_proxy: bool = False, max_workers: int = 5
) -> None:
    """
    模式3：处理已注册的账户，为它们创建密钥并查询余额 (并发版本)

    参数:
        use_proxy: 是否使用代理
        max_workers: 最大并发数
    """
    logger.info(f"开始执行处理已注册账户模式 (并发数: {max_workers})...")
    accounts = load_accounts()

    if not accounts:
        logger.warning(f"在 {ACCOUNTS_FILE} 中未找到任何账户信息。")
        return

    existing_keys = load_keys()
    existing_key_emails = {
        key.get("email") for key in existing_keys if key.get("email")
    }
    logger.info(
        f"已加载 {len(existing_keys)} 个现有密钥，其中 {len(existing_key_emails)} 个有关联邮箱。"
    )

    actual_workers = min(max_workers, len(accounts))

    successful = 0
    failed = 0
    skipped = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_workers) as executor:
        # 提交所有任务
        future_to_account = {
            executor.submit(
                _process_account_worker, account, existing_key_emails, use_proxy
            ): account
            for account in accounts
        }

        # 处理完成的任务
        for future in concurrent.futures.as_completed(future_to_account):
            account = future_to_account[future]
            account_email = account.get("email", "未知邮箱")

            try:
                result = future.result()
                if result["success"]:
                    successful += 1
                elif result.get("error") in [
                    "key_already_exists",
                    "missing_access_token",
                ]:
                    skipped += 1
                else:
                    failed += 1
                    logger.error(
                        f"账户 {account_email} 处理失败: {result.get('error', '未知错误')}"
                    )
            except Exception as e:
                failed += 1
                logger.error(f"处理账户 {account_email} 的任务发生异常: {e}")

    logger.info(
        f"处理已注册账户模式完成。成功: {successful}, 失败: {failed}, 跳过: {skipped}, 总计: {len(accounts)}"
    )
    logger.info(f"密钥信息已更新到: {KEYS_FILE}")


def mode_create_key_and_check_balance(
    email: Optional[str] = None,
    password: Optional[str] = None,
    access_token: Optional[str] = None,
    use_proxy: bool = False,
    max_workers: int = 5,
) -> Tuple[Dict, Any]:
    """
    模式2：创建密钥并检查余额

    参数:
        email: 账号邮箱，如果提供则使用此邮箱进行登录
        password: 账号密码
        access_token: 如果已有access_token则直接使用
        use_proxy: 是否使用代理
        max_workers: 最大并发数（当批量处理多个账户时使用）

    返回:
        (密钥信息, 余额信息)的元组
    """
    proxy = None
    if use_proxy:
        try:
            proxy = get_proxy_url()
            logger.info(f"使用代理: {proxy}")
        except Exception as e:
            logger.error(f"获取代理失败: {e}")

    email_for_key_association = email  # email from -e argument
    # 如果没有提供access_token，则注册新账号
    if not access_token:
        if not email_for_key_association:  # If -e was not used
            logger.info("未提供邮箱和访问令牌，将注册新账号 (邮箱随机生成)")
            # register_account will generate an email if None is passed
        else:
            logger.info(f"使用邮箱 {email_for_key_association} 尝试注册或登录逻辑")

        # 确保密码是字符串
        actual_password = password if password is not None else "a123123123."

        # register_account 现在返回 account_info，包含所使用的email
        register_result_info = register_account(
            email=email_for_key_association, password=actual_password, proxy=proxy
        )
        access_token = register_result_info.get("access_token")
        email_for_key_association = register_result_info.get(
            "email"
        )  # 更新为实际使用的email

        if not access_token:
            raise Exception("未获取到访问令牌，无法继续")
        logger.info(
            f"账号操作完成，邮箱: {email_for_key_association}, Access Token: {access_token[:8]}..."
        )

    # 创建密钥（但不立即保存）
    logger.info("正在准备API密钥元数据...")
    key_details = create_key(access_token, proxy=proxy)  # create_key现在返回key_info
    api_key = key_details.get("key")

    if not api_key:
        raise Exception("创建密钥失败，未获取到API密钥")

    # 查询余额
    logger.info(f"正在查询账户余额 (API Key: {api_key[:8]}...).")
    balance_result = get_balance(api_key, proxy=proxy)
    current_balance = balance_result.get("balance", 0)

    key_details["balance"] = current_balance
    if email_for_key_association:
        key_details["email"] = email_for_key_association

    save_key(key_details)

    logger.info(
        f"API密钥创建并保存成功: {api_key} (邮箱: {email_for_key_association or '未关联'}), 余额: {current_balance}"
    )
    logger.info(f"密钥信息 (含余额和邮箱) 已保存到: {KEYS_FILE}")

    return key_details, balance_result  # key_details 现在包含余额和邮箱


def main():
    parser = argparse.ArgumentParser(description="Browser Use API自动化工具")

    subparsers = parser.add_subparsers(dest="mode", help="操作模式")

    # 模式1：注册账号并创建订单
    register_parser = subparsers.add_parser("register", help="注册账号并创建订单")
    register_parser.add_argument(
        "-c", "--count", type=int, default=1, help="要创建的账号数量，默认为1"
    )
    register_parser.add_argument("--proxy", action="store_true", help="使用代理")
    register_parser.add_argument(
        "--max-workers", type=int, default=5, help="最大并发数，默认为5"
    )

    # 模式2：创建密钥并查询余额
    key_parser = subparsers.add_parser("key", help="创建API密钥并查询余额")
    key_parser.add_argument("-e", "--email", help="账号邮箱，如不提供则注册新账号")
    key_parser.add_argument(
        "-p",
        "--password",
        default="123123123.",
        help="账号密码，默认为123123123.",
    )
    key_parser.add_argument("-t", "--token", help="如已有access_token，可直接提供")
    key_parser.add_argument("--proxy", action="store_true", help="使用代理")
    key_parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        help="最大并发数，默认为5（批量处理时有效）",
    )

    # 模式3：处理来自 register 模式的账户
    process_accounts_parser = subparsers.add_parser(
        "process_accounts", help="处理已注册的账户，创建密钥并查询余额"
    )
    process_accounts_parser.add_argument(
        "--proxy", action="store_true", help="为每个账户操作使用代理"
    )
    process_accounts_parser.add_argument(
        "--max-workers", type=int, default=5, help="最大并发数，默认为5"
    )

    args = parser.parse_args()
    args.mode = "process_accounts"
    args.count = 30
    args.proxy = True
    args.max_workers = 1

    if args.mode == "register":
        """
        注册账号并创建订单
        """
        mode_register_and_create_order(
            count=args.count, use_proxy=args.proxy, max_workers=args.max_workers
        )
    elif args.mode == "key":
        """
        创建密钥并查询余额
        """
        mode_create_key_and_check_balance(
            email=args.email,
            password=args.password,
            access_token=args.token,
            use_proxy=args.proxy,
            max_workers=args.max_workers,
        )
    elif args.mode == "process_accounts":
        """
        处理已注册的账户，创建密钥并查询余额
        """
        mode_process_registered_accounts(
            use_proxy=args.proxy, max_workers=args.max_workers
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
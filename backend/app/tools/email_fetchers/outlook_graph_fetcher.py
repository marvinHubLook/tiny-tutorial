import logging
import requests
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
import base64
import json
import time
import os

from .base_fetcher import AbstractEmailFetcher, EmailMessage, Attachment
from app.utils.logger import getLogger

logger = getLogger(__name__)

# Microsoft Graph API 端点
GRAPH_API_ENDPOINT = 'https://graph.microsoft.com/v1.0'

# 身份验证 API 端点
AUTH_ENDPOINTS = {
    "tenant": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
    "personal": "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
}


class OutlookGraphAPIFetcher(AbstractEmailFetcher):
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Outlook Graph API 邮件获取器

        参数:
            config: 配置字典，包含以下可能的键:
                - client_id: 应用程序ID（必需）
                - account_email: 账户电子邮件地址
                - user_principal_name: 用户主体名称，如果与 account_email 不同
                - tenant_id: 租户ID（组织模式需要）
                - client_secret: 客户端密钥（组织模式需要）
                - username: 用户名（个人模式）
                - password: 密码（个人模式）
                - access_token: 预先获取的访问令牌（可选）
                - proxy: 代理设置，例如 "http://127.0.0.1:7890"
                - scopes: API 权限范围
        """
        super().__init__(config)
        # 共享配置
        self.client_id = config.get("client_id")
        self.user_principal_name = config.get("user_principal_name", self.account_email)

        # 租户模式配置 (应用权限)
        self.tenant_id = config.get("tenant_id")
        self.client_secret = config.get("client_secret")

        # 个人账户配置 (委派权限)
        self.username = config.get("username", self.account_email)
        self.password = config.get("password")
        self.provided_token = config.get("access_token")
        self.refresh_token = config.get("refresh_token")  # 添加刷新令牌

        self.token_cache_file = config.get("token_cache_file")

        # 代理设置
        self.proxy = config.get("proxy")
        self.proxies = None
        if self.proxy:
            self.proxies = {
                "http": self.proxy,
                "https": self.proxy
            }
            logger.info(f"已配置代理: {self.proxy}")

        # 初始化其他属性
        self.access_token = None
        self.token_expires_at = 0  # 令牌过期时间戳

        # 根据参数判断认证模式
        if self.client_secret and self.tenant_id:
            self.auth_mode = "tenant"
            self.authority = AUTH_ENDPOINTS["tenant"].format(tenant_id=self.tenant_id)
            self.scopes = config.get("scopes", ["https://graph.microsoft.com/.default"])
        else:
            self.auth_mode = "personal"
            self.authority = AUTH_ENDPOINTS["personal"]
            self.scopes = config.get("scopes", ["Mail.Read", "Mail.ReadWrite"])

        # 尝试从缓存文件加载令牌
        self._load_token_from_cache()

        logger.info(f"初始化 OutlookGraphAPIFetcher，认证模式: {self.auth_mode}")

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

    def _refresh_access_token(self):
        """
        使用刷新令牌获取新的访问令牌

        返回:
            bool: 刷新是否成功
        """
        if not self.refresh_token:
            logger.warning("没有可用的刷新令牌")
            return False

        logger.info(f"正在使用刷新令牌获取新的访问令牌，用户: {self.username}")

        # 准备请求数据
        data = {
            'client_id': self.client_id,
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'scope': ' '.join(self.scopes)
        }

        # 如果是租户模式且有客户端密钥，则添加
        if self.auth_mode == "tenant" and self.client_secret:
            data['client_secret'] = self.client_secret

        try:
            # 发送刷新令牌请求
            response = requests.post(
                self.authority,
                data=data,
                proxies=self.proxies
            )

            if response.status_code == 200:
                result = response.json()
                self.access_token = result['access_token']

                # 如果响应中包含新的刷新令牌，则更新它
                if 'refresh_token' in result:
                    self.refresh_token = result['refresh_token']

                # 计算令牌过期时间（留出30秒安全边界）
                self.token_expires_at = time.time() + result.get('expires_in', 3600) - 30

                # 保存到缓存
                self._save_token_to_cache()

                logger.info(f"成功使用刷新令牌获取新的访问令牌，用户: {self.username}")
                return True
            else:
                logger.warning(f"刷新令牌请求失败: {response.status_code} - {response.text}")
                # 刷新令牌可能已失效
                self.refresh_token = None
                return False

        except Exception as e:
            logger.warning(f"刷新令牌请求异常: {str(e)}")
            return False

    def _get_tenant_token(self):
        """
        使用客户端密钥获取应用级令牌(应用权限)

        返回:
            str: 访问令牌
        """
        logger.info(f"正在为租户 {self.tenant_id} 获取新的应用级令牌...")

        # 准备请求数据
        data = {
            'client_id': self.client_id,
            'scope': ' '.join(self.scopes),
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials'
        }

        # 发送令牌请求
        try:
            response = requests.post(
                self.authority,
                data=data,
                proxies=self.proxies
            )
            response.raise_for_status()
            result = response.json()

            if "access_token" in result:
                self.access_token = result['access_token']
                # 计算token过期时间（留出30秒安全边界）
                self.token_expires_at = time.time() + result.get('expires_in', 3600) - 30
                logger.info(f"成功获取应用级令牌，client_id: {self.client_id}")
                return self.access_token
            else:
                error_msg = f"获取应用级令牌失败: {result.get('error_description')}"
                logger.error(error_msg)
                raise ConnectionError(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"获取应用级令牌请求失败: {str(e)}"
            logger.error(error_msg)
            raise ConnectionError(error_msg)

    def _get_personal_token(self):
        """
        使用用户名密码或其他方式获取用户级令牌(委派权限)

        返回:
            str: 访问令牌
        """
        # 首先尝试使用刷新令牌
        if self.refresh_token:
            if self._refresh_access_token():
                return self.access_token
            else:
                logger.info("刷新令牌无效或已过期，将尝试其他认证方式")

        logger.info(f"正在为用户 {self.username} 获取新的用户级令牌...")

        # 如果提供了用户名和密码，使用密码授权模式
        if self.password:
            # 准备请求数据
            data = {
                'client_id': self.client_id,
                'scope': ' '.join(self.scopes),
                'username': self.username,
                'password': self.password,
                'grant_type': 'password'
            }

            try:
                logger.info(f"正在使用用户名/密码授权获取令牌...")
                response = requests.post(
                    self.authority,
                    data=data,
                    proxies=self.proxies
                )

                # 检查响应
                if response.status_code == 200:
                    result = response.json()
                    self.access_token = result['access_token']

                    # 保存刷新令牌（如果有）
                    if 'refresh_token' in result:
                        self.refresh_token = result['refresh_token']
                        logger.info("已获取刷新令牌")

                    # 计算token过期时间（留出30秒安全边界）
                    self.token_expires_at = time.time() + result.get('expires_in', 3600) - 30

                    # 保存到缓存
                    self._save_token_to_cache()

                    logger.info(f"成功获取用户级令牌，用户: {self.username}")
                    return self.access_token
                else:
                    error_data = response.json()
                    logger.warning(
                        f"用户名/密码授权失败: {error_data.get('error')}: {error_data.get('error_description')}")

                    # 如果是个人账户，密码授权可能不支持，需要使用设备码流程
                    if "AADSTS50126" in response.text or "wstrust" in response.text.lower():
                        logger.warning("Microsoft 个人账户不支持用户名/密码认证，将使用设备码流程。")
                    else:
                        logger.warning(f"用户名/密码认证错误: {response.text}")
            except requests.exceptions.RequestException as e:
                logger.warning(f"用户名/密码授权请求失败: {str(e)}")

        # 如果没有密码或者密码授权失败，使用设备码流程
        logger.info("开始设备码流程认证...")
        try:
            # 1. 初始化设备码流程
            device_code_data = {
                'client_id': self.client_id,
                'scope': ' '.join(self.scopes)
            }

            device_code_response = requests.post(
                f"https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode",
                data=device_code_data,
                proxies=self.proxies
            )
            device_code_response.raise_for_status()
            flow = device_code_response.json()

            if "user_code" not in flow:
                error_msg = f"无法启动设备码流程: {flow.get('error_description')}"
                logger.error(error_msg)
                raise ConnectionError(error_msg)

            # 2. 向用户显示设备码及验证网址
            print(flow["message"])
            logger.info(f"设备码流程消息: {flow['message']}")

            # 3. 轮询令牌终结点
            device_code = flow["device_code"]
            interval = flow.get("interval", 5)
            expires_in = flow.get("expires_in", 900)
            end_time = time.time() + expires_in

            token_request_data = {
                'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
                'device_code': device_code,
                'client_id': self.client_id
            }

            # 循环等待用户完成验证
            while time.time() < end_time:
                time.sleep(interval)

                token_response = requests.post(
                    self.authority,
                    data=token_request_data,
                    proxies=self.proxies
                )

                if token_response.status_code == 200:
                    result = token_response.json()
                    self.access_token = result['access_token']

                    # 保存刷新令牌（如果有）
                    if 'refresh_token' in result:
                        self.refresh_token = result['refresh_token']
                        logger.info("已获取刷新令牌")

                    # 计算token过期时间（留出30秒安全边界）
                    self.token_expires_at = time.time() + result.get('expires_in', 3600) - 30

                    # 保存到缓存
                    self._save_token_to_cache()

                    logger.info(f"成功通过设备码流程获取令牌，用户: {self.username}")
                    return self.access_token

                # 如果仍在等待用户验证
                result = token_response.json()
                if result.get("error") == "authorization_pending":
                    logger.info("等待用户完成验证...")
                    continue
                elif result.get("error") == "slow_down":
                    # 增加轮询间隔
                    interval += 5
                    logger.info(f"收到 slow_down 响应，增加轮询间隔至 {interval}秒")
                    continue
                elif result.get("error") == "expired_token":
                    error_msg = "设备码已过期，验证超时"
                    logger.error(error_msg)
                    raise ConnectionError(error_msg)
                else:
                    error_msg = f"设备码验证失败: {result.get('error_description')}"
                    logger.error(error_msg)
                    raise ConnectionError(error_msg)

            error_msg = "设备码验证超时"
            logger.error(error_msg)
            raise ConnectionError(error_msg)

        except requests.exceptions.RequestException as e:
            error_msg = f"设备码流程请求失败: {str(e)}"
            logger.error(error_msg)
            raise ConnectionError(error_msg)

    def connect(self) -> None:
        """
        连接到 Microsoft Graph API 并获取访问令牌
        """
        try:
            # 检查是否已有有效的访问令牌
            if self.access_token and time.time() < self.token_expires_at:
                logger.info("使用现有的有效访问令牌")
                return

            # 首先检查是否已提供访问令牌
            if self.provided_token:
                self.access_token = self.provided_token
                # 设置一个较长的过期时间，因为我们无法知道提供的令牌何时过期
                self.token_expires_at = time.time() + 3600  # 假设有效期为1小时
                logger.info(f"使用提供的访问令牌")
                return

            # 如果有刷新令牌，尝试使用它获取新的访问令牌
            if self.refresh_token and self.auth_mode == "personal":
                if self._refresh_access_token():
                    return
                else:
                    logger.info("刷新令牌无效或已过期")

            # 否则根据认证模式获取新令牌
            if self.auth_mode == "tenant":
                self._get_tenant_token()
            else:  # personal mode
                self._get_personal_token()

        except Exception as e:
            logger.error(f"Outlook Graph API: 连接失败: {e}")
            raise

    def _make_graph_api_call(self, method, url_suffix, params=None, json_data=None, headers=None):
        """
        发送请求到 Microsoft Graph API

        参数:
            method: HTTP 方法 (GET, POST, PATCH, DELETE 等)
            url_suffix: API 端点的后缀部分
            params: URL 查询参数
            json_data: 要发送的 JSON 数据
            headers: 额外的 HTTP 头

        返回:
            dict: API 响应的 JSON 数据
        """
        # 检查令牌是否存在或已过期
        if not self.access_token or time.time() >= self.token_expires_at:
            self.connect()

        # 准备请求头
        req_headers = {
            'Authorization': 'Bearer ' + self.access_token,
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        if headers:
            req_headers.update(headers)

        full_url = f"{GRAPH_API_ENDPOINT}{url_suffix}"
        try:
            # 发送请求
            response = requests.request(
                method,
                full_url,
                headers=req_headers,
                params=params,
                json=json_data,
                proxies=self.proxies
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(
                f"Outlook Graph API: HTTP 错误 {method} {full_url}: {e.response.status_code} - {e.response.text}")
            if e.response.status_code == 401:  # 未授权，令牌可能已过期
                if not self.provided_token:  # 如果不是使用提供的固定令牌
                    logger.info("Outlook Graph API: 令牌可能已过期，尝试重新获取。")
                    self.access_token = None  # 强制下次调用重新获取
                    self.token_expires_at = 0
                else:
                    logger.error("Outlook Graph API: 提供的令牌无效或已过期。")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Outlook Graph API: 请求异常 {method} {full_url}: {e}")
            raise

    def fetch_emails(self, criteria: Optional[Dict[str, Any]] = None) -> List[EmailMessage]:
        """
        根据给定的条件获取邮件

        参数:
            criteria: 过滤条件，可以包含以下键:
                - graph_filter_string: Graph API 过滤字符串
                - since_date: 日期时间对象，获取此日期之后的邮件
                - limit: 最大返回邮件数量

        返回:
            List[EmailMessage]: 获取到的邮件列表
        """
        # 确保有访问令牌
        if not self.access_token or time.time() >= self.token_expires_at:
            self.connect()

        fetched_emails: List[EmailMessage] = []

        # 构建过滤条件
        filter_query = "isRead eq false"  # 默认获取未读邮件
        if criteria and "graph_filter_string" in criteria:
            filter_query = criteria["graph_filter_string"]
        elif criteria and "since_date" in criteria:  # datetime 对象
            # 确保日期时间是 ISO 8601 格式的 UTC 时间
            dt_utc = criteria["since_date"].astimezone(timezone.utc)
            date_str = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            filter_query = f"isRead eq false and receivedDateTime ge {date_str}"

        # 选择需要返回的字段
        select_fields = "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments"
        expand_fields = "attachments($select=name,contentType)"  # 注意: contentBytes 只适用于小型附件

        # 根据认证模式选择合适的 API 端点
        if self.auth_mode == "tenant":
            # 应用权限模式 - 需要指定用户
            url_suffix = f"/users/{self.user_principal_name}/messages"
        else:
            # 委派权限模式 - 使用当前用户上下文
            url_suffix = "/me/messages"

        # 准备请求参数
        params = {
            "$filter": filter_query,
            "$select": select_fields,
            "$expand": expand_fields,  # 注意: 如果附件很多或很大，直接展开可能会有问题
            "$top": str(criteria.get("limit", 25)) if criteria else "25"  # 限制结果数量
        }

        logger.debug(f"Outlook Graph API: 获取邮件，参数: {params}")

        try:
            # 发送请求
            response_data = self._make_graph_api_call("GET", url_suffix, params=params)
            graph_messages = response_data.get('value', [])

            if not graph_messages:
                logger.info(f"Outlook Graph API: 未找到符合过滤条件 '{filter_query}' 的邮件")
                return []

            logger.info(f"Outlook Graph API: 找到 {len(graph_messages)} 封符合条件的邮件。")

            # 处理每封邮件
            for msg_data in graph_messages:
                email_id = msg_data.get('id')
                message_id_header = msg_data.get('messageId')  # 这是实际的 Message-ID 头
                subject = msg_data.get('subject')

                # 处理发件人
                sender_obj = msg_data.get('from', {}).get('emailAddress', {})
                sender = f"{sender_obj.get('name', '')} <{sender_obj.get('address', '')}>".strip()

                # 处理收件人
                to_recipients = [
                    f"{r.get('emailAddress', {}).get('name', '')} <{r.get('emailAddress', {}).get('address', '')}>".strip()
                    for r in msg_data.get('toRecipients', [])]
                cc_recipients = [
                    f"{r.get('emailAddress', {}).get('name', '')} <{r.get('emailAddress', {}).get('address', '')}>".strip()
                    for r in msg_data.get('ccRecipients', [])]

                # 处理邮件正文
                body_obj = msg_data.get('body', {})
                body_content = body_obj.get('content', '')
                body_type = body_obj.get('contentType', 'text').lower()  # 'text' 或 'html'
                body_text = body_content if body_type == 'text' else None
                body_html = body_content if body_type == 'html' else None

                # 处理接收日期
                received_dt_str = msg_data.get('receivedDateTime')
                received_dt = datetime.fromisoformat(
                    received_dt_str.replace('Z', '+00:00')) if received_dt_str else None

                # 处理附件
                attachments_list = []
                if msg_data.get('hasAttachments'):
                    # 如果附件已被展开且足够小:
                    for att_data in msg_data.get('attachments', []):
                        if 'contentBytes' in att_data:  # 只有当返回了 contentBytes 时
                            attachments_list.append(
                                Attachment(
                                    filename=att_data.get('name'),
                                    content_type=att_data.get('contentType'),
                                    data=base64.b64decode(att_data['contentBytes'])
                                )
                            )
                        # 否则，如果 'contentBytes' 不存在，你需要为每个附件进行额外的 API 调用:
                        # GET /users/{id|userPrincipalName}/messages/{message_id}/attachments/{attachment_id}
                        # 此示例假设附件足够小，可以直接展开。

                # 创建 EmailMessage 对象并添加到列表
                fetched_emails.append(
                    EmailMessage(
                        id=email_id,
                        message_id_header=message_id_header,
                        subject=subject,
                        sender=sender,
                        recipients_to=to_recipients,
                        recipients_cc=cc_recipients,
                        body_text=body_text,
                        body_html=body_html,
                        received_date=received_dt,
                        attachments=attachments_list,
                        raw=msg_data,
                        provider_type="outlook_graph",
                        account_email=self.account_email
                    )
                )
            return fetched_emails

        except Exception as e:
            logger.error(f"Outlook Graph API: 获取邮件时出错，用户: {self.user_principal_name}: {e}")
            raise

    def mark_as_read(self, email_ids: List[str]) -> None:
        """
        将指定的邮件标记为已读

        参数:
            email_ids: 要标记为已读的邮件 ID 列表
        """
        # 确保有访问令牌
        if not self.access_token or time.time() >= self.token_expires_at:
            self.connect()

        if not email_ids:
            return

        # Graph API 可以批量处理请求，但为简单起见，逐个更新
        # 如需实现批处理: https://docs.microsoft.com/en-us/graph/json-batching
        for email_id in email_ids:
            # 根据认证模式选择合适的 API 端点
            if self.auth_mode == "tenant":
                url_suffix = f"/users/{self.user_principal_name}/messages/{email_id}"
            else:
                url_suffix = f"/me/messages/{email_id}"

            patch_data = {"isRead": True}
            try:
                logger.info(f"Outlook Graph API: 将邮件 {email_id} 标记为已读。")
                self._make_graph_api_call("PATCH", url_suffix, json_data=patch_data)
            except Exception as e:
                logger.error(f"Outlook Graph API: 标记邮件 {email_id} 为已读时出错: {e}")

    def disconnect(self) -> None:
        """
        断开连接，清除当前会话的认证状态
        """
        # 清除内存中的令牌相当于"断开"当前会话的认证状态
        self.access_token = None
        self.token_expires_at = 0
        logger.info(f"Outlook Graph API: '已断开连接'(令牌已清除)，用户: {self.user_principal_name}")
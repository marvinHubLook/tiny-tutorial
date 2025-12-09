import requests
import base64
import json
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse, parse_qs, unquote
from tqdm import tqdm
import yaml

from app.utils.logger import getLogger

logger = getLogger(__name__)

PROTOCOL = "socks"  # 本地代理协议: "socks" (SOCKS5) 或 "http"
LISTEN_ADDRESS = "127.0.0.1"  # 本地代理监听地址


class SubscriptionConverter:
    def __init__(self, start_port: int = 10000):
        # NEW: Added 'hysteria2' to supported protocols
        self.supported_protocols = ['vmess', 'trojan', 'ss', 'ssr', 'vless', 'hysteria2']
        # FIX: Removed unused self.port_mappings
        self.start_port = start_port

    def fetch_subscription(self, url: str) -> str:
        """获取订阅内容"""
        try:
            headers = {
                'User-Agent': 'Clash/2023.08.17'  # ENHANCEMENT: Using a common client User-Agent
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # 尝试base64解码
            try:
                content = base64.b64decode(response.text).decode('utf-8')
            except (ValueError, TypeError):
                content = response.text

            return content
        except Exception as e:
            print(f"获取订阅失败: {e}")
            return ""

    # --- 辅助函数 ---
    def safe_base64_decode(self, data: str) -> Optional[str]:
        """尝试Base64解码，处理可能的URL安全变体和填充问题"""
        data = data.replace('-', '+').replace('_', '/')  # URL safe to standard
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        try:
            return base64.b64decode(data).decode('utf-8')
        except Exception:
            return None

    def parse_vmess_url(self, vmess_url_str: str) -> Optional[Dict[str, Any]]:
        """解析VMess订阅链接"""
        try:
            base64_encoded_config = vmess_url_str[len("vmess://"):]
            decoded_json_str = self.safe_base64_decode(base64_encoded_config)
            if not decoded_json_str:
                raise ValueError("Base64解码失败或内容无效")

            config = json.loads(decoded_json_str)

            server = config.get('add')
            port = config.get('port')
            uuid = config.get('id')
            node_name = unquote(config.get('ps', f"{server}:{port}"))

            if not all([server, port, uuid]):
                raise ValueError("VMess链接缺少必要参数 (add, port, id)")

            return {
                "type": "vmess",
                "name": node_name,
                "server": server,
                "port": int(port),
                "uuid": uuid,
                "alter_id": int(config.get('aid', 0)),
                "cipher": config.get('scy', 'auto'),
                "network": config.get('net', 'tcp'),
                "tls": config.get('tls', '') == 'tls',
                "host": config.get('host', ''),
                "path": config.get('path', '/'),
                "sni": config.get('sni', '') or server,
                "alpn": config.get('alpn', '').split(',') if config.get('alpn') else [],
                "fingerprint": config.get('fp', ''),
                "allow_insecure": config.get('allowInsecure', '0') == '1' or config.get('skip-cert-verify', False),
                "service_name": config.get('servicename', ''),
            }
        except Exception as e:
            print(f"解析VMess链接失败: {vmess_url_str} - 错误: {e}")
            return None

    def parse_trojan_url(self, trojan_url_str: str) -> Optional[Dict[str, Any]]:
        """解析Trojan订阅链接"""
        try:
            parsed_url = urlparse(trojan_url_str)
            password = parsed_url.username
            server = parsed_url.hostname
            port = parsed_url.port
            node_name = unquote(parsed_url.fragment) if parsed_url.fragment else f"{server}:{port}"

            if not all([password, server, port]):
                raise ValueError("Trojan链接缺少必要参数 (password, server, port)")

            # ENHANCEMENT: Safer query param access
            query_params = parse_qs(parsed_url.query)
            sni = query_params.get('sni', [server])[0]
            fingerprint = query_params.get('fp', [''])[0]
            allow_insecure = query_params.get('allowInsecure', ['0'])[0] == '1' or \
                             query_params.get('skip-cert-verify', ['false'])[0] == 'true'
            alpn_str = query_params.get('alpn', [''])[0]
            alpn = alpn_str.split(',') if alpn_str else []

            return {
                "type": "trojan",
                "name": node_name,
                "password": password,
                "server": server,
                "port": int(port),
                "sni": sni,
                "fingerprint": fingerprint,
                "allow_insecure": allow_insecure,
                "alpn": alpn
            }
        except Exception as e:
            print(f"解析Trojan链接失败: {trojan_url_str} - 错误: {e}")
            return None

    # ENHANCEMENT: Rewritten for clarity and robustness
    def parse_ss_url(self, ss_url_str: str) -> Optional[Dict[str, Any]]:
        """解析Shadowsocks订阅链接 (支持多种格式)"""
        try:
            if '@' not in ss_url_str:
                # Format: ss://base64(method:password@server:port)#name
                encoded_part = ss_url_str[len("ss://"):].split('#')[0]
                decoded_info = self.safe_base64_decode(encoded_part)
                if not decoded_info:
                    raise ValueError("Base64解码失败")
                # Reconstruct a standard URL to parse
                ss_url_str = f"ss://{decoded_info}{'#' + ss_url_str.split('#')[1] if '#' in ss_url_str else ''}"

            parsed_url = urlparse(ss_url_str)
            server = parsed_url.hostname
            port = parsed_url.port
            node_name = unquote(parsed_url.fragment) if parsed_url.fragment else f"{server}:{port}"

            # Format: ss://method:password@server:port#name
            # Or from the decoded part above
            user_info = unquote(parsed_url.username or '')
            password = unquote(parsed_url.password or '')

            if ':' in user_info and not password:  # method:pass is in username field
                method, password = user_info.split(':', 1)
            else:  # method is in username, password is in password
                method = user_info

            if not all([method, password, server, port]):
                raise ValueError("Shadowsocks链接缺少必要参数 (method, password, server, port)")

            return {
                "type": "ss",
                "name": node_name,
                "method": method,
                "password": password,
                "server": server,
                "port": int(port)
            }
        except Exception as e:
            print(f"解析Shadowsocks链接失败: {ss_url_str} - 错误: {e}")
            return None

    def parse_vless_url(self, vless_url_str: str) -> Optional[Dict[str, Any]]:
        """解析VLESS订阅链接"""
        try:
            parsed_url = urlparse(vless_url_str)
            uuid = parsed_url.username
            server = parsed_url.hostname
            port = parsed_url.port
            node_name = unquote(parsed_url.fragment) if parsed_url.fragment else f"{server}:{port}"

            if not all([uuid, server, port]):
                raise ValueError("VLESS链接缺少必要参数 (uuid, server, port)")

            # ENHANCEMENT: Safer query param access
            query_params = parse_qs(parsed_url.query)
            network = query_params.get('type', ['tcp'])[0]
            security = query_params.get('security', ['none'])[0]
            flow = query_params.get('flow', [''])[0]
            sni = query_params.get('sni', [server])[0]
            fingerprint = query_params.get('fp', [''])[0]
            alpn_str = query_params.get('alpn', [''])[0]
            alpn = alpn_str.split(',') if alpn_str else []
            allow_insecure = query_params.get('allowInsecure', ['0'])[0] == '1'
            public_key = query_params.get('pbk', [''])[0]
            short_id = query_params.get('sid', [''])[0]
            spider_x = query_params.get('spx', [''])[0]
            path = query_params.get('path', ['/'])[0]
            host = query_params.get('host', [server])[0]
            service_name = query_params.get('serviceName', [''])[0]  # Corrected key from 'servicename'

            return {
                "type": "vless",
                "name": node_name,
                "uuid": uuid,
                "server": server,
                "port": int(port),
                "network": network,
                "security": security,
                "flow": flow,
                "sni": sni,
                "fingerprint": fingerprint,
                "alpn": alpn,
                "allow_insecure": allow_insecure,
                "public_key": public_key,
                "short_id": short_id,
                "spider_x": spider_x,
                "path": path,
                "host": host,
                "service_name": service_name,
            }
        except Exception as e:
            print(f"解析VLESS链接失败: {vless_url_str} - 错误: {e}")
            return None

    # NEW: Hysteria2 parser
    def parse_hysteria2_url(self, hy2_url_str: str) -> Optional[Dict[str, Any]]:
        """解析Hysteria2订阅链接"""
        try:
            parsed_url = urlparse(hy2_url_str)
            auth = parsed_url.username
            server = parsed_url.hostname
            port = parsed_url.port
            node_name = unquote(parsed_url.fragment) if parsed_url.fragment else f"{server}:{port}"

            if not all([auth, server, port]):
                raise ValueError("Hysteria2链接缺少必要参数 (auth, server, port)")

            query_params = parse_qs(parsed_url.query)
            sni = query_params.get('sni', [server])[0]
            insecure = query_params.get('insecure', ['0'])[0] == '1' or query_params.get('skip-cert-verify', ['0'])[
                0] == '1'
            obfs_type = query_params.get('obfs', [''])[0]
            obfs_password = query_params.get('obfs-password', [''])[0]

            return {
                "type": "hysteria2",
                "name": node_name,
                "server": server,
                "port": int(port),
                "auth": auth,
                "sni": sni,
                "insecure": insecure,
                "obfs_type": obfs_type,
                "obfs_password": obfs_password,
            }
        except Exception as e:
            print(f"解析Hysteria2链接失败: {hy2_url_str} - 错误: {e}")
            return None

    def parse_subscription_link(self, link_str: str) -> Optional[Dict[str, Any]]:
        """根据链接前缀判断协议并调用相应的解析函数"""
        link_str = link_str.strip()
        if link_str.startswith("vmess://"):
            return self.parse_vmess_url(link_str)
        elif link_str.startswith("trojan://"):
            return self.parse_trojan_url(link_str)
        elif link_str.startswith("ss://"):
            return self.parse_ss_url(link_str)
        elif link_str.startswith("vless://"):
            return self.parse_vless_url(link_str)
        # NEW: Hysteria2 support
        elif link_str.startswith("hysteria2://"):
            return self.parse_hysteria2_url(link_str)
        else:
            if link_str:  # Avoid printing warnings for empty lines
                print(f"警告: 不支持的协议或格式: {link_str[:50]}...")
            return None

    def generate_xray_config(self, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """根据解析的节点信息生成Xray的JSON配置文件。"""
        inbounds = []
        outbounds = []
        routing_rules = []

        for i, node in enumerate(tqdm(nodes, desc="Generating Xray Config")):
            local_port = self.start_port + i
            inbound_tag = f"inbound_{i}"
            outbound_tag = f"outbound_{i}"

            inbounds.append({
                "listen": LISTEN_ADDRESS,
                "port": local_port,
                "protocol": PROTOCOL,
                "settings": {
                    "auth": "noauth",
                    "udp": True,
                    "ip": LISTEN_ADDRESS
                },
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
                "tag": inbound_tag
            })

            outbound_config = {"protocol": node["type"], "tag": outbound_tag, "settings": {}, "streamSettings": {}}

            # FIX: Standardized key access and correct config generation
            if node["type"] == "vmess":
                outbound_config["settings"]["vnext"] = [{
                    "address": node["server"],
                    "port": node["port"],
                    "users": [{"id": node["uuid"], "alterId": node["alter_id"] if 'alter_id' in node else node['alterId'],
                               "security": node["cipher"]}]
                }]
                outbound_config["streamSettings"] = {
                    "network": node["network"],
                    "security": "tls" if node["tls"] else "none"
                }
                if node["tls"]:
                    outbound_config["streamSettings"]["tlsSettings"] = {
                        "serverName": node["sni"],
                        "allowInsecure": node["allow_insecure"],
                        "fingerprint": node["fingerprint"] or "chrome",
                        "alpn": node["alpn"] or ["h2", "http/1.1"]
                    }
                if node["network"] == "ws":
                    wsOpts= node["ws-opts"] if 'ws-opts' in node else {
                        "path": node["path"],
                        "headers": {"Host": node["host"]}
                    }
                    outbound_config["streamSettings"]["wsSettings"] = wsOpts
                elif node["network"] == "grpc":
                    outbound_config["streamSettings"]["grpcSettings"] = {"serviceName": node["service_name"]}
            elif node["type"] == "trojan":
                outbound_config["settings"]["servers"] = [{
                    "address": node["server"],
                    "port": node["port"],
                    "password": node["password"]
                }]
                outbound_config["streamSettings"] = {
                    "network": "tcp",
                    "security": "tls",
                    "tlsSettings": {
                        "serverName": node["sni"] if 'sni' in node else node["server"],
                        "allowInsecure": node["allow_insecure"] if 'allow_insecure' in node else False,
                        "fingerprint": node["fingerprint"] if 'fingerprint' in node else "chrome",
                        "alpn": node["alpn"] if 'alpn' in node else ["h2", "http/1.1"]
                    }
                }

            elif node['type'] == 'shadowsocks':
                outbound_config["settings"]["servers"] = [{
                    "address": node["server"],
                    "port": node["port"],
                    "method": node["method"] if 'method' in node else node["cipher"],
                    "password": node["password"]
                }]
                outbound_config["streamSettings"] = {"network": "tcp", "security": "none"}

            elif node["type"] == "vless":
                outbound_config["settings"]["vnext"] = [{
                    "address": node["server"],
                    "port": node["port"],
                    "users": [{"id": node["uuid"], "encryption": "none", "flow": node.get("flow")}]
                }]
                outbound_config["streamSettings"] = {"network": node["network"], "security": node["security"]}
                if node["security"] in ["tls", "reality"]:
                    tls_settings = {
                        "serverName": node["sni"],
                        "allowInsecure": node["allow_insecure"],
                        "fingerprint": node["fingerprint"] or "chrome",
                        "alpn": node["alpn"] or ["h2", "http/1.1"]
                    }
                    if node["security"] == "reality":
                        tls_settings["realitySettings"] = {
                            "publicKey": node["public_key"],
                            "shortId": node["short_id"],
                            "spiderX": node["spider_x"]
                        }
                    outbound_config["streamSettings"]["tlsSettings"] = tls_settings
                if node["network"] == "ws":
                    outbound_config["streamSettings"]["wsSettings"] = {"path": node["path"],
                                                                       "headers": {"Host": node["host"]}}
                elif node["network"] == "grpc":
                    outbound_config["streamSettings"]["grpcSettings"] = {"serviceName": node["service_name"]}

            # NEW: Hysteria2 config generation
            elif node["type"] == "hysteria2":
                outbound_config["settings"] = {
                    "server": node["server"],
                    "port": node["port"],
                    "auth": node["auth"],
                    "sni": node["sni"],
                    "insecure": node["insecure"] if 'insecure' in node else False
                }
                if node.get("obfs_type") and node.get("obfs_password"):
                    outbound_config["settings"]["obfs"] = {
                        "type": node["obfs_type"],
                        "password": node["obfs_password"]
                    }
                # Hysteria2 manages its own stream, so streamSettings is empty
                outbound_config["streamSettings"] = {}

            outbounds.append(outbound_config)
            routing_rules.append({"type": "field", "inboundTag": [inbound_tag], "outboundTag": outbound_tag})

        xray_config = {
            "log": {"loglevel": "warning"},
            "inbounds": inbounds,
            "outbounds": outbounds + [
                {"protocol": "freedom", "tag": "direct"},
                {"protocol": "blackhole", "tag": "block"}
            ],
            "routing": {
                "domainStrategy": "AsIs",
                "rules": routing_rules + [
                    {"type": "field", "outboundTag": "direct", "ip": ["geoip:private"]},
                    {"type": "field", "outboundTag": "direct", "domain": ["geosite:private"]},
                ]
            }
        }
        return xray_config

    def write_xray_config(self, config: Dict[str, Any], file_path: str):
        """将Xray配置写入文件"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)  # ENHANCEMENT: indent=2 for smaller file size
            print(f"Xray配置已成功写入: {file_path}")
        except Exception as e:
            print(f"写入Xray配置失败: {e}")

    def parse_yaml_config(self, config_path: str) -> List[Dict[str, Any]]:
        """解析YAML配置文件 (e.g., Clash config)"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            if config and "proxies" in config:
                # FIX: Correct return syntax and type
                for proxy in config["proxies"]:
                    if proxy["type"] == "ss":
                        proxy["type"] = "shadowsocks"
                return config.get("proxies", [])
            return []
        except Exception as e:
            print(f"解析YAML配置失败: {e}")
            # FIX: Return empty list for consistency
            return []
#


if __name__ == "__main__":
    converter = SubscriptionConverter()
    # url = "https://spboard.cxwqs520.xyz/s/1686f24b0f61231cb1c5d7339447ce00"
    # url = "http://23.145.248.218:3389/api/v1/client/subscribe?token=14a2ff898d353516b4233800d3c38d06"
    # url = "https://52pokemon.xz61.cn/api/v1/client/subscribe?token=def90736bdf83907717e2662b5ba145e"
    # content = converter.fetch_subscription(url)
    # links = [link.strip() for link in content.split('\n') if link.strip()]
    # nodes = []
    # for link in links:
    #     node = converter.parse_subscription_link(link)
    #     if node:
    #         nodes.append(node)
    # #  drop first 3 nodes
    # nodes = nodes[3:]
    # config = converter.generate_xray_config(nodes)
    # converter.write_xray_config(config, "xray_config.json")

    config_path = "../config/temp.yaml"
    nodes = converter.parse_yaml_config(config_path)
    config = converter.generate_xray_config(nodes)
    converter.write_xray_config(config, "xray_temp_config.json")
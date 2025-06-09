import requests
import base64
import json
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs, unquote

PROTOCOL = "socks"  # 本地代理协议: "socks" (SOCKS5) 或 "http"
LISTEN_ADDRESS = "127.0.0.1"  # 本地代理监听地址


class SubscriptionConverter:
    def __init__(self, start_port: int = 10000):
        self.supported_protocols = ['vmess', 'trojan', 'ss', 'ssr', 'vless']
        self.port_mappings: Dict[int, int] = {}  # 存储端口映射关系
        self.start_port = start_port

    def fetch_subscription(self, url: str) -> str:
        """获取订阅内容"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # 尝试base64解码
            try:
                content = base64.b64decode(response.text).decode('utf-8')
            except:
                content = response.text

            return content
        except Exception as e:
            print(f"获取订阅失败: {e}")
            return ""

    # --- 辅助函数 ---
    def safe_base64_decode(self, data: str) -> str:
        """尝试Base64解码，处理可能的URL安全变体和填充问题"""
        data = data.replace('-', '+').replace('_', '/')  # URL safe to standard
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        try:
            return base64.b64decode(data).decode('utf-8')
        except Exception:
            return None

    def parse_vmess_url(self, vmess_url_str: str) -> Dict[str, Any]:
        """解析VMess订阅链接"""
        try:
            # vmess://base64_encoded_json_config
            base64_encoded_config = vmess_url_str[len("vmess://"):]
            decoded_json_str = self.safe_base64_decode(base64_encoded_config)
            if not decoded_json_str:
                raise ValueError("Base64解码失败或内容无效")

            config = json.loads(decoded_json_str)

            # 提取核心参数
            server = config.get('add')
            port = config.get('port')
            uuid = config.get('id')
            alter_id = config.get('aid', 0)
            security = config.get('scy', 'auto')  # 加密方式

            # 提取流设置
            network = config.get('net', 'tcp')
            tls = config.get('tls', '') == 'tls'
            host = config.get('host', '')
            path = config.get('path', '/')
            sni = config.get('sni', '')
            alpn = config.get('alpn', '')
            fingerprint = config.get('fp', '')  # TLS指纹
            allow_insecure = config.get('allowInsecure', '0') == '1'

            # for grpc
            service_name = config.get('servicename', '')

            # for http/2
            h2_host = config.get('host', '')

            node_name = unquote(config.get('ps', f"{server}:{port}"))  # 解码节点名称

            if not (server and port and uuid):
                raise ValueError("VMess链接缺少必要参数")

            return {
                "type": "vmess",
                "name": node_name,
                "server": server,
                "port": int(port),
                "uuid": uuid,
                "alter_id": int(alter_id),
                "security": security,
                "network": network,
                "tls": tls,
                "host": host,
                "path": path,
                "sni": sni if sni else server,  # Fallback to server as SNI
                "alpn": alpn.split(',') if alpn else [],
                "fingerprint": fingerprint,
                "allow_insecure": allow_insecure,
                "service_name": service_name,
                "h2_host": h2_host
            }
        except Exception as e:
            print(f"解析VMess链接失败: {vmess_url_str} - 错误: {e}")
            return None

    def parse_trojan_url(self, trojan_url_str: str) -> Dict[str, Any]:
        """解析Trojan订阅链接"""
        try:
            parsed_url = urlparse(trojan_url_str)

            node_name = unquote(
                parsed_url.fragment) if parsed_url.fragment else f"{parsed_url.hostname}:{parsed_url.port}"

            password = parsed_url.username
            server = parsed_url.hostname
            port = parsed_url.port

            query_params = parse_qs(parsed_url.query)
            sni = query_params.get('sni', [server])[0]
            fingerprint = query_params.get('fp', [''])[0]
            allow_insecure = query_params.get('allowInsecure', ['0'])[0] == '1'
            alpn = query_params.get('alpn', [''])[0].split(',') if query_params.get('alpn', [''])[0] else []

            if not (password and server and port):
                raise ValueError("Trojan链接缺少必要参数")

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

    def parse_ss_url(self, ss_url_str: str) -> Dict[str, Any]:
        """解析Shadowsocks订阅链接 (支持 base64 和 direct 格式)"""
        try:
            # ss://[base64_encoded_method:password@]server:port[#name]
            # 或 ss://base64_encoded_info[#name]

            base_part = ss_url_str[len("ss://"):].split('#')[0]  # 移除片段部分
            node_name = unquote(ss_url_str.split('#')[1]) if '#' in ss_url_str else f"{base_part.split('@')[-1]}"

            # 尝试 Base64 解码整个 Base Part
            decoded_base_part = self.safe_base64_decode(base_part.split('@')[0]) + '@' + \
                                base_part.split('@')[1].split('?')[0]
            if decoded_base_part:
                # 可能是 base64(method:password@server:port) 格式
                parts = decoded_base_part.split('@')
                if len(parts) == 2:
                    method_pass = parts[0].split(':')
                    server_port = parts[1].split(':')
                    method = method_pass[0]
                    password = method_pass[1]
                    server = server_port[0]
                    port = int(server_port[1])
                else:
                    # 兼容 ss://method:password@server:port 这种未完全base64的格式
                    raise ValueError("Shadowsocks Base64解码内容格式不正确")
            else:
                # 直接 method:password@server:port 格式
                parts = base_part.split('@')
                if len(parts) == 2:
                    method_pass = parts[0].split(':')
                    server_port = parts[1].split(':')
                    method = method_pass[0]
                    password = method_pass[1]
                    server = server_port[0]
                    port = int(server_port[1])
                else:
                    raise ValueError("Shadowsocks链接格式不正确")

            if not (method and password and server and port):
                raise ValueError("Shadowsocks链接缺少必要参数")

            return {
                "type": "shadowsocks",
                "name": node_name,
                "method": method,
                "password": password,
                "server": server,
                "port": port
            }
        except Exception as e:
            print(f"解析Shadowsocks链接失败: {ss_url_str} - 错误: {e}")
            return None

    def parse_vless_url(self, vless_url_str: str) -> Dict[str, Any]:
        """解析VLESS订阅链接"""
        try:
            # vless://uuid@server:port?params#name
            parsed_url = urlparse(vless_url_str)

            node_name = unquote(
                parsed_url.fragment) if parsed_url.fragment else f"{parsed_url.hostname}:{parsed_url.port}"

            uuid = parsed_url.username
            server = parsed_url.hostname
            port = parsed_url.port

            query_params = parse_qs(parsed_url.query)

            # Stream Settings
            network = query_params.get('type', ['tcp'])[0]
            security = query_params.get('security', ['none'])[0]  # tls, reality, none
            flow = query_params.get('flow', [''])[0]  # 例如 "xtls-rprx-vision"

            # TLS Settings
            sni = query_params.get('sni', [server])[0]
            fingerprint = query_params.get('fp', [''])[0]  # TLS指纹
            alpn = query_params.get('alpn', [''])[0].split(',') if query_params.get('alpn', [''])[0] else []
            allow_insecure = query_params.get('allowInsecure', ['0'])[0] == '1'

            # Reality Settings (only if security is 'reality')
            public_key = query_params.get('pbk', [''])[0]
            short_id = query_params.get('sid', [''])[0]
            spider_x = query_params.get('spx', [''])[0]  # Reality SpiderX, e.g., /

            # WS Settings
            path = query_params.get('path', ['/'])[0]
            host = query_params.get('host', [''])[0]  # WS Host

            # gRPC Settings
            service_name = query_params.get('servicename', [''])[0]
            enable_health_check = query_params.get('ehc', ['0'])[0] == '1'

            if not (uuid and server and port):
                raise ValueError("VLESS链接缺少必要参数")

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
                "enable_health_check": enable_health_check
            }
        except Exception as e:
            print(f"解析VLESS链接失败: {vless_url_str} - 错误: {e}")
            return None

    def parse_subscription_link(self, link_str: str) -> Dict[str, Any]:
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
        else:
            print(f"警告: 不支持的协议或格式: {link_str[:50]}...")
            return None

    def generate_xray_config(self, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """根据解析的节点信息生成Xray的JSON配置文件。"""
        inbounds = []
        outbounds = []
        routing_rules = []

        for i, node in enumerate(nodes):
            local_port = self.start_port + i + 1
            inbound_tag = f"inbound_{i + 1}"
            outbound_tag = f"outbound_{i + 1}"

            # 添加入站 (inbound) 配置
            inbounds.append({
                "listen": LISTEN_ADDRESS,
                "port": local_port,
                "protocol": PROTOCOL,
                "settings": {
                    "auth": "noauth",
                    "udp": True,
                    "ip": LISTEN_ADDRESS if PROTOCOL == "socks" else None  # For SOCKS5
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls"]
                },
                "tag": inbound_tag
            })

            # 添加出站 (outbound) 配置
            outbound_settings = {}
            stream_settings = {}

            # 根据协议类型构建不同的出站配置
            if node["type"] == "vmess":
                outbound_settings = {
                    "vnext": [
                        {
                            "address": node["server"],
                            "port": node["port"],
                            "users": [
                                {
                                    "id": node["uuid"],
                                    "alterId": node["alter_id"],
                                    "security": node["security"]
                                }
                            ]
                        }
                    ]
                }
                stream_settings = {
                    "network": node["network"],
                    "security": "tls" if node["tls"] else "none"
                }
                if node["tls"]:
                    stream_settings["tlsSettings"] = {
                        "serverName": node["sni"],
                        "allowInsecure": node["allow_insecure"],
                        "fingerprint": node["fingerprint"] if node["fingerprint"] else None,
                        "alpn": node["alpn"] if node["alpn"] else None
                    }
                if node["network"] == "ws":
                    stream_settings["wsSettings"] = {
                        "path": node["path"],
                        "headers": {"Host": node["host"]} if node["host"] else {}
                    }
                elif node["network"] == "grpc":
                    stream_settings["grpcSettings"] = {
                        "serviceName": node["service_name"]
                    }
                elif node["network"] == "h2":
                    stream_settings["httpSettings"] = {
                        "host": [node["h2_host"]] if node["h2_host"] else []
                    }

            elif node["type"] == "trojan":
                outbound_settings = {
                    "servers": [
                        {
                            "address": node["server"],
                            "port": node["port"],
                            "password": node["password"]
                        }
                    ]
                }
                stream_settings = {
                    "network": "tcp",  # Trojan通常是TCP
                    "security": "tls",
                    "tlsSettings": {
                        "serverName": node["sni"],
                        "allowInsecure": node["allow_insecure"],
                        "fingerprint": node["fingerprint"] if node["fingerprint"] else None,
                        "alpn": node["alpn"] if node["alpn"] else None
                    }
                }

            elif node["type"] == "shadowsocks":
                outbound_settings = {
                    "servers": [
                        {
                            "address": node["server"],
                            "port": node["port"],
                            "method": node["method"],
                            "password": node["password"]
                        }
                    ]
                }
                stream_settings = {"network": "tcp", "security": "none"}  # SS通常是TCP无TLS

            elif node["type"] == "vless":
                outbound_settings = {
                    "vnext": [
                        {
                            "address": node["server"],
                            "port": node["port"],
                            "users": [
                                {
                                    "id": node["uuid"],
                                    "encryption": "none",  # VLESS 通常为 "none"
                                    "flow": node["flow"] if node["flow"] else None
                                }
                            ]
                        }
                    ]
                }
                stream_settings = {
                    "network": node["network"],
                    "security": node["security"]
                }
                if node["security"] in ["tls", "reality"]:
                    tls_settings = {
                        "serverName": node["sni"],
                        "allowInsecure": node["allow_insecure"],
                        "fingerprint": node["fingerprint"] if node["fingerprint"] else None,
                        "alpn": node["alpn"] if node["alpn"] else None
                    }
                    if node["security"] == "reality":
                        tls_settings["realitySettings"] = {
                            "publicKey": node["public_key"],
                            "shortId": node["short_id"] if node["short_id"] else None,
                            "spiderX": node["spider_x"] if node["spider_x"] else None
                        }
                    stream_settings["tlsSettings"] = tls_settings

                if node["network"] == "ws":
                    stream_settings["wsSettings"] = {
                        "path": node["path"],
                        "headers": {"Host": node["host"]} if node["host"] else {}
                    }
                elif node["network"] == "grpc":
                    stream_settings["grpcSettings"] = {
                        "serviceName": node["service_name"],
                        "enableHealthCheck": node["enable_health_check"]
                    }
                elif node["network"] == "h2":
                    stream_settings["httpSettings"] = {
                        "host": [node["host"]] if node["host"] else []  # h2 host is list
                    }

            outbounds.append({
                "tag": outbound_tag,
                "protocol": node["type"],  # Xray protocol name
                "settings": outbound_settings,
                "streamSettings": stream_settings
            })

            # 添加路由规则
            routing_rules.append({
                "type": "field",
                "inboundTag": [inbound_tag],
                "outboundTag": outbound_tag
            })

        # Xray 完整配置结构
        xray_config = {
            "log": {
                "loglevel": "warning"
            },
            "inbounds": inbounds,
            "outbounds": outbounds + [
                # 添加一个直连 (direct) 和一个阻止 (block) 出站，以防万一
                {"protocol": "freedom", "tag": "direct"},
                {"protocol": "blackhole", "tag": "block"}
            ],
            "routing": {
                "domainStrategy": "AsIs",
                "rules": routing_rules + [
                    # 默认规则，如果上面没有匹配到，则直连或阻止
                    {"type": "field", "outboundTag": "direct", "ip": ["geoip:private"]},  # 内网直连
                    # 可以根据需要添加更多全局路由规则
                ]
            }
        }

        return xray_config

    def write_xray_config(self, config: Dict[str, Any], file_path: str):
        """将Xray配置写入文件"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            print(f"Xray配置已成功写入: {file_path}")
        except Exception as e:
            print(f"写入Xray配置失败: {e}")


if __name__ == "__main__":
    converter = SubscriptionConverter()
    url = "http://xxxx"
    content = converter.fetch_subscription(url)
    links = [link.strip() for link in content.split('\n') if link.strip()]
    nodes = []
    for link in links:
        node = converter.parse_subscription_link(link)
        if node:
            nodes.append(node)
    #  drop first 3 nodes
    nodes = nodes[3:]
    config = converter.generate_xray_config(nodes)
    converter.write_xray_config(config, "xray_config.json")

import httpx
import time
import asyncio
from typing import Optional, Dict, Any


async def get_info_with_proxy(
        url: str,
        proxy: Optional[Dict[str, str]] = None,
        timeout: int = 10
) -> Optional[Dict[str, Any]]:
    """
    Fetches information from a URL using an optional proxy.

    Args:
        url (str): The URL to fetch.
        proxy (Optional[Dict[str, str]]): Proxy settings in the format {'http': 'http://proxy:port', 'https': 'https://proxy:port'}.
        timeout (int): Timeout for the request in seconds.

    Returns:
        Optional[Dict[str, Any]]: Parsed JSON response if successful, None otherwise.
    """
    clint_config = {
        "timeout": httpx.Timeout(timeout, connect=timeout),
        "follow_redirects": True,
    }
    if proxy is not None:
        clint_config["proxies"] = proxy

    _proxy = proxy.get('http://') or proxy.get('https://') if proxy else None

    try:
        start_time = time.time()
        async with httpx.AsyncClient(**clint_config) as client:
            try:
                response = await client.get(url, timeout=timeout)
                response.raise_for_status()
                end_time = time.time()
                latency = round((end_time - start_time) * 1000, 2)  # Convert to milliseconds
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "status": 'success',
                        "latency": latency,
                        "data": data,
                        'proxy_used': _proxy,
                    }
                else:
                    return {
                        "status": 'error',
                        "latency": latency,
                        "message": f"HTTP error: {response.status_code}",
                        'proxy_used': _proxy,
                    }
            except httpx.TimeoutException as e:
                return {
                    "status": 'error',
                    "latency": None,
                    "message": f"Request timed out: {e}",
                    'proxy_used': _proxy,
                }
            except httpx.RequestError as e:
                return {
                    "status": 'error',
                    "latency": None,
                    "message": f"Request error: {e}",
                    'proxy_used': _proxy,
                }
    except Exception as e:
        return {
            "status": 'error',
            "latency": None,
            "message": f"An unexpected error occurred: {e}",
            'proxy_used': _proxy,
        }


async def get_multiple_proxies(
        url: str,
        proxies: Dict[str, str],
        timeout: int = 10
) -> list[Optional[Dict[str, Any]]]:
    tasks = []
    for proxy in proxies:
        task = get_info_with_proxy(url, proxy, timeout=timeout)
        tasks.append(task)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results


if __name__ == "__main__":
    url = "https://api.ipify.org?format=json"
    # socks5 proxy
    # proxy = {
    #     "http://": "socks5://127.0.0.1:10001",
    #     "https://": "socks5://127.0.0.1:10001"
    # }
    # result = asyncio.run(get_info_with_proxy(url, proxy))
    # print(result)

    proxies = [ {
        "http://": "socks5://127.0.0.1:"+str(10000+port),
        "https://": "socks5://127.0.0.1:"+ str(10000+port)
    } for port in range(1,70)]

    results = asyncio.run(get_multiple_proxies(url, proxies))
    for i, res in enumerate(results):
        print(f"Proxy {i+1}: {res}")

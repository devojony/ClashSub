from decimal import Decimal
import os
import logging
import asyncio
from datetime import datetime
import sys
import re
import base64
import json

import aiohttp
import yaml
from tqdm import tqdm
import collections


SubInfo = collections.namedtuple(
    "SubInfo", ["url", "upload", "download", "total", "expireSec"]
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/gooooooooooooogle/collectSub/main"
GITHUB_API_BASE = "https://api.github.com/repos/gooooooooooooogle/collectSub"


async def fetch_remote_txt(url):
    logger.info(f"开始获取远程内容: {url}")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            text = await response.text()
            logger.info(f"成功获取远程内容，长度: {len(text)}")
            return text


async def get_latest_sub_file(session, proxy: str | None = None) -> str | None:
    now = datetime.now()
    year = now.year
    month = now.month
    day = now.day
    timeout = aiohttp.ClientTimeout(total=30)

    # 尝试当前月份和上个月
    for attempt in range(2):
        if attempt == 1:
            # 回退到上个月
            month -= 1
            if month == 0:
                month = 12
                year -= 1
            logger.info(f"当前月份目录不存在，尝试上个月: {year}/{month}")

        sub_dir_url = f"{GITHUB_API_BASE}/contents/sub/{year}/{month}"
        logger.info(f"检查目录: {sub_dir_url}")

        try:
            async with session.get(
                sub_dir_url, timeout=timeout, proxy=proxy
            ) as response:
                if response.status == 404:
                    logger.warning(f"目录不存在: sub/{year}/{month}")
                    continue
                response.raise_for_status()
                files = await response.json()

            available_files = [f for f in files if f["name"].endswith(".yaml")]
            if not available_files:
                logger.warning("未找到yaml文件")
                continue

            # 如果是当前月份，尝试找今天的文件
            if attempt == 0:
                target_file = f"{month}-{day}.yaml"
                for f in available_files:
                    if f["name"] == target_file:
                        logger.info(f"找到今日订阅文件: {f['name']}")
                        return f["download_url"]

            # 否则使用最新的文件
            available_files.sort(key=lambda x: x["name"], reverse=True)
            latest = available_files[0]
            logger.info(f"使用最新订阅文件: {latest['name']}")
            return latest["download_url"]

        except Exception as e:
            logger.error(f"获取订阅文件列表失败: {e}")
            continue

    return None


async def fetch_clash_subscriptions(
    session, url, proxy: str | None = None
) -> tuple[list[str], list[str]]:
    """返回 (clash_urls, v2ray_urls)"""
    logger.info(f"获取订阅配置: {url}")
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with session.get(url, timeout=timeout, proxy=proxy) as response:
            response.raise_for_status()
            content = await response.text()
            data = yaml.safe_load(content)
            if not data:
                logger.warning("解析yaml失败")
                return [], []

            clash_urls = []
            v2ray_urls = []

            if "clash订阅" in data:
                urls = [u.strip() for u in data["clash订阅"] if u.strip()]
                logger.info(f"clash订阅: {len(urls)} 个")
                clash_urls.extend(urls)

            if "机场订阅" in data:
                urls = [u.strip() for u in data["机场订阅"] if u.strip()]
                logger.info(f"机场订阅: {len(urls)} 个")
                clash_urls.extend(urls)

            if "开心玩耍" in data:
                pattern = re.compile(r"https?://\S+")
                for item in data["开心玩耍"]:
                    match = pattern.search(str(item))
                    if match:
                        clash_urls.append(match.group())
                logger.info(f"开心玩耍: {len([u for u in data['开心玩耍'] if u])} 个")

            if "v2订阅" in data:
                urls = [u.strip() for u in data["v2订阅"] if u.strip()]
                logger.info(f"v2订阅: {len(urls)} 个")
                v2ray_urls.extend(urls)

            logger.info(
                f"总计获取到 {len(clash_urls)} 个clash订阅URL, {len(v2ray_urls)} 个v2ray订阅URL"
            )
            return clash_urls, v2ray_urls
    except Exception as e:
        logger.error(f"解析订阅配置失败: {e}")
        return [], []


async def fetch_v2ray_proxies(session, url, proxy: str | None = None) -> list[dict]:
    """获取 v2ray 订阅并转换为 clash proxy 格式"""
    logger.info(f"获取v2ray订阅: {url}")
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with session.get(url, timeout=timeout, proxy=proxy) as response:
            response.raise_for_status()
            content = await response.text()

            # base64 解码
            try:
                decoded = base64.b64decode(content).decode("utf-8")
            except Exception:
                logger.warning(f"base64解码失败，尝试直接解析: {url}")
                decoded = content

            proxies = []
            for line in decoded.split("\n"):
                line = line.strip()
                if not line:
                    continue

                try:
                    if line.startswith("vmess://"):
                        proxy_config = parse_vmess(line)
                        if proxy_config:
                            proxies.append(proxy_config)
                    elif line.startswith("vless://"):
                        proxy_config = parse_vless(line)
                        if proxy_config:
                            proxies.append(proxy_config)
                    elif line.startswith("ss://"):
                        proxy_config = parse_ss(line)
                        if proxy_config:
                            proxies.append(proxy_config)
                    elif line.startswith("trojan://"):
                        proxy_config = parse_trojan(line)
                        if proxy_config:
                            proxies.append(proxy_config)
                except Exception as e:
                    logger.debug(f"解析代理失败: {line[:50]}... 错误: {e}")
                    continue

            logger.info(f"从 {url} 解析到 {len(proxies)} 个代理")
            return proxies
    except Exception as e:
        logger.error(f"获取v2ray订阅失败: {url}, 错误: {e}")
        return []


def parse_vmess(uri: str) -> dict | None:
    """解析 vmess:// URI 为 clash 格式"""
    try:
        data = json.loads(base64.b64decode(uri[8:]).decode("utf-8"))
        return {
            "name": data.get("ps", "vmess"),
            "type": "vmess",
            "server": data.get("add"),
            "port": int(data.get("port", 443)),
            "uuid": data.get("id"),
            "alterId": int(data.get("aid", 0)),
            "cipher": data.get("scy", "auto"),
            "network": data.get("net", "tcp"),
            "tls": data.get("tls") == "tls",
            "skip-cert-verify": True,
        }
    except Exception as e:
        logger.debug(f"vmess解析失败: {e}")
        return None


def parse_vless(uri: str) -> dict | None:
    """解析 vless:// URI 为 clash 格式"""
    try:
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(uri)
        params = parse_qs(parsed.query)

        return {
            "name": params.get("remarks", ["vless"])[0]
            if "remarks" in params
            else "vless",
            "type": "vless",
            "server": parsed.hostname,
            "port": parsed.port or 443,
            "uuid": parsed.username,
            "network": params.get("type", ["tcp"])[0],
            "tls": params.get("security", [""])[0] == "tls",
            "skip-cert-verify": True,
        }
    except Exception as e:
        logger.debug(f"vless解析失败: {e}")
        return None


def parse_ss(uri: str) -> dict | None:
    """解析 ss:// URI 为 clash 格式"""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(uri)

        if not parsed.username:
            return None

        # 解码 userinfo
        userinfo = base64.b64decode(parsed.username).decode("utf-8")
        method, password = userinfo.split(":", 1)

        return {
            "name": parsed.fragment or "ss",
            "type": "ss",
            "server": parsed.hostname,
            "port": parsed.port or 443,
            "cipher": method,
            "password": password,
        }
    except Exception as e:
        logger.debug(f"ss解析失败: {e}")
        return None


def parse_trojan(uri: str) -> dict | None:
    """解析 trojan:// URI 为 clash 格式"""
    try:
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(uri)
        params = parse_qs(parsed.query)

        return {
            "name": parsed.fragment or "trojan",
            "type": "trojan",
            "server": parsed.hostname,
            "port": parsed.port or 443,
            "password": parsed.username,
            "sni": params.get("sni", [parsed.hostname])[0],
            "skip-cert-verify": True,
        }
    except Exception as e:
        logger.debug(f"trojan解析失败: {e}")
        return None


async def generate_provider_file(
    session, provider_urls: list[str], v2ray_proxies: list[dict], proxy: str | None
):
    """生成只包含 proxies 的 provider 文件"""
    logger.info("开始生成 provider 专用文件")

    all_proxies = []

    # 从 provider URLs 获取节点
    if provider_urls:
        logger.info(f"从 {len(provider_urls)} 个 provider 获取节点")
        for provider_url in provider_urls:
            try:
                timeout = aiohttp.ClientTimeout(total=60)
                headers = {"User-Agent": "clash.meta"}
                async with session.get(
                    provider_url, timeout=timeout, proxy=proxy, headers=headers
                ) as response:
                    response.raise_for_status()
                    content = await response.text()
                    data = yaml.safe_load(content)

                    # 提取 proxies
                    proxies = data.get("proxies", [])
                    if proxies:
                        all_proxies.extend(proxies)
                        logger.info(
                            f"从 {provider_url[:50]}... 获取 {len(proxies)} 个节点"
                        )
            except Exception as e:
                logger.error(
                    f"获取 provider 节点失败: {provider_url[:50]}... 错误: {e}"
                )

    # 添加 v2ray 节点
    if v2ray_proxies:
        all_proxies.extend(v2ray_proxies)
        logger.info(f"添加 {len(v2ray_proxies)} 个 v2ray 节点")

    if not all_proxies:
        logger.warning("没有可用节点，跳过生成 provider 文件")
        return

    # 生成 provider 格式的配置
    provider_config = {"proxies": all_proxies}

    output_path = os.path.join("clash", "proxies.yaml")
    logger.info(f"写入 provider 文件: {output_path} (共 {len(all_proxies)} 个节点)")

    with open(output_path, "w", encoding="utf-8") as file:
        yaml.dump(provider_config, file, allow_unicode=True, sort_keys=False)

    logger.info(f"Provider 文件生成完成: {output_path}")


async def main():
    logger.info("开始加载配置文件")
    with open("clash-template.yaml", "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if proxy:
        logger.info(f"使用代理: {proxy}")

    logger.info("开始获取远程订阅内容")
    async with aiohttp.ClientSession() as session:
        sub_file_url = await get_latest_sub_file(session, proxy)
        if not sub_file_url:
            logger.error("无法获取订阅文件")
            return

        clash_urls, v2ray_urls = await fetch_clash_subscriptions(
            session, sub_file_url, proxy
        )
        if not clash_urls and not v2ray_urls:
            logger.error("未获取到任何订阅URL")
            return

        # 处理 clash 订阅
        logger.info("开始过滤有效clash订阅URL")
        valid_clash_urls = await filter_valid_urls(clash_urls) if clash_urls else []

        # 处理 v2ray 订阅
        all_v2ray_proxies = []
        if v2ray_urls:
            logger.info(f"开始获取v2ray订阅，共 {len(v2ray_urls)} 个")
            for v2_url in v2ray_urls:
                proxies = await fetch_v2ray_proxies(session, v2_url, proxy)
                all_v2ray_proxies.extend(proxies)
            logger.info(f"v2ray订阅共获取到 {len(all_v2ray_proxies)} 个代理")

    # 配置 proxy-providers
    config["proxy-providers"] = {
        f"provider#{i}": {
            "type": "http",
            "url": pp.strip(),
            "interval": 3600,
            "health-check": {
                "enable": True,
                "interval": 600,
                "url": "http://www.gstatic.com/generate_204",
            },
            "exclude-filter": "套餐|流量|群组|邀请|官网|重置|剩余|订阅",
        }
        for i, pp in enumerate(valid_clash_urls)
    }

    # 添加 v2ray proxies
    if all_v2ray_proxies:
        if "proxies" not in config:
            config["proxies"] = []
        config["proxies"].extend(all_v2ray_proxies)
        logger.info(f"添加 {len(all_v2ray_proxies)} 个v2ray代理到配置")

    # 更新 proxy-groups 以使用 include-all 或 include-all-providers
    has_proxies = all_v2ray_proxies and len(all_v2ray_proxies) > 0
    has_providers = len(config.get("proxy-providers", {})) > 0

    if has_proxies or has_providers:
        logger.info(
            f"更新 proxy-groups 配置 (proxies: {has_proxies}, providers: {has_providers})"
        )
        for group in config.get("proxy-groups", []):
            # 为需要代理节点的组添加 include-all 字段
            if group.get("type") in ["select", "url-test", "fallback", "load-balance"]:
                # 如果同时有 proxies 和 providers，使用 include-all
                if has_proxies and has_providers:
                    group["include-all"] = True
                    logger.debug(f"为 {group.get('name')} 设置 include-all: true")
                # 如果只有 providers，使用 include-all-providers
                elif has_providers:
                    group["include-all-providers"] = True
                    logger.debug(
                        f"为 {group.get('name')} 设置 include-all-providers: true"
                    )
                # 如果只有 proxies，使用 include-all-proxies
                elif has_proxies:
                    group["include-all-proxies"] = True
                    logger.debug(
                        f"为 {group.get('name')} 设置 include-all-proxies: true"
                    )

    logger.info("创建输出目录")
    os.makedirs("clash", exist_ok=True)

    output_path = os.path.join("clash", "subs.yaml")

    # 检查文件是否有变更
    old_content = None
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as file:
            old_content = file.read()

    # 生成新内容
    import io

    new_content_io = io.StringIO()
    yaml.dump(config, new_content_io, allow_unicode=True, sort_keys=False)
    new_content = new_content_io.getvalue()

    # 比较内容
    if old_content == new_content:
        logger.info("配置文件无变更，跳过写入")
    else:
        logger.info(f"开始写入配置文件: {output_path}")
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(new_content)
        logger.info(f"配置文件写入完成: {output_path}")

    # 生成 provider 专用文件（只包含 proxies）
    if has_proxies or has_providers:
        await generate_provider_file(
            session, valid_clash_urls, all_v2ray_proxies, proxy
        )


# subscription-userinfo: upload=1234; download=2234; total=1024000; expire=2218532293
async def fetch_sub_info(session, url) -> SubInfo | None:
    try:
        logger.debug(f"开始获取订阅信息: {url}")
        async with session.get(url) as response:
            response.raise_for_status()
            sub_info = response.headers.get("subscription-userinfo")
            if not sub_info:
                logger.warning(f"未找到订阅信息: {url}")
                return None
            logger.debug(f"成功获取订阅信息: {url}")

            info_dict = {}
            for item in sub_info.split(";"):
                item = item.strip()
                if not item:
                    continue
                key, value = item.split("=")
                info_dict[key.strip()] = value.strip()

            def safe_int(value):
                try:
                    if value.lower() == "infinity":
                        return 0
                    if not value:
                        return sys.maxsize
                    return Decimal(value)
                except ValueError:
                    logger.error(f"数据解析失败: <{value}>")
                    return -1

            return SubInfo(
                url=url,  # 添加原始URL
                upload=safe_int(info_dict.get("upload")),
                download=safe_int(info_dict.get("download")),
                total=safe_int(info_dict.get("total")),
                expireSec=safe_int(info_dict.get("expire")),
            )
    except Exception as e:
        logger.error(f"获取订阅信息失败: {url}, 错误: {str(e)}")
        return None


async def filter_valid_urls_concurrent(urls: list[str]) -> list[str]:
    valid_urls = []
    # 增加连接数限制到50，提高并发性能
    connector = aiohttp.TCPConnector(limit=50, force_close=True)

    # 添加性能统计
    start_time = datetime.now()

    async with aiohttp.ClientSession(
        connector=connector, headers={"User-Agent": "clash.meta"}
    ) as session:
        tasks = [asyncio.create_task(fetch_sub_info(session, url)) for url in urls]
        now = datetime.now().timestamp()

        # 使用asyncio.as_completed替代gather，实现流式处理
        with tqdm(total=len(urls), desc="过滤URL") as pbar:
            for task in asyncio.as_completed(tasks):
                try:
                    info: SubInfo | None = await task
                    if not info:
                        continue

                    usage = info.download + info.upload
                    if info.total > 0 and usage >= info.total:
                        logger.warning(
                            f"订阅流量已耗尽({usage / (1024**3):.2f} GB) - {info.url}"
                        )
                        continue

                    if info.expireSec <= now:
                        now_datetime = datetime.fromtimestamp(now).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        sub_datetime = datetime.fromtimestamp(info.expireSec).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        logger.warning(
                            f"订阅已经过期({now_datetime} / {sub_datetime}) - {info.url}"
                        )
                        continue

                    valid_urls.append(info.url)
                    logger.info(f"有效URL: {info.url}")

                except asyncio.TimeoutError:
                    logger.warning("请求超时")
                except Exception as e:
                    logger.error(f"处理URL时出错: {str(e)}")
                finally:
                    pbar.update(1)

    # 计算并记录性能统计
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    logger.info(
        f"URL过滤完成 - 总数: {len(urls)}, "
        f"成功: {len(valid_urls)}, "
        f"耗时: {duration:.2f}秒, "
        f"平均速度: {len(urls) / duration:.2f} URL/秒"
    )
    return valid_urls


async def filter_valid_urls(urls: list[str]) -> list[str]:
    logger.info(f"开始过滤URL，总数: {len(urls)}")
    valid_urls = await filter_valid_urls_concurrent(urls)
    logger.info(f"过滤完成，有效URL数: {len(valid_urls)}")
    return valid_urls


if __name__ == "__main__":
    asyncio.run(main())

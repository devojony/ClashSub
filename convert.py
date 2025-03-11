from decimal import Decimal
import os
import logging
import asyncio
from datetime import datetime
import sys

import aiohttp
import yaml
from tqdm import tqdm
import collections

SubInfo = collections.namedtuple(
    "SubInfo",
    ['url', 'upload', 'download', 'total', 'expireSec']
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


async def fetch_remote_txt(url):
    logger.info(f"开始获取远程内容: {url}")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            text = await response.text()
            logger.info(f"成功获取远程内容，长度: {len(text)}")
            return text


async def main():
    logger.info("开始加载配置文件")
    with open("clash-template.yaml", "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    logger.info("开始获取远程订阅内容")
    remote_url = "https://raw.githubusercontent.com/devojony/collectSub/refs/heads/main/sub/sub_all_clash.txt"
    content = await fetch_remote_txt(remote_url)
    proxy_providers = [p for p in content.split("\n") if p.strip()]
    logger.info(f"获取到初始URL数量: {len(proxy_providers)}")

    logger.info("开始过滤有效URL")
    proxy_providers = await filter_valid_urls(proxy_providers)

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
            "exclude-filter": "套餐|流量|群组|邀请|官网|重置|剩余|订阅"
        }
        for i, pp in enumerate(proxy_providers)
    }

    logger.info("创建输出目录")
    os.makedirs("clash", exist_ok=True)

    output_path = os.path.join("clash", "subs.yaml")
    logger.info(f"开始写入配置文件: {output_path}")
    with open(output_path, "w", encoding="utf-8") as file:
        yaml.dump(config, file, allow_unicode=True, sort_keys=False)
    logger.info(f"配置文件写入完成: {output_path}")


# subscription-userinfo: upload=1234; download=2234; total=1024000; expire=2218532293
async def fetch_sub_info(session, url) -> SubInfo | None:
    try:
        logger.debug(f"开始获取订阅信息: {url}")
        async with session.get(url) as response:
            response.raise_for_status()
            sub_info = response.headers.get("subscription-userinfo")
            if not sub_info:
                logger.debug(f"未找到订阅信息: {url}")
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
                    if value.lower() == 'infinity':
                        return 0
                    if not value:
                        return sys.maxsize
                    return Decimal(value)
                except ValueError:
                    logger.debug(f"数据解析失败: <{value}>")
                    return -1

            return SubInfo(
                url=url,  # 添加原始URL
                upload=safe_int(info_dict.get("upload")),
                download=safe_int(info_dict.get("download")),
                total=safe_int(info_dict.get("total")),
                expireSec=safe_int(info_dict.get("expire"))
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
        connector=connector,
        headers={"User-Agent": "clash.meta"}
    ) as session:
        tasks = [
            asyncio.create_task(
                fetch_sub_info(session, url)
            )
            for url in urls
        ]
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
                            f"订阅流量已耗尽({usage / (1024**3):.2f} GB) - {info.url}")
                        continue

                    if info.expireSec <= now: 
                        now_datetime = datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')
                        sub_datetime = datetime.fromtimestamp(info.expireSec).strftime('%Y-%m-%d %H:%M:%S')
                        logger.warning(f"订阅已经过期({now_datetime} / {sub_datetime}) - {info.url}")
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
        f"平均速度: {len(urls)/duration:.2f} URL/秒"
    )
    return valid_urls


async def filter_valid_urls(urls: list[str]) -> list[str]:
    logger.info(f"开始过滤URL，总数: {len(urls)}")
    valid_urls = await filter_valid_urls_concurrent(urls)
    logger.info(f"过滤完成，有效URL数: {len(valid_urls)}")
    return valid_urls


if __name__ == "__main__":
    asyncio.run(main())

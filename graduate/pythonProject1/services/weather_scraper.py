"""weather_scraper.py

【教学版说明】
本文件是“数据采集”模块，核心能力：
1) httpx + asyncio 异步爬取 2345 天气网各辖区数据
2) BeautifulSoup 解析 HTML
3) 数据清洗与校验
4) 去重后写入 MySQL（重复数据跳过）
5) 日志记录与异常重试

注意：
- 为了不破坏你原有项目的导入结构，本模块**不要**使用 pythonProject1.xxx 这种包名导入。
- 统一使用项目同级模块导入：import models / from database import SessionLocal。
- 这样可避免“同一张表被注册两次”的错误：Table 'weather_data' is already defined。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

# 关键：这里必须用与 api_server.py 相同的导入方式（同一套 models/Base）
import models
from models import WeatherData


# --------------------- 日志配置 ---------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s",
    handlers=[
        logging.FileHandler("scraper.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class WeatherScraper:
    """2345 天气网爬虫（精简版：抓当前页面可见历史表格）。"""

    BASE_URL = "https://tianqi.2345.com/wea_history/{area_code}.htm"

    # 广州各辖区在 2345 天气网的 URL code
    AREA_CODES = {
        "从化区": "70077",
        "增城区": "60368",
        "花都区": "60024",
        "南沙区": "72028",
        "番禺区": "60025",
        "白云区": "72026",
        "黄埔区": "72027",
        "天河区": "72025",
        "海珠区": "72024",
        "荔湾区": "72022",
        "越秀区": "72023",
    }

    def __init__(self, max_retries: int = 3, timeout: int = 20):
        self.max_retries = max_retries
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        }

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        """带重试机制的异步请求。"""
        for attempt in range(self.max_retries):
            try:
                resp = await client.get(url, headers=self.headers, timeout=self.timeout)
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPError as e:
                logger.warning(f"请求失败 (第 {attempt + 1} 次): {url}, 错误: {e}")
                await asyncio.sleep(2 ** attempt)
        logger.error(f"请求失败超过 {self.max_retries} 次: {url}")
        return None

    def _parse_html(self, html: str, area: str) -> List[Dict]:
        """解析单个页面 HTML，提取天气数据。"""
        soup = BeautifulSoup(html, "html.parser")

        # 2345 历史页通常使用 history-table
        table = soup.find("table", class_="history-table")
        if not table:
            return []

        data: List[Dict] = []
        rows = table.find_all("tr")[1:]
        for row in rows:
            cols = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cols) < 6:
                continue

            try:
                # 日期：页面可能是 "2026-01-01 周四"，只取前半段 "YYYY-MM-DD"
                date_str = (cols[0] or "").split()[0]
                d = datetime.strptime(date_str, "%Y-%m-%d").date()

                # 温度：页面有两种常见格式：
                # 1) "28℃/20℃"（一个单元格里同时有高低温）
                # 2) 分成两列：cols[1]="21°" cols[2]="8°"（此时 cols[3] 才是天气）
                def _to_float(s: str) -> float:
                    # 去掉 ° / ℃ 以及其它非数字符号（保留负号/小数点）
                    ss = (s or "").replace("℃", "").replace("°", "")
                    ss = "".join(ch for ch in ss if (ch.isdigit() or ch in "- ."))
                    return float(ss)

                if "/" in (cols[1] or ""):
                    temp_parts = cols[1].replace("℃", "").replace("°", "").split("/")
                    max_temp = _to_float(temp_parts[0])
                    min_temp = _to_float(temp_parts[1])
                    weather_text = cols[2]
                    wind_text = cols[3]
                    aqi_text = cols[5]
                else:
                    # 兼容 6 列：date, max, min, weather, wind, aqi
                    max_temp = _to_float(cols[1])
                    min_temp = _to_float(cols[2])
                    weather_text = cols[3]
                    wind_text = cols[4]
                    aqi_text = cols[5]

                # AQI：可能含文字，取数字部分
                aqi_val = None
                if aqi_text:
                    num = "".join([ch for ch in aqi_text if ch.isdigit()])
                    aqi_val = int(num) if num else None

                item = {
                    "area": area,
                    "date": d,
                    "max_temp": max_temp,
                    "min_temp": min_temp,
                    "weather": weather_text,
                    "wind": wind_text,
                    "aqi": aqi_val,
                }
                data.append(item)
            except Exception as e:
                logger.warning(f"解析行失败: {cols}, 错误: {e}")

        return data

    async def scrape_area(self, client: httpx.AsyncClient, area: str, code: str) -> List[Dict]:
        url = self.BASE_URL.format(area_code=code)
        logger.info(f"正在爬取 {area} ({url})...")
        html = await self._fetch_page(client, url)
        if not html:
            return []
        return self._parse_html(html, area)

    async def run(self) -> List[Dict]:
        """爬取所有辖区并返回数据。"""
        all_data: List[Dict] = []
        async with httpx.AsyncClient() as client:
            tasks = [self.scrape_area(client, area, code) for area, code in self.AREA_CODES.items()]
            results = await asyncio.gather(*tasks)
            for res in results:
                all_data.extend(res)
        logger.info(f"所有辖区爬取完成，共获得 {len(all_data)} 条原始数据。")
        return all_data


def save_data_to_db(data: List[Dict], db: Session) -> int:
    """去重后写入数据库。"""
    if not data:
        return 0

    existing_keys = set()
    min_date = min(d["date"] for d in data)
    max_date = max(d["date"] for d in data)

    existing_records = (
        db.query(WeatherData.area, WeatherData.date)
        .filter(WeatherData.date.between(min_date, max_date))
        .all()
    )
    for area, d in existing_records:
        existing_keys.add((area, d))

    new_records = []
    for item in data:
        if (item["area"], item["date"]) in existing_keys:
            continue
        new_records.append(WeatherData(**item))

    if new_records:
        db.bulk_save_objects(new_records)
        db.commit()
        logger.info(f"成功向数据库插入 {len(new_records)} 条新记录。")
        return len(new_records)

    logger.info("没有新数据需要插入数据库。")
    return 0


async def run_scrape_once_async() -> Dict:
    """给外部调用的一次性采集（异步）。"""
    from database import SessionLocal  # 延迟导入，避免循环

    logger.info("====== 开始执行采集任务 ======")
    scraper = WeatherScraper()
    db = None
    try:
        scraped_data = await scraper.run()
        db = SessionLocal()
        inserted = save_data_to_db(scraped_data, db)
        return {"ok": True, "total_scraped": len(scraped_data), "inserted": inserted}
    except Exception as e:
        logger.error(f"采集任务执行失败: {e}", exc_info=True)
        return {"ok": False, "total_scraped": 0, "inserted": 0, "error": str(e)}
    finally:
        if db:
            db.close()
        logger.info("====== 采集任务结束 ======")


if __name__ == "__main__":
    # 本文件直接运行：执行一次采集用于测试
    print(asyncio.run(run_scrape_once_async()))

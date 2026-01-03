"""scrape_service.py

B方案：手动触发采集服务
- 不自动启动定时任务
- FastAPI 路由调用 run_scrape_once() 即可执行一次采集并返回结果

关键点：
- 必须与主应用使用相同的导入路径（同一套 models/Base），避免表重复注册。
- 因此这里使用：from services.weather_scraper import ...（不要 pythonProject1.services...）。
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from database import SessionLocal

from services.weather_scraper import WeatherScraper, save_data_to_db


@dataclass
class ScrapeResult:
    ok: bool
    inserted: int
    total_scraped: int
    started_at: str
    finished_at: str
    error: Optional[str] = None


async def _run_scrape_once_async() -> ScrapeResult:
    started = datetime.utcnow()
    db = None
    try:
        scraper = WeatherScraper()
        scraped = await scraper.run()

        db = SessionLocal()
        inserted = save_data_to_db(scraped, db)

        finished = datetime.utcnow()
        return ScrapeResult(
            ok=True,
            inserted=int(inserted),
            total_scraped=int(len(scraped)),
            started_at=started.isoformat() + "Z",
            finished_at=finished.isoformat() + "Z",
            error=None,
        )
    except Exception as e:
        finished = datetime.utcnow()
        return ScrapeResult(
            ok=False,
            inserted=0,
            total_scraped=0,
            started_at=started.isoformat() + "Z",
            finished_at=finished.isoformat() + "Z",
            error=str(e),
        )
    finally:
        if db:
            db.close()


def run_scrape_once() -> Dict[str, Any]:
    """同步执行一次采集（给 FastAPI 的普通 def 路由使用）。"""
    result = asyncio.run(_run_scrape_once_async())
    return asdict(result)

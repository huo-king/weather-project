"""export_service.py

导出服务：把查询结果导出为 CSV。

注意：
- 浏览器对 Content-Disposition 的文件名编码比较挑剔。
- 如果文件名包含中文，Starlette 默认会尝试用 latin-1 编码 header，导致报错。
- 解决方案：
  1) Content-Disposition 使用 ASCII filename（不含中文）
  2) 同时提供 RFC5987 的 filename*（UTF-8 URL 编码）
"""

from __future__ import annotations

from io import StringIO
from typing import Optional, Tuple
from urllib.parse import quote

import pandas as pd
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from models import WeatherData


def build_export_df(
    db: Session,
    area: Optional[str],
    start_d,
    end_d,
) -> pd.DataFrame:
    cols = [
        WeatherData.area,
        WeatherData.date,
        WeatherData.max_temp,
        WeatherData.min_temp,
        WeatherData.weather,
        WeatherData.wind,
        WeatherData.aqi,
    ]

    stmt = select(*cols)
    conds = []
    if area:
        conds.append(WeatherData.area == area)
    if start_d:
        conds.append(WeatherData.date >= start_d)
    if end_d:
        conds.append(WeatherData.date <= end_d)
    if conds:
        stmt = stmt.where(and_(*conds))

    rows = db.execute(stmt).all()
    return pd.DataFrame(rows, columns=["area", "date", "max_temp", "min_temp", "weather", "wind", "aqi"])


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    sio = StringIO()
    df.to_csv(sio, index=False)
    return sio.getvalue().encode("utf-8-sig")


def build_content_disposition(filename_utf8: str) -> str:
    """生成兼容中文文件名的 Content-Disposition。

    - filename: 仅 ASCII，防止 header 编码失败
    - filename*: RFC5987 UTF-8 编码，浏览器会优先使用
    """

    safe_ascii = "download.csv"
    encoded = quote(filename_utf8)
    return f"attachment; filename={safe_ascii}; filename*=UTF-8''{encoded}"

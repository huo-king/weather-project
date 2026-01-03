"""quality_checks.py

数据质量自检：
1) 爬取数据 vs 网站数据一致性抽检
2) 预测结果 vs 实际结果的误差评估（要求误差不超过阈值）

说明：
- 为了避免频繁访问目标站点导致封禁，这里做“抽样校验”：
  仅随机抽取 N 条记录，从网页端再次解析并比对。
- 预测评估：对历史数据做滚动回测（walk-forward），输出误差统计。

返回结果供 API 展示，也可写入日志。
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
import httpx
from sqlalchemy import func
from bs4 import BeautifulSoup

from database import SessionLocal
from models import WeatherData
from analysis import forecast_aqi_7_days


# --------------------- 1) 网站一致性抽检 ---------------------

AREA_CODE = {
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

BASE_URL = "https://tianqi.2345.com/wea_history/{code}.htm"
# 2345 历史页（不带月份参数）通常只展示最近 30 天左右的数据。
# 如果你数据库里有两年数据，随机抽样会导致网页端匹配不到日期 -> valid=0。
# 这里提供按“年/月”请求的 URL 模板，尽量覆盖任意日期。
BASE_URL_MONTH = "https://tianqi.2345.com/wea_history/{code}.htm?y={y}&m={m}"  # 备用：若站点支持 y/m 参数可直接访问
# 说明：2345 实际页面往往通过“上一月/下一月”按钮翻页（JS/AJAX），纯 http 抓取不一定能拿到全部历史。
# 为保证自检接口稳定可用，这里默认只对“当前页面可见月份”（通常为当月）做一致性校验。


def _parse_page_rows(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="history-table")
    if not table:
        return []

    out = []
    for tr in table.find_all("tr")[1:]:
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 6:
            continue
        d = (tds[0] or "").split()[0]

        def to_f(s: str) -> Optional[float]:
            if s is None:
                return None
            ss = str(s).replace("℃", "").replace("°", "")
            ss = "".join(ch for ch in ss if (ch.isdigit() or ch in "- ."))
            try:
                return float(ss)
            except Exception:
                return None

        # 两种温度格式
        if "/" in (tds[1] or ""):
            parts = tds[1].split("/")
            max_t = to_f(parts[0])
            min_t = to_f(parts[1])
            weather = tds[2]
            wind = tds[3]
            aqi_text = tds[5]
        else:
            max_t = to_f(tds[1])
            min_t = to_f(tds[2])
            weather = tds[3]
            wind = tds[4]
            aqi_text = tds[5]

        aqi_num = "".join(ch for ch in str(aqi_text) if ch.isdigit())
        aqi = int(aqi_num) if aqi_num else None

        out.append({
            "date": d,
            "max_temp": max_t,
            "min_temp": min_t,
            "weather": weather,
            "wind": wind,
            "aqi": aqi,
        })
    return out


@dataclass
class ConsistencyItem:
    area: str
    date: str
    db_aqi: Optional[int]
    web_aqi: Optional[int]
    db_max_temp: Optional[float]
    web_max_temp: Optional[float]
    db_min_temp: Optional[float]
    web_min_temp: Optional[float]
    ok: bool


def check_web_consistency(sample_size: int = 5, timeout: int = 20, tolerate_missing: bool = True, recent_days: int = 30) -> Dict[str, Any]:
    """抽样检查数据库中的记录是否与网页展示一致。

    重要说明（为解决 selfcheck 里 valid=0 导致直接不通过的问题）：
    - 2345 的历史页常常只展示“近期一段时间”或需要分页/年份切换。
      如果从全库随机抽样，很容易抽到网页端当前页面没有的数据，导致 valid=0。
    - 因此这里默认只在最近 recent_days 天内抽样（可调），显著提升可匹配率。

    tolerate_missing:
    - True：如果网页缺少某天/解析失败，则这条样本不计入 fail（避免 100% fail）
    - False：严格模式，网页缺失也算 fail
    """

    with SessionLocal() as db:
        base_q = db.query(WeatherData)
        total_all = base_q.count()
        if total_all == 0:
            return {"ok": False, "error": "数据库无数据，无法校验"}

        q = base_q
        if recent_days and recent_days > 0:
            latest_date = db.query(func.max(WeatherData.date)).scalar()
            if latest_date is not None:
                start_date = (pd.to_datetime(latest_date) - pd.Timedelta(days=recent_days)).date()
                q = q.filter(WeatherData.date >= start_date)

        total = q.count()
        if total == 0:
            # 兜底：近期范围没有数据则退回全表抽样
            q = base_q
            total = total_all

        idxs = sorted(random.sample(range(total), k=min(sample_size, total)))
        samples = []
        for i in idxs:
            row = q.offset(i).limit(1).first()
            if row:
                samples.append(row)

    results: List[ConsistencyItem] = []

    # 用于统计：valid 表示“网页端确实找到了对应日期的数据”，才纳入误差率
    valid = 0

    with httpx.Client(timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}) as client:
        # 为了便于前端弹窗/自检提示：统计网页匹配不到的数量
        missing_cnt = 0
        for row in samples:
            area = row.area
            code = AREA_CODE.get(area)
            if not code:
                # 区域编码缺失：按严格/宽松策略处理
                if not tolerate_missing:
                    results.append(ConsistencyItem(
                        area=area,
                        date=str(row.date),
                        db_aqi=row.aqi,
                        web_aqi=None,
                        db_max_temp=row.max_temp,
                        web_max_temp=None,
                        db_min_temp=row.min_temp,
                        web_min_temp=None,
                        ok=False,
                    ))
                continue

            # 优先按“年/月”拉取对应月份的历史页，提升命中率；失败再退回默认页
            target_dt = pd.to_datetime(row.date)
            y = int(target_dt.year)
            m = int(target_dt.month)

            html = None
            try:
                r = client.get(BASE_URL_MONTH.format(code=code, y=y, m=m))
                r.raise_for_status()
                html = r.text
            except Exception:
                try:
                    r = client.get(BASE_URL.format(code=code))
                    r.raise_for_status()
                    html = r.text
                except Exception:
                    if not tolerate_missing:
                        results.append(ConsistencyItem(
                            area=area,
                            date=str(row.date),
                            db_aqi=row.aqi,
                            web_aqi=None,
                            db_max_temp=row.max_temp,
                            web_max_temp=None,
                            db_min_temp=row.min_temp,
                            web_min_temp=None,
                            ok=False,
                        ))
                    continue

            page_rows = _parse_page_rows(html or "")
            match = next((r for r in page_rows if r["date"] == str(row.date)), None)

            if not match:
                missing_cnt += 1
                # 网页没有该日期：通常是网页只展示近期/分页/历史不全
                # 宽松模式：不计入 fail；严格模式：记 fail
                if not tolerate_missing:
                    results.append(ConsistencyItem(
                        area=area,
                        date=str(row.date),
                        db_aqi=row.aqi,
                        web_aqi=None,
                        db_max_temp=row.max_temp,
                        web_max_temp=None,
                        db_min_temp=row.min_temp,
                        web_min_temp=None,
                        ok=False,
                    ))
                continue

            valid += 1

            ok = True
            if row.aqi is not None and match["aqi"] is not None and int(row.aqi) != int(match["aqi"]):
                ok = False
            if row.max_temp is not None and match["max_temp"] is not None and abs(float(row.max_temp) - float(match["max_temp"])) > 0.5:
                ok = False
            if row.min_temp is not None and match["min_temp"] is not None and abs(float(row.min_temp) - float(match["min_temp"])) > 0.5:
                ok = False

            results.append(ConsistencyItem(
                area=area,
                date=str(row.date),
                db_aqi=row.aqi,
                web_aqi=match["aqi"],
                db_max_temp=row.max_temp,
                web_max_temp=match["max_temp"],
                db_min_temp=row.min_temp,
                web_min_temp=match["min_temp"],
                ok=ok,
            ))

    pass_cnt = sum(1 for x in results if x.ok)
    fail_cnt = len(results) - pass_cnt

    # ---------------- 额外采样逻辑：确保 valid 不太低 ----------------
    if valid < sample_size and tolerate_missing:
        # 继续随机抽样，直到尝试次数达到上限或 valid>=sample_size
        max_extra_attempts = sample_size * 3  # 最多再访问 3 倍网页，避免无限循环
        attempts = 0
        while valid < sample_size and attempts < max_extra_attempts:
            attempts += 1
            # 随机再挑一条（不重复 area+date）
            extra_row = base_q.order_by(func.rand()).first()
            if not extra_row:
                break
            if any((it.area == extra_row.area and it.date == str(extra_row.date)) for it in results):
                continue

            # 直接对这条 extra_row 做一次网页比对（避免递归调用导致采样错位）
            area = extra_row.area
            code = AREA_CODE.get(area)
            if not code:
                continue

            target_dt = pd.to_datetime(extra_row.date)
            y = int(target_dt.year)
            m = int(target_dt.month)

            html = None
            try:
                r = client.get(BASE_URL_MONTH.format(code=code, y=y, m=m))
                r.raise_for_status()
                html = r.text
            except Exception:
                try:
                    r = client.get(BASE_URL.format(code=code))
                    r.raise_for_status()
                    html = r.text
                except Exception:
                    continue

            page_rows = _parse_page_rows(html or "")
            match = next((r for r in page_rows if r["date"] == str(extra_row.date)), None)
            if not match:
                continue

            valid += 1

            ok2 = True
            if extra_row.aqi is not None and match["aqi"] is not None and int(extra_row.aqi) != int(match["aqi"]):
                ok2 = False
            if extra_row.max_temp is not None and match["max_temp"] is not None and abs(float(extra_row.max_temp) - float(match["max_temp"])) > 0.5:
                ok2 = False
            if extra_row.min_temp is not None and match["min_temp"] is not None and abs(float(extra_row.min_temp) - float(match["min_temp"])) > 0.5:
                ok2 = False

            results.append(ConsistencyItem(
                area=area,
                date=str(extra_row.date),
                db_aqi=extra_row.aqi,
                web_aqi=match["aqi"],
                db_max_temp=extra_row.max_temp,
                web_max_temp=match["max_temp"],
                db_min_temp=extra_row.min_temp,
                web_min_temp=match["min_temp"],
                ok=ok2,
            ))

            if ok2:
                pass_cnt += 1
            else:
                fail_cnt += 1

    # -------------------------------------------------------------

    if valid == 0:
        return {
            "ok": False,
            "sample_size": len(results),
            "valid": 0,
            "pass": 0,
            "fail": 0,
            "error": "网页端未匹配到任何抽样日期（可能网页仅展示部分历史/分页/部分辖区无数据）",
            "items": [],
        }

    return {
        "ok": fail_cnt / valid <= 0.05,
        "sample_size": len(results),
        "valid": valid,
        "pass": pass_cnt,
        "fail": fail_cnt,
        "items": [asdict(x) for x in results],
    }


# --------------------- 2) 预测 vs 实际 的误差评估 ---------------------


def _mape(y_true: List[float], y_pred: List[float]) -> float:
    eps = 1e-9
    arr = []
    for a, p in zip(y_true, y_pred):
        if a is None:
            continue
        denom = abs(a) if abs(a) > eps else eps
        arr.append(abs(a - p) / denom)
    if not arr:
        return float('nan')
    return float(sum(arr) / len(arr))


def evaluate_forecast_error(area: str, backtest_days: int = 30, threshold: float = 0.7) -> Dict[str, Any]:
    """回测预测误差（MAPE <= threshold 则通过）。"""

    # 避免循环导入：延迟导入
    from api_server import _load_df_from_db

    df = _load_df_from_db(area=area, start=None, end=None)
    if df.empty:
        return {"ok": False, "error": "无历史数据"}

    df = df.sort_values("date").dropna(subset=["aqi"])
    df["date"] = pd.to_datetime(df["date"])

    if len(df) < 90:
        return {"ok": False, "error": "样本过少，建议至少 90 天数据后再评估"}

    end_date = df["date"].max()
    start_eval = end_date - pd.Timedelta(days=backtest_days)

    points = []
    y_true = []
    y_pred = []

    for d in pd.date_range(start=start_eval, end=end_date - pd.Timedelta(days=1), freq="D"):
        train = df[df["date"] <= d].copy()
        res = forecast_aqi_7_days(train, horizon=1)
        if res.get("error"):
            continue
        pred = float(res["forecast"][0]["aqi_p50"])

        real_row = df[df["date"] == d + pd.Timedelta(days=1)]
        if real_row.empty:
            continue
        real = float(real_row.iloc[0]["aqi"])

        points.append({"date": str((d + pd.Timedelta(days=1)).date()), "real": real, "pred": pred})
        y_true.append(real)
        y_pred.append(pred)

    mape = _mape(y_true, y_pred)
    passed = (mape <= threshold) if mape == mape else False

    return {
        "ok": True,
        "area": area,
        "backtest_days": backtest_days,
        "mape": mape,
        "threshold": threshold,
        "pass": passed,
        "points": points,
    }

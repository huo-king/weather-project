"""api_server.py

【教学版说明】
这是本项目的 FastAPI 后端入口文件，主要做 3 件事：
1) 提供“基础气象/AQI查询接口”（给前端 ECharts 画趋势图/对比图/散点图用）
2) 提供“高级分析接口”（线性回归、风向/风力统计、三因素热力图、未来7日预测）
3) 提供“用户系统接口”（注册/登录/JWT鉴权、收藏、历史查询）

【运行方式】
- 方式B：直接右键运行本文件
  python api_server.py

【访问地址】
- 前端页面： http://127.0.0.1:8000/
- 接口文档： http://127.0.0.1:8000/docs

------------------------------------------------------------
【接口目录】
一、基础接口
- GET /api/areas                         获取所有可选区域（含“广州（全市）”）
- GET /api/trend/aqi                     AQI趋势（按天）
- GET /api/trend/temp                    温度趋势（最高/最低）
- GET /api/compare/aqi                   各区平均AQI对比
- GET /api/correlation/temp_aqi          温度与AQI相关性（r + p + n）

二、高级分析
- GET /api/analysis/linear_regression    线性回归：AQI与温度/风/天气等关系
- GET /api/analysis/wind_vs_aqi          风力等级/风向 与 AQI 统计
- GET /api/analysis/multi_factor         三因素热力图数据（温度×风力×天气）
- GET /api/analysis/forecast_7d          未来7天AQI预测（分位数区间）

三、用户系统
- POST /api/users/register               注册
- POST /api/users/login                  登录（返回JWT token）
- GET  /api/users/me                     当前用户信息（需要token）
- POST /api/users/password_reset/request 申请重置密码（演示：返回token）
- POST /api/users/password_reset/confirm 确认重置
- GET/POST/DELETE /api/users/favorites   收藏管理（需要token）
- GET/POST /api/users/history            历史查询（最多保留30条，需要token）
"""

from __future__ import annotations

# ---------------------
# 1. 标准库导入
# ---------------------
from datetime import date
from pathlib import Path
from typing import Optional, Dict, Any, List

# ---------------------
# 2. 第三方库导入
# ---------------------
import pandas as pd

# FastAPI 相关
from fastapi import FastAPI, Query, HTTPException, Request, Depends
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

# SQLAlchemy（数据库ORM）
from sqlalchemy import select, func, and_
from fastapi.responses import StreamingResponse

from services.aggregation import aggregate_series
from services.export_service import build_export_df, df_to_csv_bytes, build_content_disposition
from sqlalchemy.orm import Session

# SciPy：用于 Pearson 相关系数显著性检验（p 值）
from scipy.stats import pearsonr

# ---------------------
# 3. 项目内部模块导入
# ---------------------
from database import SessionLocal, engine
import models
from models import WeatherData, User, UserFavorite, SearchHistory, SocialInteraction

# 高级分析函数
from analysis import (
    train_aqi_prediction_model,
    analyze_wind_vs_aqi,
    analyze_multi_factor_relationship,
    forecast_aqi_7_days,
)

import schemas_predict

# 用户系统（Pydantic模型、JWT/密码哈希）
import schemas
import auth


# 采集服务（B方案：手动触发）
from services.scrape_service import run_scrape_once

# 质量自检服务
from services.quality_checks import check_web_consistency, evaluate_forecast_error


# ============================================================
# FastAPI App 初始化
# ============================================================
app = FastAPI(title="Guangzhou Weather & AQI API", version="0.4.0")

# 首次启动时自动创建表结构
models.Base.metadata.create_all(bind=engine)


# ============================================================
# 前端页面托管
# ============================================================
BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """主页：返回 index.html"""
    return templates.TemplateResponse("index.html", {"request": request})


# ============================================================
# CORS 设置
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 工具函数
# ============================================================

def _parse_date(s: Optional[str], field_name: str) -> Optional[date]:
    """解析日期字符串（YYYY-MM-DD）为 date。"""
    if s is None or s == "":
        return None
    try:
        return pd.to_datetime(s).date()
    except Exception:
        raise HTTPException(status_code=400, detail=f"{field_name} 日期格式不正确：{s}，期望 YYYY-MM-DD")


def _area_filter(area: str) -> Optional[str]:
    """把“广州/全市”等转换为 None（表示不过滤区域）。"""
    if area in ("广州", "广州市", "全市", "全部", "all", "ALL"):
        return None
    return area


def _load_df_from_db(area: str, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
    """从 MySQL 拉取用于分析/建模的数据，并转成 DataFrame。"""
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    area_real = _area_filter(area)

    with SessionLocal() as db:
        stmt = select(
            WeatherData.date,
            WeatherData.max_temp,
            WeatherData.min_temp,
            WeatherData.weather,
            WeatherData.wind,
            WeatherData.aqi,
        )

        conds = []
        if area_real:
            conds.append(WeatherData.area == area_real)
        if start_d:
            conds.append(WeatherData.date >= start_d)
        if end_d:
            conds.append(WeatherData.date <= end_d)
        if conds:
            stmt = stmt.where(and_(*conds))

        rows = db.execute(stmt).all()

    return pd.DataFrame(rows, columns=["date", "max_temp", "min_temp", "weather", "wind", "aqi"])


def get_db() -> Session:
    """FastAPI 依赖注入：返回 Session。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 允许社交统计接口在未登录时也可调用：token 可选
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/users/login", auto_error=False)

def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """获取当前用户（可选）。

    - 未登录 / token 无效：返回 None
    - 已登录且 token 有效：返回 User
    """
    if not token:
        return None
    try:
        from jose import jwt
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            return None
        user = db.query(User).filter(User.email == email).first()
        return user
    except Exception:
        return None


# ============================================================
# 管理/采集接口（B方案：手动触发，不影响原功能）
# ============================================================

@app.post("/api/admin/scrape_now")
def admin_scrape_now() -> Dict[str, Any]:
    """手动触发一次数据采集。

    说明：
    - 该接口不会自动定时运行，完全由你手动触发（B方案）。
    - 为了不影响你现有功能，这里不做复杂权限控制；如需更严格，可改为仅管理员可调用。

    返回：
    - ok: 是否成功
    - inserted: 插入数据库的新记录条数
    - total_scraped: 本次爬到的原始记录条数
    - started_at/finished_at: UTC时间
    - error: 失败原因（如有）
    """
    return run_scrape_once()


# ============================================================
# 社交按钮接口（五角星/爱心/加号：收藏/点赞/关注）
# ============================================================

@app.get("/api/social/stats")
def social_stats(area: str = Query("广州"), current_user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    """获取某区域的点赞/收藏/关注统计及当前用户是否已点过。"""

    # 统计总数
    like_count = db.query(SocialInteraction).filter(SocialInteraction.area == area, SocialInteraction.interaction_type == "like").count()
    fav_count = db.query(SocialInteraction).filter(SocialInteraction.area == area, SocialInteraction.interaction_type == "favorite").count()
    follow_count = db.query(SocialInteraction).filter(SocialInteraction.area == area, SocialInteraction.interaction_type == "follow").count()

    # 若没登录，则所有 active=false
    if not current_user:
        return {
            "area": area,
            "like": {"count": like_count, "active": False},
            "favorite": {"count": fav_count, "active": False},
            "follow": {"count": follow_count, "active": False},
        }

    # 已登录：查询是否已操作
    def has_it(t: str) -> bool:
        return db.query(SocialInteraction).filter(
            SocialInteraction.user_id == current_user.id,
            SocialInteraction.area == area,
            SocialInteraction.interaction_type == t,
        ).first() is not None

    return {
        "area": area,
        "like": {"count": like_count, "active": has_it("like")},
        "favorite": {"count": fav_count, "active": has_it("favorite")},
        "follow": {"count": follow_count, "active": has_it("follow")},
    }


@app.post("/api/social/toggle")
def social_toggle(payload: Dict[str, Any], current_user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """点赞/收藏/关注：点击一次切换（有则取消，无则新增）。"""

    area = (payload.get("area") or "广州").strip()
    t = (payload.get("type") or "").strip()

    if t not in ("like", "favorite", "follow"):
        raise HTTPException(status_code=400, detail="type 必须是 like/favorite/follow")

    # 查找是否已存在
    existing = db.query(SocialInteraction).filter(
        SocialInteraction.user_id == current_user.id,
        SocialInteraction.area == area,
        SocialInteraction.interaction_type == t,
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        active = False
    else:
        item = SocialInteraction(user_id=current_user.id, area=area, interaction_type=t)
        db.add(item)
        db.commit()
        active = True

    # 返回最新总数
    count = db.query(SocialInteraction).filter(SocialInteraction.area == area, SocialInteraction.interaction_type == t).count()
    return {"ok": True, "area": area, "type": t, "count": count, "active": active}


# ============================================================
# 导出/下载接口
# ============================================================

@app.get("/api/export/weather_data.csv")
def export_weather_data_csv(area: str = Query("广州"), start: Optional[str] = None, end: Optional[str] = None, db: Session = Depends(get_db)):
    """导出原始天气数据为 CSV。

    说明：
    - area=广州 表示导出全市所有区；否则导出单个区。
    - start/end 支持为空。
    """
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    area_real = _area_filter(area)

    df = build_export_df(db=db, area=area_real, start_d=start_d, end_d=end_d)
    content = df_to_csv_bytes(df)

    filename_utf8 = f"weather_data_{area}_{start_d or ''}_{end_d or ''}.csv".replace(":", "-")

    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": build_content_disposition(filename_utf8)},
    )


# ============================================================
# 质量自检接口（数据一致性 + 预测误差阈值）
# ============================================================

@app.get("/api/quality/web_consistency")
def api_quality_web_consistency(sample_size: int = 5, recent_days: int = 7):
    """抽样检查：数据库数据是否与网站展示一致。

    说明：
    - 默认启用 tolerate_missing=True：网页端缺失/无法匹配的样本不计入 fail
    - 并尝试自动补抽样，尽量让 valid 更接近 sample_size
    """
    return check_web_consistency(sample_size=sample_size, tolerate_missing=True, recent_days=recent_days)


@app.get("/api/quality/forecast_eval")
def api_quality_forecast_eval(area: str = Query("广州"), backtest_days: int = 30, threshold: float = 0.7):
    """回测评估：预测 vs 实际误差（默认要求不超过70%）。"""
    return evaluate_forecast_error(area=area, backtest_days=backtest_days, threshold=threshold)


# ============================================================
# 基础数据接口
# ============================================================

@app.get("/api/areas")
def list_areas() -> Dict[str, Any]:
    """获取区域列表（含“广州”虚拟项）。"""
    with SessionLocal() as db:
        rows = db.execute(select(WeatherData.area).distinct().order_by(WeatherData.area)).all()
        areas = [r[0] for r in rows]
    return {"areas": ["广州"] + areas}


@app.get("/api/trend/aqi")
def trend_aqi(area: str = Query("广州"), start: Optional[str] = None, end: Optional[str] = None, granularity: str = Query("day", description="day/week/month")) -> Dict[str, Any]:
    """AQI趋势（按天）。"""
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    area_real = _area_filter(area)

    with SessionLocal() as db:
        if area_real:
            stmt = select(WeatherData.date, WeatherData.aqi).where(WeatherData.area == area_real)
            if start_d:
                stmt = stmt.where(WeatherData.date >= start_d)
            if end_d:
                stmt = stmt.where(WeatherData.date <= end_d)
            stmt = stmt.order_by(WeatherData.date.asc())
            rows = db.execute(stmt).all()
            df = pd.DataFrame(rows, columns=["date", "aqi"]).dropna(subset=["date"])
            # 这里的区级数据本身就是 aqi，不需要改名
            if not df.empty and granularity != "day":
                df = aggregate_series(df, granularity=granularity, agg="mean")

            x = [d.isoformat() for d in df["date"].tolist()]
            y = [round(v, 2) if v is not None else None for v in df["aqi"].tolist()]
            return {"area": area, "granularity": granularity, "x": x, "y": y}

        stmt = select(WeatherData.date, func.avg(WeatherData.aqi).label("aqi_avg")).group_by(WeatherData.date)
        if start_d:
            stmt = stmt.where(WeatherData.date >= start_d)
        if end_d:
            stmt = stmt.where(WeatherData.date <= end_d)
        stmt = stmt.order_by(WeatherData.date.asc())
        rows = db.execute(stmt).all()
        df = pd.DataFrame(rows, columns=["date", "aqi_avg"]).dropna(subset=["date"])
        df = df.rename(columns={"aqi_avg": "aqi"})
        if not df.empty and granularity != "day":
            df = aggregate_series(df, granularity=granularity, agg="mean")

        x = [d.isoformat() for d in df["date"].tolist()]
        y = [round(v, 2) if v is not None else None for v in df["aqi"].tolist()]
        return {"area": area, "granularity": granularity, "x": x, "y": y}


@app.get("/api/trend/temp")
def trend_temp(area: str = Query("广州"), start: Optional[str] = None, end: Optional[str] = None, granularity: str = Query("day", description="day/week/month")) -> Dict[str, Any]:
    """温度趋势（最高/最低）。"""
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    area_real = _area_filter(area)

    with SessionLocal() as db:
        if area_real:
            stmt = select(WeatherData.date, WeatherData.max_temp, WeatherData.min_temp).where(WeatherData.area == area_real)
            if start_d:
                stmt = stmt.where(WeatherData.date >= start_d)
            if end_d:
                stmt = stmt.where(WeatherData.date <= end_d)
            stmt = stmt.order_by(WeatherData.date.asc())
            rows = db.execute(stmt).all()
            df = pd.DataFrame(rows, columns=["date", "max_temp", "min_temp"]).dropna(subset=["date"])
            if not df.empty and granularity != "day":
                df = aggregate_series(df, granularity=granularity, agg="mean")

            x = [d.isoformat() for d in df["date"].tolist()]
            y1 = [round(v, 2) if v is not None else None for v in df["max_temp"].tolist()]
            y2 = [round(v, 2) if v is not None else None for v in df["min_temp"].tolist()]
            return {"area": area, "granularity": granularity, "x": x, "max": y1, "min": y2}

        stmt = (
            select(
                WeatherData.date,
                func.avg(WeatherData.max_temp).label("max_avg"),
                func.avg(WeatherData.min_temp).label("min_avg"),
            )
            .group_by(WeatherData.date)
            .order_by(WeatherData.date.asc())
        )
        if start_d:
            stmt = stmt.where(WeatherData.date >= start_d)
        if end_d:
            stmt = stmt.where(WeatherData.date <= end_d)
        rows = db.execute(stmt).all()
        df = pd.DataFrame(rows, columns=["date", "max_temp", "min_temp"]).dropna(subset=["date"])
        if not df.empty and granularity != "day":
            df = aggregate_series(df, granularity=granularity, agg="mean")

        x = [d.isoformat() for d in df["date"].tolist()]
        y1 = [round(v, 2) if v is not None else None for v in df["max_temp"].tolist()]
        y2 = [round(v, 2) if v is not None else None for v in df["min_temp"].tolist()]
        return {"area": area, "granularity": granularity, "x": x, "max": y1, "min": y2}


@app.get("/api/compare/aqi")
def compare_aqi(start: Optional[str] = None, end: Optional[str] = None, granularity: str = Query("day", description="day/week/month")) -> Dict[str, Any]:
    """各区平均AQI对比（柱状图数据）。"""
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")

    with SessionLocal() as db:
        if granularity == "day":
            # 原逻辑：直接对时间范围内所有天求平均
            stmt = select(WeatherData.area, func.avg(WeatherData.aqi).label("aqi_avg")).group_by(WeatherData.area)
            if start_d:
                stmt = stmt.where(WeatherData.date >= start_d)
            if end_d:
                stmt = stmt.where(WeatherData.date <= end_d)
            stmt = stmt.order_by(func.avg(WeatherData.aqi).desc())
            rows = db.execute(stmt).all()
            data = [{"area": r[0], "aqi_avg": round(float(r[1]), 2) if r[1] is not None else None} for r in rows]
        else:
            # week/month：先按天取各区 AQI，再在 pandas 里按 week/month 聚合
            stmt = select(WeatherData.area, WeatherData.date, WeatherData.aqi)
            conds = []
            if start_d:
                conds.append(WeatherData.date >= start_d)
            if end_d:
                conds.append(WeatherData.date <= end_d)
            if conds:
                stmt = stmt.where(and_(*conds))
            rows = db.execute(stmt).all()
            df = pd.DataFrame(rows, columns=["area", "date", "aqi"]).dropna(subset=["date", "aqi"])
            if df.empty:
                data = []
            else:
                # 对每个区做聚合，再取聚合后的均值用于对比
                parts = []
                for a, g in df.groupby("area"):
                    g2 = aggregate_series(g[["date", "aqi"]], granularity=granularity, agg="mean")
                    parts.append({"area": a, "aqi_avg": float(g2["aqi"].mean()) if not g2.empty else None})
                data = sorted(parts, key=lambda x: (x["aqi_avg"] is None, -(x["aqi_avg"] or 0)))

    return {
        "start": start_d.isoformat() if start_d else None,
        "end": end_d.isoformat() if end_d else None,
        "granularity": granularity,
        "data": data,
    }


@app.get("/api/correlation/temp_aqi")
def correlation_temp_aqi(area: str = Query("广州"), start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    """温度与 AQI 相关性：散点数据 + Pearson r + p + n。"""
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    area_real = _area_filter(area)

    with SessionLocal() as db:
        stmt = select(WeatherData.date, WeatherData.max_temp, WeatherData.min_temp, WeatherData.aqi)
        conds = []
        if area_real:
            conds.append(WeatherData.area == area_real)
        if start_d:
            conds.append(WeatherData.date >= start_d)
        if end_d:
            conds.append(WeatherData.date <= end_d)
        if conds:
            stmt = stmt.where(and_(*conds))

        rows = db.execute(stmt).all()

    if not rows:
        return {"area": area, "corr_max_aqi": None, "corr_min_aqi": None, "p_max_aqi": None, "p_min_aqi": None, "n": 0, "points_max": [], "points_min": []}

    df = pd.DataFrame(rows, columns=["date", "max_temp", "min_temp", "aqi"]).dropna()
    if df.empty:
        return {"area": area, "corr_max_aqi": None, "corr_min_aqi": None, "p_max_aqi": None, "p_min_aqi": None, "n": 0, "points_max": [], "points_min": []}

    r_max, p_max = pearsonr(df["max_temp"].astype(float), df["aqi"].astype(float))
    r_min, p_min = pearsonr(df["min_temp"].astype(float), df["aqi"].astype(float))

    return {
        "area": area,
        "corr_max_aqi": round(float(r_max), 4),
        "corr_min_aqi": round(float(r_min), 4),
        "p_max_aqi": float(p_max),
        "p_min_aqi": float(p_min),
        "n": int(len(df)),
        "points_max": df[["max_temp", "aqi"]].values.tolist(),
        "points_min": df[["min_temp", "aqi"]].values.tolist(),
    }


@app.get("/api/analysis/selfcheck")
def analysis_selfcheck(
    area: str = Query("广州"),
    backtest_days: int = 7,
    threshold: float = 0.3,
    web_sample_size: int = 20,
    web_error_rate_limit: float = 0.05,
):
    """综合自检：

    1) 对比爬取数据与 2345 天气网原始数据：不一致率 <= 5%
    2) 验证 AQI 预测与实际偏差：7 天内预测准确率不低于 70%
       - 这里用 MAPE <= 30% 作为“准确率>=70%”的等价判据

    返回：
    - web_consistency: 网站一致性抽检结果
    - forecast_eval: 预测回测评估结果
    - ok: 两项都通过才算通过
    """

    # 默认采用“宽松模式”：网页端缺失/匹配不到日期不计入 fail（否则很容易 100% fail）
    # 说明：2345 历史页常通过翻页加载更早月份，纯 http 抓取无法可靠获取两年全量。
    # 自检采用“近期可见月份”抽检，避免 valid=0 造成误判。
    web = check_web_consistency(sample_size=web_sample_size, tolerate_missing=True, recent_days=7)

    # 网站一致性：不一致率 = fail / valid（valid 表示网页端能匹配到日期的样本数）
    web_error_rate = None
    web_pass = False
    if web.get("valid"):
        web_error_rate = (web.get("fail", 0) / max(1, web.get("valid", 1)))
        web_pass = (web_error_rate <= web_error_rate_limit)
    else:
        web_pass = False

    forecast = evaluate_forecast_error(area=area, backtest_days=backtest_days, threshold=threshold)

    # 预测是否通过：后端函数返回字段名是 pass
    forecast_pass = bool(forecast.get("pass")) if forecast.get("ok") else False

    return {
        "ok": bool(web_pass and forecast_pass),
        "area": area,
        "web_consistency": {
            **web,
            "error_rate": web_error_rate,
            "limit": web_error_rate_limit,
            "pass": web_pass,
        },
        "forecast_eval": forecast,
    }


# ============================================================
# 高级分析接口
# ============================================================

@app.get("/api/analysis/linear_regression")
def analysis_linear_regression(area: str = Query("广州"), start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    df = _load_df_from_db(area=area, start=start, end=end)
    if df.empty:
        return {"area": area, "error": "查询条件下无数据"}
    return {"area": area, **train_aqi_prediction_model(df)}


@app.get("/api/analysis/wind_vs_aqi")
def analysis_wind_vs_aqi(area: str = Query("广州"), start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    df = _load_df_from_db(area=area, start=start, end=end)
    if df.empty:
        return {"area": area, "speed_analysis": [], "direction_analysis": []}
    return {"area": area, **analyze_wind_vs_aqi(df)}


@app.get("/api/analysis/multi_factor")
def analysis_multi_factor(area: str = Query("广州"), start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    df = _load_df_from_db(area=area, start=start, end=end)
    if df.empty:
        return {"area": area, "heatmap_data": []}
    return {"area": area, "heatmap_data": analyze_multi_factor_relationship(df)}


@app.get("/api/analysis/forecast_7d")
def analysis_forecast_7d(area: str = Query("广州"), start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    """未来7天 AQI 预测（分位数区间）。

    说明：
    - area 传具体区名：按该区历史数据预测
    - area=广州：目前按全市平均 AQI 序列进行预测（通过 SQL 聚合后再喂给模型）
    """

    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    area_real = _area_filter(area)

    # 1) 如果是具体区：直接用原始序列
    if area_real:
        df = _load_df_from_db(area=area, start=start, end=end)
        if df.empty:
            return {"area": area, "error": "查询条件下无数据"}
        result = forecast_aqi_7_days(df)
        return {"area": area, **result}

    # 2) 如果是全市：先按天聚合出全市平均 AQI，再构造一个 DataFrame 供模型使用
    with SessionLocal() as db:
        stmt = select(
            WeatherData.date,
            func.avg(WeatherData.max_temp).label("max_temp"),
            func.avg(WeatherData.min_temp).label("min_temp"),
            func.avg(WeatherData.aqi).label("aqi"),
            # wind/weather 作为文本难以聚合，这里用 None 占位，模型主要依赖 lag
        ).group_by(WeatherData.date)
        if start_d:
            stmt = stmt.where(WeatherData.date >= start_d)
        if end_d:
            stmt = stmt.where(WeatherData.date <= end_d)
        stmt = stmt.order_by(WeatherData.date.asc())
        rows = db.execute(stmt).all()

    if not rows:
        return {"area": area, "error": "查询条件下无数据"}

    df = pd.DataFrame(rows, columns=["date", "max_temp", "min_temp", "aqi"])

    # 预测模型还需要 wind/weather 字段，给个默认占位
    df["wind"] = "北风1级"
    df["weather"] = "多云"

    result = forecast_aqi_7_days(df)
    return {"area": area, **result}


@app.post("/api/predict/aqi_7d", response_model=schemas_predict.AQI7dPredictResponse)
def predict_aqi_7d(payload: schemas_predict.AQI7dPredictRequest):
    """支持“输入实时气象参数”的7天AQI预测。

    - payload.area: 区域
    - payload.meteo_7d: 可选，长度=7，包含 max_temp/min_temp/wind_speed

    返回：
    - forecast: 7天预测（含区间、等级、提示、置信度）
    """

    area = payload.area or "广州"
    # 取近一段历史数据用于训练/构造 lag
    df_hist = _load_df_from_db(area=area, start=None, end=None)
    if df_hist.empty:
        raise HTTPException(status_code=400, detail="该区域无历史数据，无法预测")

    future = None
    if payload.meteo_7d:
        if len(payload.meteo_7d) != 7:
            raise HTTPException(status_code=400, detail="meteo_7d 必须为长度 7")
        future = [
            {"max_temp": d.max_temp, "min_temp": d.min_temp, "wind_speed": d.wind_speed}
            for d in payload.meteo_7d
        ]

    result = forecast_aqi_7_days(df_hist, future_meteo_7d=future)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    return {"area": area, **result}


# ============================================================
# 用户系统接口
# ============================================================

@app.post("/api/users/register", response_model=schemas.UserOut)
def user_register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="邮箱已注册")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=auth.get_password_hash(payload.password),
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/users/login", response_model=schemas.TokenOut)
def user_login(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    if not auth.verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = auth.create_access_token({"sub": user.email})
    return schemas.TokenOut(access_token=token)


@app.get("/api/users/me", response_model=schemas.UserOut)
def user_me(current_user: User = Depends(auth.get_current_user)):
    return current_user


@app.get("/api/users/preferred_areas", response_model=schemas.PreferredAreasUpdate)
def preferred_areas_get(current_user: User = Depends(auth.get_current_user)):
    """获取当前用户的常用辖区（最多3个）。"""
    return {"areas": current_user.preferred_areas or []}


@app.put("/api/users/preferred_areas", response_model=schemas.PreferredAreasUpdate)
def preferred_areas_update(
    payload: schemas.PreferredAreasUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth.get_current_user),
):
    """更新当前用户的常用辖区（最多3个）。

    注意：
    - auth.get_current_user 内部会自己 Depends(get_db) 拿一个 Session。
    - 而本接口又单独 Depends(get_db) 拿了另一个 Session。
    - 因此 current_user 绑定的 Session 与这里的 db 可能不是同一个，
      直接 db.refresh(current_user) 会报：Instance is not persistent within this Session。

    解决：用当前接口的 db 再查一次用户对象，然后更新/commit。
    """

    areas = payload.areas or []

    # 去空 + 去重（保序）+ 截断到3个
    seen = set()
    norm: List[str] = []
    for a in areas:
        a = (a or "").strip()
        if not a:
            continue
        if a in seen:
            continue
        seen.add(a)
        norm.append(a)
    norm = norm[:3]

    # 用当前 Session 重新加载 user，确保对象 persistent in this Session
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.preferred_areas = norm
    db.commit()
    db.refresh(user)
    return {"areas": user.preferred_areas or []}


@app.post("/api/users/password_reset/request")
def password_reset_request(payload: schemas.PasswordResetRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="邮箱不存在")

    reset_token = auth.create_access_token({"sub": user.email, "type": "pwd_reset"})
    return {"reset_token": reset_token}


@app.post("/api/users/password_reset/confirm")
def password_reset_confirm(payload: schemas.PasswordResetConfirm, db: Session = Depends(get_db)):
    try:
        from jose import jwt
        decoded = jwt.decode(payload.token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        if decoded.get("type") != "pwd_reset":
            raise HTTPException(status_code=400, detail="token类型不正确")
        email = decoded.get("sub")
        if not email:
            raise HTTPException(status_code=400, detail="token无效")
    except Exception:
        raise HTTPException(status_code=400, detail="token无效或已过期")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.hashed_password = auth.get_password_hash(payload.new_password)
    db.commit()
    return {"ok": True}


@app.get("/api/users/favorites", response_model=List[schemas.FavoriteOut])
def favorites_list(current_user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(UserFavorite)
        .filter(UserFavorite.user_id == current_user.id)
        .order_by(UserFavorite.created_at.desc())
        .all()
    )


@app.post("/api/users/favorites", response_model=schemas.FavoriteOut)
def favorites_add(payload: schemas.FavoriteCreate, current_user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    existing = db.query(UserFavorite).filter(
        UserFavorite.user_id == current_user.id,
        UserFavorite.chart_type == payload.chart_type,
        UserFavorite.area == payload.area,
    ).first()
    if existing:
        return existing

    fav = UserFavorite(user_id=current_user.id, chart_type=payload.chart_type, area=payload.area)
    db.add(fav)
    db.commit()
    db.refresh(fav)
    return fav


@app.delete("/api/users/favorites/{favorite_id}")
def favorites_delete(favorite_id: int, current_user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    fav = db.query(UserFavorite).filter(UserFavorite.id == favorite_id, UserFavorite.user_id == current_user.id).first()
    if not fav:
        raise HTTPException(status_code=404, detail="收藏不存在")
    db.delete(fav)
    db.commit()
    return {"ok": True}


@app.get("/api/users/history", response_model=List[schemas.HistoryOut])
def history_list(current_user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == current_user.id)
        .order_by(SearchHistory.searched_at.desc())
        .limit(30)
        .all()
    )


@app.post("/api/users/history")
def history_add(payload: schemas.HistoryCreate, current_user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    params = {"area": payload.area, "start": payload.start, "end": payload.end, "extra": payload.extra}
    item = SearchHistory(user_id=current_user.id, search_params=params)
    db.add(item)
    db.commit()

    # 超过30条则删除最旧的
    ids = (
        db.query(SearchHistory.id)
        .filter(SearchHistory.user_id == current_user.id)
        .order_by(SearchHistory.searched_at.desc())
        .all()
    )
    ids = [x[0] for x in ids]
    if len(ids) > 30:
        to_delete = ids[30:]
        db.query(SearchHistory).filter(SearchHistory.id.in_(to_delete)).delete(synchronize_session=False)
        db.commit()

    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, reload=True)

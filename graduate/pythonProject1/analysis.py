"""analysis.py

【教学版说明】
本文件专门放“数据分析 / 机器学习”相关的代码，主要服务于 api_server.py 中的高级分析接口。

为什么要单独拆一个文件？
- api_server.py 主要负责“路由/接口”，不适合放太多数据处理细节。
- analysis.py 负责“怎么从数据中提取特征、怎么建模、怎么统计”，结构更清晰。

本文件实现了 4 类能力：
1) 特征工程：从原始字段 wind/weather 中提取 wind_speed / wind_direction / weather_simple 等可用特征
2) 解释性建模（线性回归）：用温度、风力、风向、天气类型解释 AQI，并返回 R²、RMSE、特征系数等
3) 描述性统计：
   - 风力等级 vs AQI（均值/中位数/样本量）
   - 风向 vs AQI（均值/中位数/样本量）
   - 三因素热力图：温度分箱 × 风力分箱 × 天气类型 -> 平均AQI
4) 未来 7 日 AQI 预测（时序回归）：
   - 基于历史 AQI + 气象变量构建滞后特征（lag）与时间特征（dow/month）
   - 使用 LightGBM 训练模型
   - 采用分位数回归（quantile regression）输出预测区间（下界/中位数/上界）

注意：
- 7日预测属于“数据驱动”的统计预测，受数据时间跨度、缺失值、外部排放影响等限制。
- 由于数据中没有真实未来 7 天的气象预报，我们默认“未来气象使用最近观测/短期持平假设”，
  因此预测更偏向于基于历史 AQI 模式的短期推断。
"""

# ---------------------
# 1. 依赖导入
# ---------------------
import re
from datetime import timedelta
from typing import Dict, Any, Optional, List

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import train_test_split

# LightGBM：用于时序回归预测（比线性回归更灵活）
import lightgbm as lgb


# ============================================================
# 一、风信息解析
# ============================================================

def _extract_wind_speed_and_direction(wind_str):
    """从 wind 字段中提取“风力等级”和“风向”。

    输入示例：
    - wind_str = "东北风3级"

    输出：
    - (wind_speed=3, wind_direction="东北风")

    为什么要做这个？
    - 原始 wind 字段是文本，机器学习模型无法直接使用。
    - 我们需要把它拆成结构化特征：风力等级（数值）+ 风向（类别）。
    """

    if not isinstance(wind_str, str):
        return None, None

    # 解析风向：删掉数字和“级”
    direction = re.sub(r"\d+", "", wind_str)
    direction = direction.replace("级", "").strip()

    # 解析风力等级：提取数字
    speed_match = re.search(r"(\d+)", wind_str)
    speed = int(speed_match.group(1)) if speed_match else None

    return speed, direction


# ============================================================
# 二、通用预处理函数
# ============================================================

def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    """对分析/建模数据进行统一预处理。

    输入 df 应包含字段（来自 api_server._load_df_from_db）：
    - date, max_temp, min_temp, weather, wind, aqi

    输出 df 会新增：
    - wind_speed: 风力等级（数值型）
    - wind_direction: 风向（类别）
    - weather_simple: 天气类型简化（类别）

    处理流程：
    1) 复制 df，避免修改原始对象
    2) wind -> wind_speed + wind_direction
    3) weather -> weather_simple（取“~”前面的主天气）
    4) 丢弃关键字段缺失的数据
    5) 转换数值列的类型，无法转换的设为 NaN 并再次丢弃
    """

    df_copy = df.copy()

    # wind -> wind_speed, wind_direction
    wind_info = df_copy["wind"].apply(_extract_wind_speed_and_direction)
    df_copy["wind_speed"] = wind_info.apply(lambda x: x[0])
    df_copy["wind_direction"] = wind_info.apply(lambda x: x[1])

    # weather -> weather_simple
    df_copy["weather_simple"] = df_copy["weather"].apply(
        lambda x: str(x).split("~")[0].strip() if isinstance(x, str) else "未知"
    )

    # 删除关键字段为空的行
    df_copy = df_copy.dropna(subset=["max_temp", "min_temp", "wind_speed", "aqi"])

    # 数值字段转型
    df_copy["wind_speed"] = pd.to_numeric(df_copy["wind_speed"], errors="coerce")
    df_copy["max_temp"] = pd.to_numeric(df_copy["max_temp"], errors="coerce")
    df_copy["min_temp"] = pd.to_numeric(df_copy["min_temp"], errors="coerce")
    df_copy["aqi"] = pd.to_numeric(df_copy["aqi"], errors="coerce")

    # 再次清除 NaN，保证可用于建模
    df_copy = df_copy.dropna(subset=["max_temp", "min_temp", "wind_speed", "aqi"])

    # date 转 datetime（用于构建时间特征）
    if "date" in df_copy.columns:
        df_copy["date"] = pd.to_datetime(df_copy["date"], errors="coerce")

    return df_copy


# ============================================================
# 三、线性回归：AQI 解释性建模
# ============================================================

def train_aqi_prediction_model(df: pd.DataFrame) -> dict:
    """训练线性回归模型，用气象因素解释/预测 AQI。

    注意：
    - 这个函数偏“解释性”，不是严格意义的未来预测。

    返回：
    - model_score_r2, rmse, intercept, top_features
    - scatter_data（实际 vs 预测）
    """

    df_processed = preprocess_data(df)

    if len(df_processed) < 30:
        return {"error": "数据不足（<30条），无法训练模型。"}

    # One-hot 编码
    df_encoded = pd.get_dummies(
        df_processed,
        columns=["weather_simple", "wind_direction"],
        prefix=["weather", "wind_dir"],
        dummy_na=False,
    )

    base_features = ["max_temp", "min_temp", "wind_speed"]
    extra_features = [c for c in df_encoded.columns if c.startswith("weather_") or c.startswith("wind_dir_")]
    features = base_features + extra_features

    X = df_encoded[features]
    y = df_encoded["aqi"]

    if len(X) < 30:
        return {"error": "有效样本过少，无法训练模型。"}

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = LinearRegression()
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    coeffs = pd.Series(model.coef_, index=features).sort_values(ascending=False)
    top_features = pd.concat([coeffs.head(8), coeffs.tail(8)])

    return {
        "model_score_r2": float(model.score(X_test, y_test)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, y_pred))),
        "intercept": float(model.intercept_),
        "top_features": {k: float(v) for k, v in top_features.to_dict().items()},
        "scatter_data": {
            "actual": [float(x) for x in y_test.tolist()],
            "predicted": [float(x) for x in y_pred.tolist()],
        },
    }


# ============================================================
# 四、风力/风向 与 AQI 的描述性统计
# ============================================================

def analyze_wind_vs_aqi(df: pd.DataFrame) -> dict:
    """风力等级、风向 与 AQI 的统计关系（均值/中位数/样本数）。"""
    df_processed = preprocess_data(df)

    wind_speed_aqi = df_processed.groupby("wind_speed")["aqi"].agg(["mean", "median", "count"]).reset_index()
    wind_speed_aqi = wind_speed_aqi[wind_speed_aqi["count"] > 5].sort_values("wind_speed")

    wind_dir_aqi = df_processed.groupby("wind_direction")["aqi"].agg(["mean", "median", "count"]).reset_index()
    wind_dir_aqi = wind_dir_aqi[wind_dir_aqi["count"] > 5].sort_values("mean", ascending=False)

    return {
        "speed_analysis": wind_speed_aqi.to_dict("records"),
        "direction_analysis": wind_dir_aqi.to_dict("records"),
    }


# ============================================================
# 五、三因素热力图数据
# ============================================================

def analyze_multi_factor_relationship(df: pd.DataFrame) -> list:
    """温度 × 风力（按天气类型筛选） -> AQI 平均，用于热力图。"""
    df_processed = preprocess_data(df)

    if df_processed.empty:
        return []

    df_processed["temp_bin"] = pd.cut(
        df_processed["max_temp"],
        bins=5,
        labels=["很低", "低", "中", "高", "很高"],
        include_lowest=True,
    )

    df_processed["wind_bin"] = pd.cut(
        df_processed["wind_speed"],
        bins=[-0.1, 2, 4, 6, 12],
        labels=["微风", "和风", "强风", "烈风"],
        include_lowest=True,
    )

    top_weather = df_processed["weather_simple"].value_counts().nlargest(6).index
    df_filtered = df_processed[df_processed["weather_simple"].isin(top_weather)]

    heatmap_data = (
        df_filtered.groupby(["temp_bin", "wind_bin", "weather_simple"])["aqi"]
        .mean()
        .reset_index()
        .dropna()
    )

    out = []
    for _, r in heatmap_data.iterrows():
        out.append(
            {
                "temp_bin": str(r["temp_bin"]),
                "wind_bin": str(r["wind_bin"]),
                "weather_simple": str(r["weather_simple"]),
                "aqi": float(r["aqi"]),
            }
        )

    return out


# ============================================================
# 六、未来7日AQI预测（时序回归 + 分位数区间）
# ============================================================

def _aqi_level_details(aqi: float) -> Dict[str, str]:
    """根据 AQI 数值返回风险等级、颜色和健康提示。"""
    if aqi is None or np.isnan(aqi):
        return {"level": "未知", "color": "#9e9e9e", "tip": "数据缺失，无法评估。"}
    aqi = round(aqi)
    if aqi <= 50:
        return {"level": "优", "color": "#4caf50", "tip": "空气质量令人满意，基本无空气污染，各类人群可正常活动。"}
    elif aqi <= 100:
        return {"level": "良", "color": "#ffc107", "tip": "空气质量可接受，但某些污染物可能对极少数异常敏感人群健康有较弱影响。"}
    elif aqi <= 150:
        return {"level": "轻度污染", "color": "#ff9800", "tip": "易感人群症状有轻度加剧，健康人群出现刺激症状。建议儿童、老年人及心脏病、呼吸系统疾病患者减少长时间、高强度的户外锻炼。"}
    elif aqi <= 200:
        return {"level": "中度污染", "color": "#f44336", "tip": "进一步加剧易感人群症状，可能对健康人群心脏、呼吸系统有影响。建议儿童、老年人及心脏病、呼吸系统疾病患者避免长时间、高强度的户外锻炼，一般人群适量减少户外运动。"}
    elif aqi <= 300:
        return {"level": "重度污染", "color": "#9c27b0", "tip": "心脏病和肺病患者症状显著加剧，运动耐受力降低，健康人群普遍出现症状。建议儿童、老年人和心脏病、肺病患者应停留在室内，停止户外运动，一般人群避免户外运动。"}
    else:
        return {"level": "严重污染", "color": "#795548", "tip": "健康人群运动耐受力降低，有明显强烈症状，提前出现某些疾病。建议儿童、老年人和病人应停留在室内，避免体力消耗，一般人群应避免户外活动。"}


def _aqi_level(aqi_value: float) -> str:
    """（兼容旧版）只返回等级字符串。"""
    return _aqi_level_details(aqi_value)["level"]


def _build_supervised_dataset(df: pd.DataFrame, lags: int = 7) -> pd.DataFrame:
    """把时间序列数据构造成监督学习数据集。

    核心思想：
    - 预测 t+1 天的 AQI，需要用到过去几天（t, t-1, ...）的 AQI 信息
    - 这就是“滞后特征”（lag features）

    本函数会生成：
    - aqi_lag_1 ... aqi_lag_lags
    - temp_max, temp_min, wind_speed（当天或滞后）
    - dow（星期几）, month（月份）

    输出：包含特征列 + target 列（aqi_next）
    """

    df2 = df.copy().sort_values("date")

    # 生成滞后 AQI 特征
    for i in range(1, lags + 1):
        df2[f"aqi_lag_{i}"] = df2["aqi"].shift(i)

    # 时间特征：星期几与月份
    df2["dow"] = df2["date"].dt.dayofweek  # 0=周一 ... 6=周日
    df2["month"] = df2["date"].dt.month

    # 目标：预测下一天 AQI
    df2["aqi_next"] = df2["aqi"].shift(-1)

    # 删除因 shift 造成的空值行
    df2 = df2.dropna().reset_index(drop=True)

    return df2


def forecast_aqi_7_days(
    df: pd.DataFrame,
    horizon: int = 7,
    lags: int = 7,
    quantiles: tuple = (0.1, 0.5, 0.9),
    future_meteo_7d: Optional[List[Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """核心函数：预测未来 horizon 天 AQI，并给出区间（quantiles）。

    预测策略：递归预测（recursive forecasting）
    - 第1天预测使用历史真实数据
    - 第2天预测会用到“第1天的预测结果”作为 lag
    - 一直滚动到第 horizon 天

    区间估计：分位数回归（Quantile Regression）
    - 训练三个 LightGBM 模型：q=0.1 / 0.5 / 0.9
    - q=0.5 作为中位数预测
    - q=0.1 和 q=0.9 作为不确定性区间

    输入：
    - df：至少包含 date/max_temp/min_temp/wind/aqi 的 DataFrame

    输出：dict
    - forecast: list[7天]，每一天含 date, aqi_p10, aqi_p50, aqi_p90, level
    - model_info: 模型参数与训练样本量
    """

    df_processed = preprocess_data(df)

    # 如果数据过少，无法进行时序建模
    if df_processed["date"].nunique() < (lags + 30):
        return {"error": f"有效日期样本不足（需要至少 {lags + 30} 天），无法进行7日预测。"}

    # 1) 构造监督学习数据集
    ds = _build_supervised_dataset(df_processed, lags=lags)

    feature_cols = [f"aqi_lag_{i}" for i in range(1, lags + 1)] + [
        "max_temp",
        "min_temp",
        "wind_speed",
        "dow",
        "month",
    ]

    X = ds[feature_cols]
    y = ds["aqi_next"]

    # 2) 训练分位数模型
    models_q = {}
    for q in quantiles:
        # objective='quantile' + alpha=q 就是分位数回归
        params = {
            "objective": "quantile",
            "alpha": q,
            "learning_rate": 0.05,
            "n_estimators": 500,
            "num_leaves": 31,
            "min_child_samples": 20,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": 42,
        }
        model = lgb.LGBMRegressor(**params)
        model.fit(X, y)
        models_q[q] = model

    # 3) 准备递归预测的初始窗口（取 ds 最后一行对应的“最后可用特征”）
    last_row = ds.iloc[-1]

    # 初始 lag 队列：最近 lags 天的 AQI（这里用 df_processed 的最后 lags 天）
    recent_aqi = df_processed.sort_values("date")["aqi"].tail(lags).tolist()

    # 未来日期从最后一天后开始
    last_date = df_processed["date"].max().date()

    forecast_list = []

    # 为了构造未来的气象特征：
    # 1) 如果传入 future_meteo_7d（长度=7），则逐日使用输入值
    # 2) 否则采用“持平假设”：使用最近一天的 max/min/wind_speed
    last_max_temp = float(df_processed.sort_values("date").iloc[-1]["max_temp"])
    last_min_temp = float(df_processed.sort_values("date").iloc[-1]["min_temp"])
    last_wind_speed = float(df_processed.sort_values("date").iloc[-1]["wind_speed"])

    for step in range(1, horizon + 1):
        target_date = last_date + timedelta(days=step)

        # 构造该天的特征
        row_feat = {}
        for i in range(1, lags + 1):
            row_feat[f"aqi_lag_{i}"] = recent_aqi[-i]

        if future_meteo_7d and len(future_meteo_7d) >= step:
            met = future_meteo_7d[step - 1]
            row_feat["max_temp"] = float(met.get("max_temp", last_max_temp))
            row_feat["min_temp"] = float(met.get("min_temp", last_min_temp))
            row_feat["wind_speed"] = float(met.get("wind_speed", last_wind_speed))
        else:
            row_feat["max_temp"] = last_max_temp
            row_feat["min_temp"] = last_min_temp
            row_feat["wind_speed"] = last_wind_speed

        row_feat["dow"] = pd.Timestamp(target_date).dayofweek
        row_feat["month"] = pd.Timestamp(target_date).month

        X_pred = pd.DataFrame([row_feat], columns=feature_cols)

        # 分位数预测
        preds = {q: float(models_q[q].predict(X_pred)[0]) for q in quantiles}

        # 取中位数（0.5）作为主预测
        p50 = preds.get(0.5, list(preds.values())[0])

        # 更新 lag 队列：把预测值当成“下一天的历史AQI”
        recent_aqi.append(p50)

        p10 = preds.get(0.1, p50)
        p90 = preds.get(0.9, p50)
        # 置信度：区间越窄越可信，简单归一化（可按需要调整）
        width = max(0.0, float(p90) - float(p10))
        confidence = max(0.0, min(1.0, 1.0 - width / 120.0))

        forecast_list.append(
            {
                "date": str(target_date),
                "aqi_p10": round(p10, 2),
                "aqi_p50": round(p50, 2),
                "aqi_p90": round(p90, 2),
                "confidence": round(float(confidence), 3),
                **_aqi_level_details(p50),
            }
        )

    return {
        "forecast": forecast_list,
        "model_info": {
            "train_samples": int(len(ds)),
            "lags": int(lags),
            "quantiles": list(quantiles),
            "note": "未来气象特征采用持平假设（使用最近一天观测值）。",
        },
    }

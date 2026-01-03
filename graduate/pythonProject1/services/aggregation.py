"""aggregation.py

提供日/周/月维度聚合工具。
- 输入：DataFrame(date, value...)
- 输出：按 granularity 聚合后的序列

说明：
- week：按自然周聚合（周一~周日），显示为该周周一日期
- month：按自然月聚合，显示为当月1号
"""

from __future__ import annotations

import pandas as pd


def _ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    return df


def aggregate_series(df: pd.DataFrame, granularity: str, agg: str = "mean") -> pd.DataFrame:
    """对单列或多列数值序列进行聚合。

    参数：
    - df: 必须包含 date 列，其他列为数值列
    - granularity: day/week/month
    - agg: mean/sum/max/min

    返回：
    - 包含 date + 原数值列的聚合结果 DataFrame
    """

    granularity = (granularity or "day").lower()
    agg = (agg or "mean").lower()

    df = _ensure_datetime(df)

    if granularity == "day":
        key = df["date"].dt.floor("D")
    elif granularity == "week":
        # 周一作为周起始
        key = df["date"].dt.to_period("W-MON").dt.start_time
    elif granularity == "month":
        key = df["date"].dt.to_period("M").dt.start_time
    else:
        raise ValueError("granularity must be day/week/month")

    df2 = df.copy()
    df2["date"] = key

    # 仅聚合数值列
    value_cols = [c for c in df2.columns if c != "date"]

    # 使用 .agg() 方法可以确保聚合后的列名保持不变
    agg_map = {col: agg for col in value_cols}
    out = df2.groupby("date", as_index=False).agg(agg_map)
    # groupby.agg 会在 agg 不支持时抛异常；这里补一个友好提示
    if agg not in ("mean", "sum", "max", "min"):
        raise ValueError("agg must be mean/sum/max/min")

    out = out.sort_values("date")
    out["date"] = out["date"].dt.date
    return out


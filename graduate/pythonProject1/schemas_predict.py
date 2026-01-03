"""schemas_predict.py

预测接口的 Pydantic 模型（单独拆文件，避免影响现有 schemas.py）。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class MeteoInput(BaseModel):
    """单日气象输入（用于未来7天预测的外生变量）。"""

    max_temp: float = Field(..., description="最高温(℃)")
    min_temp: float = Field(..., description="最低温(℃)")
    wind_speed: float = Field(..., description="风力等级(数值)")


class AQI7dPredictRequest(BaseModel):
    """预测请求：指定区域 + 未来7天的气象假设输入。

    若 meteo_7d 不传，则后端默认用最近一天的 max/min/wind_speed 做持平假设。
    """

    area: str = Field("广州", description="区域")
    meteo_7d: Optional[List[MeteoInput]] = Field(default=None, description="未来7天气象输入(长度=7)")


class AQI7dPredictItem(BaseModel):
    date: str
    aqi_p10: float
    aqi_p50: float
    aqi_p90: float
    level: str
    color: str
    tip: str
    confidence: float = Field(..., description="置信度(0~1)，越大表示越稳定")


class AQI7dPredictResponse(BaseModel):
    area: str
    forecast: List[AQI7dPredictItem]
    model_info: dict


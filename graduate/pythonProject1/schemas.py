"""schemas.py

【教学版说明】
本文件定义 FastAPI 接口的“数据模型”（Pydantic 模型）。

为什么要用 Pydantic？
1) 入参校验：前端传来的 JSON 会被自动校验（比如邮箱格式、密码长度）
2) 出参格式统一：接口返回的数据结构更稳定
3) 自动生成接口文档：/docs 会显示每个接口需要什么字段

你可以把它理解为：
- 请求体（Request Body）和响应体（Response）的“数据规范”。

本项目主要包含 3 类 schema：
1) 用户相关（注册/登录/重置密码）
2) 收藏相关
3) 历史查询相关
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field


# ============================================================
# 一、用户注册/登录
# ============================================================

class UserCreate(BaseModel):
    """注册接口的请求体。

    前端需要传：
    - username
    - email
    - password

    Field(min_length/max_length) 会自动做长度校验。

    注意：
    - EmailStr 依赖 email-validator 库，用于验证邮箱格式。
    """

    username: str = Field(min_length=2, max_length=50)
    email: str

    # bcrypt 有 72 字节限制，但我们这里给到 128 是为了更通用。
    # 如果你担心中文导致超长，可把 max_length 改小，比如 72。
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    """登录接口的请求体。"""

    email: str
    password: str


class UserOut(BaseModel):
    """用户信息的返回格式（不包含密码）。

    说明：
    - 绝不能把 hashed_password 返回给前端。
    - from_attributes=True 允许 Pydantic 从 ORM 对象读取字段。
    """

    id: int
    username: str
    email: str
    created_at: datetime
    preferred_areas: Optional[List[str]] = []

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    """登录成功后返回的 token 格式。"""

    access_token: str
    token_type: str = "bearer"


# ============================================================
# 二、密码重置（演示版）
# ============================================================

class PasswordResetRequest(BaseModel):
    """申请重置密码：只需要邮箱。"""

    email: str


class PasswordResetConfirm(BaseModel):
    """确认重置密码。

    前端要传：
    - token：上一步 request 接口返回的重置 token
    - new_password：新密码
    """

    token: str
    new_password: str = Field(min_length=6, max_length=128)


# ============================================================
# 三、收藏图表
# ============================================================

class FavoriteCreate(BaseModel):
    """添加收藏的请求体。

    chart_type 示例：
    - aqi_trend / temp_trend / temp_aqi_corr / advanced_regression 等

    area 示例：
    - 广州 / 从化区 / 番禺区 ...
    """

    chart_type: str
    area: str


class FavoriteOut(BaseModel):
    """收藏记录返回格式。"""

    id: int
    chart_type: str
    area: str
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# 四、历史查询
# ============================================================

class HistoryCreate(BaseModel):
    """写入历史查询记录的请求体。

    说明：
    - 本系统前端在用户点击“应用筛选”时，会把 area/start/end 写入历史。
    - extra 是预留字段，未来可扩展更多筛选条件。
    """

    area: str
    start: Optional[str] = None
    end: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


class HistoryOut(BaseModel):
    """历史查询记录返回格式。"""

    id: int
    search_params: Dict[str, Any]
    searched_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# 五、常用辖区（目前预留）
# ============================================================

class PreferredAreasUpdate(BaseModel):
    """常用辖区更新请求体。

    需求：最多 3 个辖区。
    说明：写入 users.preferred_areas(JSON)。
    """

    areas: List[str] = Field(default_factory=list, description="最多3个辖区/区域", max_length=3)

"""models.py

【教学版说明】
本文件定义数据库表结构（ORM 模型）。

你可以把它理解为：
- MySQL 里真正的表（weather_data/users/...）
- 在 Python 里用 class 来表示

SQLAlchemy ORM 的作用：
- 让你用 Python 操作数据库，而不是手写 SQL
- 例如：db.query(User).filter(User.email==xxx).first()

本项目的表分 2 类：
1) 业务数据表
   - WeatherData：你爬取并清洗后的天气/AQI数据
2) 用户系统表
   - User：用户基础信息
   - UserFavorite：用户收藏的图表（图表类型+辖区）
   - SearchHistory：用户历史查询记录（JSON 存储查询参数）
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Date,
    DateTime,
    func,
    Boolean,
    ForeignKey,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


# ============================================================
# 一、天气/AQI 数据表
# ============================================================
class WeatherData(Base):
    """天气数据表（weather_data）。

    说明：
    - 这是你的 CSV 数据清洗后导入 MySQL 的主表
    - 每一行代表：某个“区域”在某一天的天气与 AQI

    重要字段：
    - area: 区域（从化区、番禺区...）
    - date: 日期
    - max_temp/min_temp: 最高/最低温
    - weather: 天气现象文本（如 多云~小雨）
    - wind: 风力风向文本（如 东北风3级）
    - aqi: 空气质量指数

    其他字段：
    - avg_high_temp/avg_low_temp/extreme_* 等是你爬虫附带的统计信息
    """

    __tablename__ = "weather_data"

    id = Column(Integer, primary_key=True, index=True)

    area = Column(String(50), index=True, comment="区域")
    date = Column(Date, index=True, comment="日期")

    max_temp = Column(Float, comment="最高温度(℃)")
    min_temp = Column(Float, comment="最低温度(℃)")

    weather = Column(String(100), comment="天气现象")
    wind = Column(String(100), comment="风力风向")

    aqi = Column(Integer, comment="空气质量指数")

    # 统计类字段（可选）
    avg_high_temp = Column(Float, nullable=True, comment="平均高温")
    avg_low_temp = Column(Float, nullable=True, comment="平均低温")
    extreme_high_temp = Column(Float, nullable=True, comment="极端高温")
    extreme_low_temp = Column(Float, nullable=True, comment="极端低温")
    avg_aqi = Column(Float, nullable=True, comment="平均空气质量指数")
    best_aqi = Column(Integer, nullable=True, comment="空气最好")
    worst_aqi = Column(Integer, nullable=True, comment="空气最差")

    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<WeatherData(area='{self.area}', date='{self.date}', aqi={self.aqi})>"


# ============================================================
# 二、用户表
# ============================================================
class User(Base):
    """用户表（users）。"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)

    hashed_password = Column(String(255), nullable=False)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 常用辖区（最多3个），用 JSON 数组存储，例如：["天河区","越秀区","番禺区"]
    preferred_areas = Column(JSON, nullable=True)

    favorites = relationship("UserFavorite", back_populates="user", cascade="all, delete-orphan")
    search_history = relationship("SearchHistory", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(username='{self.username}', email='{self.email}')>"


# ============================================================
# 三、收藏表
# ============================================================
class UserFavorite(Base):
    """用户收藏表（user_favorites）。"""

    __tablename__ = "user_favorites"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    chart_type = Column(String(50), nullable=False)
    area = Column(String(50), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="favorites")

    __table_args__ = (UniqueConstraint("user_id", "chart_type", "area", name="_user_chart_area_uc"),)

    def __repr__(self):
        return f"<UserFavorite(user_id={self.user_id}, chart='{self.chart_type}', area='{self.area}')>"


# ============================================================
# 四、历史查询表
# ============================================================
class SearchHistory(Base):
    """用户历史查询表（search_history）。"""

    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    search_params = Column(JSON, nullable=False)

    searched_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="search_history")

    def __repr__(self):
        return f"<SearchHistory(user_id={self.user_id}, params='{self.search_params}')>"


# ============================================================
# 五、社交互动表（点赞/收藏/关注）
# ============================================================
class SocialInteraction(Base):
    """社交互动记录表（social_interactions）。

    说明：
    - 记录用户对某个“区域”进行的“互动类型”（点赞/收藏/关注）。
    - UniqueConstraint 确保同一用户对同一区域不能重复进行同一种操作。
    """

    __tablename__ = "social_interactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 互动类型：like, favorite, follow
    interaction_type = Column(String(50), nullable=False, index=True)

    # 互动的对象：区域名称
    area = Column(String(50), nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # 组合唯一约束：一个用户只能对一个区域点一次赞
    __table_args__ = (UniqueConstraint("user_id", "interaction_type", "area", name="_user_interaction_area_uc"),)

    def __repr__(self):
        return f"<SocialInteraction(user_id={self.user_id}, type='{self.interaction_type}', area='{self.area}')>"


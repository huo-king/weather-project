"""db_optimizations.py

数据库性能优化：索引自检与创建（幂等）。

说明：
- 仅针对 MySQL（information_schema + CREATE INDEX）。
- 为了不引入 Alembic，本模块提供轻量的“启动自检”，不会影响原功能。
- 如无权限创建索引，会打印 warning，不阻止服务启动。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from config import Config
from database import engine


def _index_exists(db: str, table: str, index_name: str) -> bool:
    with engine.connect() as conn:
        n = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.statistics
                WHERE table_schema = :db
                  AND table_name = :table
                  AND index_name = :idx;
                """
            ),
            {"db": db, "table": table, "idx": index_name},
        ).scalar()
        return int(n or 0) > 0


def _safe_exec(sql: str):
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()


def ensure_indexes():
    """创建常用索引（如果不存在）。"""

    db = Config.MYSQL_DB

    # weather_data
    idxs = [
        ("weather_data", "idx_weather_area_date", "CREATE INDEX idx_weather_area_date ON weather_data(area, date)"),
        ("weather_data", "idx_weather_date", "CREATE INDEX idx_weather_date ON weather_data(date)"),

        # user_favorites
        ("user_favorites", "idx_fav_user_created", "CREATE INDEX idx_fav_user_created ON user_favorites(user_id, created_at)"),

        # search_history
        ("search_history", "idx_hist_user_time", "CREATE INDEX idx_hist_user_time ON search_history(user_id, searched_at)"),

        # social_interactions
        ("social_interactions", "idx_social_area_type", "CREATE INDEX idx_social_area_type ON social_interactions(area, interaction_type)"),
        ("social_interactions", "idx_social_user_area_type", "CREATE INDEX idx_social_user_area_type ON social_interactions(user_id, area, interaction_type)"),
    ]

    for table, idx_name, sql in idxs:
        try:
            if _index_exists(db, table, idx_name):
                continue
            _safe_exec(sql)
            print(f"[Index] created {idx_name} on {table}")
        except Exception as e:
            print(f"[Index] create {idx_name} failed: {e}")


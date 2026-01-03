"""migrate.py

轻量级数据库迁移脚本（教学/作业友好，不依赖 Alembic）。

解决的问题：
- 当你在 models.py 增加了字段，但 MySQL 里旧表没有该列时，会导致 500。
- 该脚本会补齐缺失列（目前只处理 preferred_areas）。

使用：
1) 确保 config.py 里 MySQL 连接正确，且数据库已创建。
2) 运行：
   python migrate.py
"""

from sqlalchemy import text

from database import engine
from config import Config


def ensure_preferred_areas_column():
    with engine.connect() as conn:
        exists = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :db
                  AND TABLE_NAME = 'users'
                  AND COLUMN_NAME = 'preferred_areas';
                """
            ),
            {"db": Config.MYSQL_DB},
        ).scalar()

        if exists and int(exists) > 0:
            print("[migrate] users.preferred_areas 已存在，跳过")
            return

        print("[migrate] 正在添加 users.preferred_areas ...")
        conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN preferred_areas JSON NULL AFTER created_at;
                """
            )
        )
        print("[migrate] 添加完成")


if __name__ == "__main__":
    ensure_preferred_areas_column()
    print("[migrate] done")


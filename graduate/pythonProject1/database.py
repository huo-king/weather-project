"""database.py

【教学版说明】
本文件负责创建数据库连接（SQLAlchemy Engine）以及 Session 工厂。

核心概念：
1) Engine：数据库连接的“发动机”，负责与 MySQL 建立连接
2) Session：一次数据库会话，负责执行查询/插入/更新等操作
3) Base：所有 ORM 模型（models.py）都要继承的基类

为什么要单独抽出来？
- 任何需要访问数据库的模块（api_server.py / main.py / services）都可以复用它。
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from config import Config


# ============================================================
# 一、创建数据库连接 URL
# ============================================================
# mysql+pymysql://用户名:密码@主机:端口/数据库名
SQLALCHEMY_DATABASE_URL = (
    f"mysql+pymysql://{Config.MYSQL_USER}:{Config.MYSQL_PASSWORD}"
    f"@{Config.MYSQL_HOST}:{Config.MYSQL_PORT}/{Config.MYSQL_DB}"
)


# ============================================================
# 二、创建 Engine
# ============================================================
# pool_pre_ping=True：
# - 在连接池取出连接之前先 ping 一下，避免“长时间不使用导致连接断开”的问题
# pool_recycle=3600：
# - 连接超过 3600 秒自动回收重建，避免 MySQL 超时
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)


# ============================================================
# 三、创建 Session 工厂
# ============================================================
# autocommit=False：
# - 不自动提交，需要手动 db.commit()
# autoflush=False：
# - 不自动 flush（写入缓存），手动控制更安全
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ============================================================
# 四、Base：ORM 基类
# ============================================================
# models.py 中所有表类都继承 Base
Base = declarative_base()

# ============================================================
# 六、在启动时自动检查并补充缺失列（避免因手工忘记迁移而报错）
# ============================================================

def _ensure_schema():
    """如果 users 表缺少 preferred_areas 字段，则自动添加。

    说明：
    1. 仅在 MySQL 下测试通过。
    2. 不依赖 Alembic，轻量级自愈。
    3. 生产环境建议用正式迁移工具（Alembic）。
    """
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            # 查询 users 表结构，判断是否已有此列
            res = conn.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :db
                  AND TABLE_NAME = 'users'
                  AND COLUMN_NAME = 'preferred_areas';
            """), {"db": Config.MYSQL_DB}).scalar()
            if res == 0:
                # 列不存在，自动新增
                conn.execute(text("""
                    ALTER TABLE users
                    ADD COLUMN preferred_areas JSON NULL AFTER created_at;
                """))
                print("[Schema] 已自动为 users 表添加 preferred_areas 字段")
    except Exception as e:
        # 打印警告，不阻止应用启动
        print(f"[Schema] 自动检查/修复 schema 失败: {e}")

# 确保在模块 import 时立即检查
_ensure_schema()

# 启动时创建常用索引（失败不阻塞）
try:
    from services.db_optimizations import ensure_indexes
    ensure_indexes()
except Exception as e:
    print(f"[Index] ensure_indexes skipped: {e}")


# ============================================================
# 五、FastAPI 依赖项：get_db
# ============================================================
# 在 FastAPI 中可以用 Depends(get_db) 获取一个 Session
# 请求结束后自动 close

def get_db():
    """FastAPI 依赖：创建并返回一个数据库 Session。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

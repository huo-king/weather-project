"""main.py

【教学版说明】
这是一个“ETL 工具脚本”，用于：
1) 初始化数据库（创建数据库 + 创建表结构）
2) 把 CSV 数据清洗后导入 MySQL
3) 查看数据库统计信息

注意：
- main.py 主要是离线工具，用来导入数据，不负责跑网页。
- 网页系统由 api_server.py 启动。

你可以理解：
- main.py = 数据准备工具
- api_server.py = 系统运行入口（后端+前端）
"""

import sys
from pathlib import Path

from sqlalchemy import func
from sqlalchemy_utils import database_exists, create_database

# ---------------------
# 让 Python 能够从当前项目目录导入模块
# ---------------------
# 例如：import database / import config / import services...
# 如果不加这行，可能出现 ModuleNotFoundError
sys.path.append(str(Path(__file__).parent))

# 导入项目模块
from database import Base, engine
from config import Config
from services.data_loader import WeatherDataLoader
from models import WeatherData


def init_db():
    """初始化数据库。

    具体做两件事：
    1) 如果数据库不存在，则创建数据库（weather_aqi）
    2) 创建表结构（Base.metadata.create_all）

    注意：
    - create_database 会创建数据库（schema），不是创建表
    - create_all 会创建表（weather_data、users、...）
    """

    # 如果数据库不存在就创建
    if not database_exists(engine.url):
        create_database(engine.url)
        print(f"数据库 {Config.MYSQL_DB} 创建成功")

    # 创建所有表
    Base.metadata.create_all(bind=engine)
    print("表结构创建成功")


def load_data(truncate: bool = False):
    """加载 CSV 数据到数据库。

    参数：
    - truncate=True：先清空 weather_data 表再导入
    - truncate=False：只导入“数据库中不存在”的新数据（按 area+date 去重）
    """

    loader = WeatherDataLoader()

    try:
        count = loader.load_data_to_db(truncate=truncate)
        print(f"数据加载完成，共处理 {count} 条记录")
    except Exception as e:
        # 捕获异常，避免程序直接崩溃
        print(f"加载数据时出错: {e}")
    finally:
        # 无论是否异常，都要关闭数据库连接
        loader.close()


def show_db_stats():
    """查看数据库统计信息。

    用途：
    - 快速确认数据库中数据是否导入成功
    - 查看日期范围与区域数量
    """

    from database import SessionLocal

    # with SessionLocal() 会自动 close session
    with SessionLocal() as db:
        # 总记录数
        total = db.query(func.count(WeatherData.id)).scalar() or 0

        # 日期最小值/最大值
        date_min = db.query(func.min(WeatherData.date)).scalar()
        date_max = db.query(func.max(WeatherData.date)).scalar()

        # 区域列表
        areas = [r[0] for r in db.query(WeatherData.area).distinct().order_by(WeatherData.area).all()]
        area_count = len(areas)

        # 各区域记录数（用于排查是否某区缺数据）
        per_area = (
            db.query(WeatherData.area, func.count(WeatherData.id).label("cnt"))
            .group_by(WeatherData.area)
            .order_by(func.count(WeatherData.id).desc())
            .all()
        )

    print("\n=== 数据库统计信息 ===")
    print(f"数据库：{Config.MYSQL_DB}")
    print(f"总记录数：{total}")
    print(f"日期范围：{date_min} ~ {date_max}")
    print(f"区域数：{area_count}")

    if areas:
        print("区域列表：" + "、".join(areas))

    print("\n各区域记录数（Top 20）：")
    for area, cnt in per_area[:20]:
        print(f"- {area}: {cnt}")


if __name__ == "__main__":
    # 用 while True 实现“循环菜单”，直到用户选择退出
    while True:
        print("\n=== 天气数据ETL工具 ===")
        print("1. 初始化数据库")
        print("2. 加载数据到数据库")
        print("3. 清空并重新加载数据")
        print("4. 查看数据库统计信息")
        print("5. 退出")

        choice = input("请选择操作 (1-5): ").strip()

        if choice == "1":
            init_db()
        elif choice == "2":
            load_data(truncate=False)
        elif choice == "3":
            confirm = input("警告：这将清空所有数据！确定继续吗？(y/n): ").strip().lower()
            if confirm == "y":
                init_db()
                load_data(truncate=True)
            else:
                print("已取消清空重载。")
        elif choice == "4":
            show_db_stats()
        elif choice == "5":
            print("已退出")
            break
        else:
            print("输入无效，请输入 1-5。")

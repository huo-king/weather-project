"""data_loader.py

【教学版说明】
本文件负责“把清洗后的 DataFrame 写入 MySQL 数据库”。

它与 data_cleaner.py 的分工：
- data_cleaner.py：负责清洗 CSV（把脏数据 -> 干净、结构化）
- data_loader.py：负责把干净数据写入数据库，并做去重、批量插入

为什么要分开？
- 清洗逻辑和数据库写入逻辑是两类事情，拆开后更容易维护和调试。

典型使用方式：
- main.py 或其他脚本调用：
  loader = WeatherDataLoader()
  loader.load_data_to_db(truncate=False)
"""

from sqlalchemy.orm import Session

from database import SessionLocal
from models import WeatherData
from services.data_cleaner import WeatherDataCleaner


class WeatherDataLoader:
    """天气数据入库器。

    功能：
    - 从 CSV -> 清洗 -> DataFrame
    - DataFrame -> 转 record list -> 批量插入 MySQL
    - 支持 truncate（清空表后重导）
    - 支持简单去重：按 (area, date) 作为唯一键

    注意：
    - 目前去重方式是：先查询数据库里所有 (area, date)，再过滤插入。
      数据量非常大时，这种方式会慢。
      更专业的做法：给 (area, date) 建唯一索引，然后用数据库 upsert。
    """

    def __init__(self, db: Session = None):
        # 如果外部没有传入 Session，就创建一个新的 SessionLocal
        self.db = db or SessionLocal()

    def load_data_to_db(self, file_path: str = None, truncate: bool = False) -> int:
        """清洗 CSV 并写入数据库。

        参数：
        - file_path: CSV 文件路径（可选）；不传则使用 Config.DATA_FILE
        - truncate: 是否清空表再导入

        返回：
        - 实际插入的新记录数量
        """

        # 1) 清洗数据
        # WeatherDataCleaner 会读取 CSV 并输出清洗后的 DataFrame
        cleaner = WeatherDataCleaner(file_path)
        df = cleaner.clean_data()

        # 2) 如果需要清空表（注意：会删除 weather_data 的所有记录）
        if truncate:
            self.db.query(WeatherData).delete()
            self.db.commit()

        # 3) DataFrame -> list[dict]
        # 每一条 dict 就对应 ORM WeatherData 的字段
        records = df.to_dict("records")

        # 4) 去重
        # 查询数据库里已有的 (area, date)
        existing_records = self.db.query(WeatherData.area, WeatherData.date).all()
        existing_keys = {(r.area, r.date) for r in existing_records}

        # 只保留数据库中不存在的记录
        new_records = []
        for record in records:
            # 如果 (区域, 日期) 组合没有出现过，则认为是新数据
            if (record["area"], record["date"]) not in existing_keys:
                new_records.append(WeatherData(**record))

        # 5) 批量插入
        if new_records:
            # bulk_save_objects 比逐条 add 更快
            self.db.bulk_save_objects(new_records)
            self.db.commit()
            print(f"成功插入 {len(new_records)} 条记录")
        else:
            print("没有新数据需要插入")

        return len(new_records)

    def close(self):
        """关闭数据库连接（Session）。"""
        if hasattr(self, "db") and self.db:
            self.db.close()

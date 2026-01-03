"""data_cleaner.py

【教学版说明】
本文件负责“把你爬虫得到的 CSV 原始数据”清洗成“适合入库 MySQL 的结构化数据”。

清洗的主要目的：
1) 字段标准化：把中文列名改成数据库字段名
2) 类型转换：温度/AQI 等字段转为数值
3) 混合字段解析：例如 "27 (2024-01-15)" 提取数字 27
4) 缺失值处理：例如 avg_low_temp 缺失，用同区域均值填补

使用方式：
- WeatherDataLoader 会调用 WeatherDataCleaner.clean_data()，得到 DataFrame
- 然后把 DataFrame 批量写入 MySQL
"""

import re
from typing import Optional

import pandas as pd

from config import Config


class WeatherDataCleaner:
    """天气数据清洗器。

    设计成类的原因：
    - 可以先 load_data() 再 clean_data()
    - file_path 可配置
    """

    def __init__(self, file_path: str = None):
        # 如果没传 file_path，就用 config.py 里配置的默认文件
        self.file_path = file_path or Config.DATA_FILE
        self.df = None

    def load_data(self) -> pd.DataFrame:
        """读取 CSV 文件。

        注意：
        - 如果 CSV 编码不是 utf-8，可能需要加 encoding 参数
        - 你目前的文件是中文列名，pandas 默认能处理
        """
        self.df = pd.read_csv(self.file_path)
        return self.df

    def clean_data(self) -> pd.DataFrame:
        """清洗数据，返回适合入库的 DataFrame。

        主要步骤：
        1) 解析日期列
        2) 提取数值列的数字（处理 "27 (2024-01-15)" 这种格式）
        3) 中文列名 -> 英文数据库列名
        4) 选择需要的列（丢弃无用列）
        5) 缺失值填充
        6) 确保字段类型正确
        """

        # 如果还没加载数据，先 load
        if self.df is None:
            self.load_data()

        df = self.df.copy()

        # 1) 处理日期：把“日期”列转成 date 类型
        # - dt.date 会把 datetime64 转成 Python 的 date
        df["date"] = pd.to_datetime(df["日期"], errors="coerce").dt.date

        # 2) 提取数值型字段中的数字
        # 注意：某些字段可能是纯数字，也可能是 "27 (2024-01-15)" 这种混合格式
        numeric_columns = [
            "最高温",
            "最低温",
            "空气质量指数",
            "平均高温",
            "平均低温",
            "极端高温",
            "极端低温",
            "平均空气质量指数",
            "空气最好",
            "空气最差",
        ]

        for col in numeric_columns:
            if col in df.columns:
                df[col] = df[col].apply(self._extract_number)

        # 3) 重命名列以匹配数据库字段
        # 数据库字段名是我们在 models.py 里定义的（WeatherData）
        column_mapping = {
            "区域": "area",
            "最高温": "max_temp",
            "最低温": "min_temp",
            "天气": "weather",
            "风力风向": "wind",
            "空气质量指数": "aqi",
            "平均高温": "avg_high_temp",
            "平均低温": "avg_low_temp",
            "极端高温": "extreme_high_temp",
            "极端低温": "extreme_low_temp",
            "平均空气质量指数": "avg_aqi",
            "空气最好": "best_aqi",
            "空气最差": "worst_aqi",
        }

        df = df.rename(columns=column_mapping)

        # 4) 选择需要的列
        # - 只保留数据库需要的列
        columns_to_keep = list(column_mapping.values()) + ["date"]
        df = df[[col for col in columns_to_keep if col in df.columns]]

        # 5) 处理缺失值
        # - 这里用“同区域的均值”进行填补，是一种简单的缺失值处理策略
        # - 更严格的做法可以用插值、按月份均值等
        if "avg_high_temp" in df.columns:
            df["avg_high_temp"] = df["avg_high_temp"].fillna(
                df.groupby("area")["max_temp"].transform("mean")
            )

        if "avg_low_temp" in df.columns:
            df["avg_low_temp"] = df["avg_low_temp"].fillna(
                df.groupby("area")["min_temp"].transform("mean")
            )

        # 6) 确保数据类型正确
        float_columns = [
            "max_temp",
            "min_temp",
            "avg_high_temp",
            "avg_low_temp",
            "extreme_high_temp",
            "extreme_low_temp",
            "avg_aqi",
        ]
        int_columns = ["aqi", "best_aqi", "worst_aqi"]

        for col in float_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        for col in int_columns:
            if col in df.columns:
                # aqi 等字段应该是整数
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        return df

    @staticmethod
    def _extract_number(value) -> Optional[float]:
        """从字符串中提取数字。

        输入示例：
        - "27 (2024-01-15)" -> 27
        - "99" -> 99
        - None/NaN -> None

        返回：float 或 None
        """
        if pd.isna(value):
            return None

        # 如果本来就是数字，直接返回
        if isinstance(value, (int, float)):
            return float(value)

        # 正则提取第一个数字（支持小数）
        match = re.search(r"(\d+\.?\d*)", str(value))
        if match:
            return float(match.group(1))

        return None

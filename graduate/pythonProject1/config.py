"""config.py

【教学版说明】
本文件是项目的“配置文件”。

为什么需要配置文件？
- 把所有可变/敏感的配置（数据库密码、密钥、文件路径等）集中到一起，方便修改。
- 避免把密码等硬编码到代码里。

本项目的配置来源：
- 优先从 .env 文件读取（load_dotenv()）
- 如果 .env 里没有，则使用代码里提供的默认值

.env 文件是什么？
- 一个纯文本文件，用于存放环境变量，通常不提交到 git。
- 格式：
  MYSQL_USER=root
  MYSQL_PASSWORD=your_password
"""

import os

from dotenv import load_dotenv

# load_dotenv() 会自动查找当前目录或上级目录的 .env 文件，并加载到环境变量中
load_dotenv()


class Config:
    """配置类：集中管理所有配置项。"""

    # ---------- 1. MySQL 数据库配置 ----------
    # os.getenv('KEY', 'default_value')：
    # - 先尝试读取环境变量 'KEY'
    # - 如果没有，就用 'default_value' 作为默认值
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "password")
    MYSQL_DB = os.getenv("MYSQL_DB", "weather_aqi")

    # ---------- 2. JWT 密钥 ----------
    # 这个密钥用于 JWT token 签名，必须保密
    # 你在 auth.py 里也定义了一个，为了统一管理，以后应都从这里读取
    SECRET_KEY = os.getenv("SECRET_KEY", "a_very_secret_key_that_should_be_in_env_file")

    # ---------- 3. 文件路径 ----------
    # 你爬虫生成的原始数据 CSV 文件名
    DATA_FILE = "广州天气数据.csv"

    # ---------- 4. 业务配置（可选） ----------
    # 把区域列表硬编码在这里，可以避免每次都查数据库
    # 但如果未来区域会变，从数据库动态获取更好
    AREAS = [
        "从化区",
        "增城区",
        "花都区",
        "南沙区",
        "番禺区",
        "白云区",
        "黄埔区",
        "天河区",
        "海珠区",
        "荔湾区",
        "越秀区",
    ]

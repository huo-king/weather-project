"""auth.py

【教学版说明】
本文件实现“用户认证/鉴权”核心逻辑，主要包含：
1) 密码哈希与校验（bcrypt）
2) JWT Token 的签发（create_access_token）
3) FastAPI 依赖项：从请求头 Authorization 里解析 token，拿到当前用户（get_current_user）

为什么需要这些？
- 密码不能明文存储到数据库，必须 hash。
- 前后端分离时，服务端通常用 JWT（无状态令牌）来识别用户身份。
- 对需要权限的接口（收藏、历史记录）要做“登录校验”，即鉴权。

注意：
- SECRET_KEY 应该放到 .env 环境变量里，不要写死在代码中（生产环境强烈建议）。
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

import models
from database import get_db

# ============================================================
# 一、JWT 配置
# ============================================================
# SECRET_KEY：JWT 签名密钥，必须保密。
# 你现在为了方便演示写在代码里，后期建议改为从环境变量读取。
SECRET_KEY = "a_very_secret_key_that_should_be_in_env_file"

# HS256：对称加密算法（同一个密钥用于签发与验证）
ALGORITHM = "HS256"

# token 默认有效期（分钟）
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24小时


# ============================================================
# 二、密码哈希（bcrypt）
# ============================================================
# passlib 提供统一的密码哈希接口。
# schemes=["bcrypt"] 表示使用 bcrypt 算法。
# bcrypt 有个重要限制：只使用密码前 72 字节，所以密码不要过长。
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证用户输入的明文密码是否与数据库中的哈希密码匹配。

    参数：
    - plain_password：用户输入的明文
    - hashed_password：数据库中存储的 hash

    返回：True/False
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """把用户明文密码转换成哈希字符串（存入数据库）。

    注意：
    - 绝不能把明文密码存到数据库。
    - 哈希结果每次都不同（因为带盐），但 verify_password 仍能验证。
    """
    return pwd_context.hash(password)


# ============================================================
# 三、JWT 令牌生成
# ============================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT Token。

    参数：
    - data：要写入 token 的数据（一般包含 sub=用户唯一标识，如邮箱）
    - expires_delta：自定义过期时间（可选）

    返回：
    - encoded_jwt：字符串形式的 token

    说明：
    - token 的 payload 会包含 exp（过期时间）
    - 前端保存 token 后，每次请求需要登录的接口都带上：
      Authorization: Bearer <token>
    """

    # 复制一份，避免修改调用方传入的 dict
    to_encode = data.copy()

    # 设置过期时间
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # exp 字段是 JWT 标准字段
    to_encode.update({"exp": expire})

    # 用 SECRET_KEY 进行签名
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# ============================================================
# 四、FastAPI 鉴权依赖：获取当前用户
# ============================================================
# OAuth2PasswordBearer 会：
# - 从请求头 Authorization: Bearer xxx 里把 token 取出来
# - tokenUrl 只是给 /docs 的“Authorize”按钮使用
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    """解析 token 并获取当前用户。

    工作流程：
    1) 从 Authorization header 取出 token
    2) jwt.decode 校验签名/解析 payload
    3) 从 payload 中读取 sub（我们存的是 email）
    4) 到数据库查用户是否存在

    若 token 无效/过期/用户不存在 -> 抛出 401。

    这个函数的典型用法：
    - 在需要登录才能访问的接口中写：
      current_user: User = Depends(auth.get_current_user)
    """

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1) 解码 token
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # sub 是 JWT 常用字段，我们这里用它存 email
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        # token 被篡改/过期/格式错误
        raise credentials_exception

    # 2) 数据库查用户
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception

    # 3) 用户是否可用
    if not user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")

    return user

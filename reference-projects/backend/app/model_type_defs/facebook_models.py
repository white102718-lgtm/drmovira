"""
Facebook 相关数据模型定义
包括 OAuth token、用户信息、数据库存储模型等
"""

from typing import Optional
from pydantic import BaseModel


class FacebookTokenResponse(BaseModel):
    """Facebook OAuth token 响应"""
    access_token: str
    token_type: str
    expires_in: int


class FacebookUserInfo(BaseModel):
    """Facebook 用户基本信息"""
    id: str
    name: Optional[str] = None
    email: Optional[str] = None


class FacebookAccountInDB(BaseModel):
    """
    MongoDB 中存储的 Facebook 账户信息
    用于持久化保存用户绑定的Facebook账户
    """
    facebook_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    app_id: str
    access_token: str
    app_secret: str
    expires_in: int
    created_at: str
    updated_at: str
    status : bool
    user_name: str


class FacebookCallbackResponse(BaseModel):
    """
    Facebook 回调成功响应
    返回绑定的账户信息
    """
    facebook_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    app_id: str
    message: str = "Facebook账户绑定成功"

from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    username: Optional[str] = Field(None)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    real_name: str                                      # 英文缩写,= ERP sys_user.name_abbr
    full_name: Optional[str] = None                     # 中文姓名,= ERP sys_user.nick_name
    roles: List[str] = []                               # 系统角色,JIT 时根据 ERP user_type + dept_name 映射
    ips: List[str] = []
    status: Optional[int] = 1
    department: Optional[str] = None                    # 本人归属部门,= ERP sys_dept.dept_name(via sys_user.dept_id)
    departments: Optional[List[str]] = []               # 可见部门集合,SUPER_ADMIN=["全部"],其余=[本部门]
    mfa_enabled: Optional[bool] = None                  # MFA 状态来自 ERP sys_user.mfa_enabled

    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v):
        return str(v) if v is not None else None

    @field_validator("username", "real_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class UserCreate(UserModel):
    password: str
    full_name: str


class UserUpdate(UserModel):
    password: Optional[str] = None
    username: Optional[str] = None
    real_name: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: Optional[str] = None
    roles: Optional[List[str]] = []


DEPT_ALL = "全部"  # 全部 部门 


class Roles:
    ADMIN = "admin"
    OPERATOR = "operator"
    OPERATOR_LEADER = "operator_leader"
    DEVELOPER = "developer"
    CREATOR = "creator"
    TEST = "test"
    AM = "am"
    BETA = "beta"
    OPERATOR_ALL = [OPERATOR, OPERATOR_LEADER]


class RoleBase(BaseModel):
    remark: Optional[str] = None
    permissions: List[str | None] = None
    status: int = 1


class RoleCreate(RoleBase):
    name: str


class RoleUpdate(RoleBase):
    name: Optional[str] = None
    _id: str


class RoleOut(RoleCreate, RoleUpdate):
    create_time: Optional[str] = None
    update_time: Optional[str] = None

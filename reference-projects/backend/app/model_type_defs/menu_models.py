from enum import Enum
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class MetaData(BaseModel):
    icon: Optional[str] = None
    activeIcon: Optional[str] = None
    title: str
    affixTab: Optional[bool] = None
    order: Optional[int] = None
    badge: Optional[str] = None
    badgeType: Optional[str] = None
    badgeVariants: Optional[str] = None
    iframeSrc: Optional[str] = None
    link: Optional[str] = None
    keepAlive: Optional[bool] = None
    hideInMenu: Optional[bool] = None
    hideChildrenInMenu: Optional[bool] = None
    hideInBreadcrumb: Optional[bool] = None
    hideInTab: Optional[bool] = None


class MenuType(str, Enum):
    menu = "menu"
    catalog = "catalog"
    action = "action"
    link = "link"
    embedded = "embedded"


class MenuItem(BaseModel):
    name: str
    status: Literal[0, 1] = 1
    type: MenuType
    path: str
    component: Optional[str] = None
    meta: MetaData
    pid: Optional[str] = None
    activePath: Optional[str] = None
    authCode: Optional[str] = None
    divider1: Optional[str] = None
    linkSrc: Optional[str] = None
    restricted_roles: Optional[List[str]] = None  # 限定可见角色，设置后仅列表内角色可见（admin 也不例外）


class MenuOut(BaseModel):
    children: Optional[List["MenuItem"]] = Field(default_factory=list)


# 当没有使用 "from __future__ import annotations" 时，需要更新 forward refs前向引用, 递归
MenuItem.model_rebuild()

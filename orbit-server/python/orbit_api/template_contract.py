"""模板只保存原配置树与明确接收者；账户/身份/分配从不进入模板合同。"""

from typing import Literal

from pydantic import Field

from orbit_api.launch_contract import (
    CampaignConfig,
    PlanOwnership,
    campaigns,
    ensure_config_size,
    fail,
    parse_model,
    text_field,
    unique_ids,
    uuid_field,
)
from orbit_api.launch_expansion import clone_campaigns
from orbit_api.reference_contract import StrictInput


class TemplateWrite(StrictInput):
    name: str
    description: str
    visibility: Literal["PRIVATE", "TEAM"]
    recipient_user_ids: list[str] = Field(max_length=500)
    campaigns: list[CampaignConfig] = Field(min_length=1, max_length=10000)


class TemplateApply(StrictInput):
    ownership: PlanOwnership
    reason: str


class TemplateArchive(StrictInput):
    reason: str


class TemplateShare(StrictInput):
    recipient_user_ids: list[str] = Field(min_length=1, max_length=500)
    reason: str


def parse_template(raw):
    value = parse_model(raw, TemplateWrite)
    value["name"] = text_field(value["name"], ("name",), 80)
    value["description"] = text_field(
        value["description"], ("description",), 500, minimum=0, multiline=True
    )
    value["recipient_user_ids"] = unique_ids(value["recipient_user_ids"], ("recipient_user_ids",))
    if value["visibility"] == "PRIVATE" and value["recipient_user_ids"]:
        fail(("recipient_user_ids",), "私有模板不得包含共享接收者")
    campaigns(value["campaigns"])
    ensure_config_size(value)
    return value


def parse_template_action(raw, action):
    value = parse_model(
        raw, {"apply": TemplateApply, "share": TemplateShare, "archive": TemplateArchive}[action]
    )
    value["reason"] = text_field(value["reason"], ("reason",), 1000, multiline=True)
    if action == "share":
        value["recipient_user_ids"] = unique_ids(
            value["recipient_user_ids"], ("recipient_user_ids",)
        )
    elif action == "apply":
        for key in ("owner_user_id", "owner_team_id"):
            value["ownership"][key] = uuid_field(value["ownership"][key], ("ownership", key))
    return value


def template_draft(template, ownership):
    """仅用于已验当前模板读取/加载权限后的原子新计划写入，不代表已授权。"""
    return {
        "name": "",
        "ownership": dict(ownership),
        "account_ids": [],
        "channel_id": None,
        "campaigns": clone_campaigns(template["campaigns"]),
        "identity_bindings": [],
        "asset_ids": [],
        "allow_repeat": False,
        "activate_after_create": False,
        "execution_mode": "META_API",
    }

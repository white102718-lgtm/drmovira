"""正式租户扫描选择：配置快照前后复验，并在外层收据事务内锁定来源版本。"""

import asyncio
import json
from dataclasses import dataclass

from sqlalchemy import text

from orbit_api.errors import OrbitError
from orbit_api.material_scanner_registry import MaterialScannerRegistry, ScannerBinding
from orbit_api.material_worker import MaterialWorker


@dataclass(frozen=True, repr=False)
class ScannerSelection:
    tenant_id: str
    configuration_id: str
    configuration_revision: int
    binding: ScannerBinding
    registry: MaterialScannerRegistry


async def select_scanner(session, tenant_id, registry, *, lock=False):
    rows = (
        (
            await session.execute(
                text(
                    "SELECT id,revision,enabled,settings_json FROM orbit_system_configuration "
                    "WHERE tenant_id=:tenant AND section='MATERIAL_SCANNER' LIMIT 2"
                    + (" FOR SHARE" if lock else "")
                ),
                {"tenant": tenant_id},
            )
        )
        .mappings()
        .all()
    )
    if len(rows) != 1 or not rows[0]["enabled"]:
        raise OrbitError(503, "SCANNER_CONFIGURATION_UNAVAILABLE", "本租户尚未启用可信扫描配置")
    row = rows[0]
    try:
        settings = (
            json.loads(row["settings_json"])
            if isinstance(row["settings_json"], str)
            else row["settings_json"]
        )
        if not isinstance(settings, dict) or set(settings) != {"profileId"}:
            raise ValueError
        binding = registry.resolve(settings["profileId"])
    except (ValueError, TypeError, KeyError, OrbitError):
        raise OrbitError(503, "SCANNER_CONFIGURATION_UNAVAILABLE", "本租户扫描候选不可用") from None
    return ScannerSelection(tenant_id, row["id"], row["revision"], binding, registry)


async def verify_selection(session, selection, claim, profile):
    if not isinstance(selection, ScannerSelection) or selection.tenant_id != claim["tenant_id"]:
        raise OrbitError(409, "SCANNER_CONFIGURATION_CHANGED", "扫描来源租户不符")
    current = await select_scanner(session, selection.tenant_id, selection.registry, lock=True)
    if current != selection or selection.binding.profile != profile:
        raise OrbitError(409, "SCANNER_CONFIGURATION_CHANGED", "扫描期间配置或实例已变化")
    selection.registry.verify(selection.binding, source=False)


class ConfiguredMaterialWorker(MaterialWorker):
    """实例逐项处理租户选择，不把上一个租户的scanner沿用为另一个租户的默认值。"""

    def __init__(self, session_factory, objects, *, registry=None, **kwargs):
        if "scanner" in kwargs or "runtime_profile_provider" in kwargs:
            raise ValueError("正式Worker仅允许受控注册表选择扫描器")
        super().__init__(session_factory, objects, **kwargs)
        self.registry = registry if registry is not None else MaterialScannerRegistry()
        self._selection = None
        self._run_lock = asyncio.Lock()

    async def run_once(self, limit=10):
        # 同一Worker实例的租户选择不得被并发run_once覆盖；跨进程仍由数据库认领保护。
        async with self._run_lock:
            try:
                return await super().run_once(limit)
            finally:
                self._selection = None

    async def current_runtime_profile(self, claim):
        async with self.sessions() as session, session.begin():
            selected = await select_scanner(session, claim["tenant_id"], self.registry)
        self.registry.verify(selected.binding)
        if self._selection is None:
            self._selection = selected
            self.scanner = selected.binding.scanner
        elif self._selection != selected:
            raise OrbitError(503, "ANTIVIRUS_RUNTIME_UNVERIFIED", "扫描期间租户配置已变化")
        return selected.binding.profile

    async def claim(self):
        self._selection = None
        return await super().claim()

    def runtime_selection(self, claim):
        if self._selection is None or self._selection.tenant_id != claim["tenant_id"]:
            raise OrbitError(409, "SCANNER_CONFIGURATION_CHANGED", "缺少正式租户扫描来源")
        return self._selection

    async def runtime_source_current(self, session, claim):
        try:
            selection = self.runtime_selection(claim)
            # 媒体完成只复核配置/实例代际，不把扫描时有效证明变成全对象有效期TTL。
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT id,revision,enabled,settings_json "
                            "FROM orbit_system_configuration WHERE tenant_id=:tenant "
                            "AND section='MATERIAL_SCANNER' LIMIT 2 FOR SHARE"
                        ),
                        {"tenant": claim["tenant_id"]},
                    )
                )
                .mappings()
                .all()
            )
            if len(rows) != 1:
                return False
            row = rows[0]
            settings = (
                json.loads(row["settings_json"])
                if isinstance(row["settings_json"], str)
                else row["settings_json"]
            )
            return bool(
                row["enabled"]
                and row["id"] == selection.configuration_id
                and row["revision"] == selection.configuration_revision
                and settings == {"profileId": selection.binding.profile.profile_id}
                and self.registry.same_generation(selection.binding)
            )
        except OrbitError:
            return False

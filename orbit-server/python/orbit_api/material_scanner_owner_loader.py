"""显式私有ORBIT配置DTO；不写env、不发现进程、不从SQL审计复建registry。"""

import hashlib
import json
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path

from orbit_api.material_antivirus import ClamdPolicy
from orbit_api.material_scanner_owner_definition import (
    OWNER_DEFINITIONS_KEY,
    ScannerOwnerDefinition,
    owner_error,
)

OWNER_ENABLED_KEY = "ORBIT_PYTHON_MATERIAL_SCANNER_OWNER_ENABLED"


@dataclass(frozen=True, repr=False)
class OwnerConfiguration:
    enabled: bool
    definition: ScannerOwnerDefinition | None
    sha256: str


def _unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError
        result[name] = value
    return result


def _utc(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError
    return parsed.astimezone(UTC)


def _canonical(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    raise TypeError


def disabled_owner_configuration():
    return OwnerConfiguration(False, None, hashlib.sha256(b'{"enabled":false}').hexdigest())


def load_owner_configuration(values_provider=None, *, now=None):
    """只有显式调用才读指定private_values；未配置enabled默认为关闭且不访问artifact。"""
    if values_provider is None:
        from config.orbit_runtime import private_values

        values_provider = private_values
    try:
        values = values_provider()
        if not isinstance(values, dict):
            raise ValueError
        enabled = values.get(OWNER_ENABLED_KEY, "false")
        if type(enabled) is not str or enabled not in {"true", "false"}:
            raise ValueError
        if enabled == "false":
            return disabled_owner_configuration()
        raw = values.get(OWNER_DEFINITIONS_KEY)
        if not isinstance(raw, str) or not 0 < len(raw.encode("utf-8")) <= 256 * 1024:
            raise ValueError
        definitions = json.loads(raw, object_pairs_hook=_unique)
        if not isinstance(definitions, dict) or len(definitions) != 1:
            raise ValueError
        profile_id, source = next(iter(definitions.items()))
        names = {field.name for field in fields(ScannerOwnerDefinition)}
        # profile_id以映射键为唯一来源，避免重复声明相互矛盾。
        if not isinstance(source, dict) or set(source) != names - {"profile_id"}:
            raise ValueError
        parsed = dict(source)
        for name in (
            "installation_root",
            "owned_root",
            "executable",
            "config_file",
            "database_directory",
            "release_receipt_file",
        ):
            value = parsed[name]
            if not isinstance(value, str) or value.strip() != value or len(value) > 1024:
                raise ValueError
            path = Path(value)
            if not path.is_absolute() or value.startswith(("\\\\", "//")):
                raise ValueError
            parsed[name] = path
        for name in ("issued_at", "expires_at"):
            parsed[name] = _utc(parsed[name])
        databases = parsed["database_files"]
        if not isinstance(databases, dict):
            raise ValueError
        parsed["database_files"] = tuple(sorted(databases.items()))
        policy = parsed["policy"]
        if not isinstance(policy, dict) or set(policy) != {
            field.name for field in fields(ClamdPolicy)
        }:
            raise ValueError
        policy = dict(policy)
        policy["daily_db_built_at"] = _utc(policy["daily_db_built_at"])
        parsed["policy"] = ClamdPolicy(**policy)
        definition = ScannerOwnerDefinition(profile_id=profile_id, **parsed)
        definition.validate(now or datetime.now(UTC))
        canonical = json.dumps(
            {"enabled": True, "definition": asdict(definition)},
            default=_canonical,
            sort_keys=True,
            separators=(",", ":"),
        )
        return OwnerConfiguration(True, definition, hashlib.sha256(canonical.encode()).hexdigest())
    except Exception:
        raise owner_error("SCANNER_OWNER_CONFIGURATION_INVALID") from None

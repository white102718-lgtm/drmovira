"""016原子唯一性纠偏真实MySQL专项；只允许当前主线隔离库，尚未排队执行。"""

import re
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MATERIAL_TAXONOMY_MIGRATION_CASES = [
    "pythonMaterialTaxonomyMigrationRejectsExistingCrossGroupDuplicateWithoutDataLoss",
    "pythonMaterialTaxonomyMigrationEnforcesTenantKindNameUniqueWithoutGroupBypass",
]


def run_material_taxonomy_migration_checks(admin, database, cases):
    """调用方统一排队；临时克隆表不含用户素材，finally仅删除本次固定前缀UUID表。"""
    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database):
        raise ValueError("标签分类迁移专项只能在当前隔离测试库执行")
    if admin.host not in {"localhost", "127.0.0.1"} or admin.port != 13306:
        raise ValueError("标签分类迁移专项只能使用本机隔离MySQL")
    source = (ROOT / "python/orbit_api/migrations/016_material_taxonomy_contract.sql").read_text(
        encoding="utf-8-sig"
    )
    created = []
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        actual = cursor.fetchone()[0]
        if isinstance(actual, bytes):
            actual = actual.decode()
        if actual != database:
            raise ValueError("标签分类迁移专项当前数据库不匹配")
        try:
            for conflicting in (True, False):
                table = "orbit_taxonomy_contract_" + uuid4().hex
                cursor.execute(f"CREATE TABLE `{table}` LIKE orbit_material_taxonomy")
                created.append(table)
                cursor.execute(f"SHOW INDEX FROM `{table}`")
                indexes = {row[2] for row in cursor.fetchall()}
                # 可在through015或through016运行；每次构造准确的010旧约束，不改业务原表。
                if "uq_material_taxonomy_kind_name" in indexes:
                    cursor.execute(
                        f"ALTER TABLE `{table}` DROP INDEX uq_material_taxonomy_kind_name"
                    )
                if "idx_material_taxonomy_kind_page" in indexes:
                    cursor.execute(
                        f"ALTER TABLE `{table}` DROP INDEX idx_material_taxonomy_kind_page"
                    )
                if "uq_material_taxonomy_name" not in indexes:
                    cursor.execute(
                        f"ALTER TABLE `{table}` ADD UNIQUE KEY "
                        "uq_material_taxonomy_name(tenant_id,kind,group_name,name)"
                    )
                tenant, other_tenant = str(uuid4()), str(uuid4())

                def insert(owner, kind, name, group, target_table=table):
                    cursor.execute(
                        f"INSERT INTO `{target_table}`(tenant_id,id,kind,name,group_name) "
                        "VALUES(%s,%s,%s,%s,%s)",
                        (owner, str(uuid4()), kind, name, group),
                    )

                insert(tenant, "TAG", "合同同名标签", "第一组")
                if conflicting:
                    insert(tenant, "TAG", "合同同名标签", "第二组")
                admin.commit()
                migration = source.replace("orbit_material_taxonomy", f"`{table}`")
                try:
                    cursor.execute(migration)
                    while cursor.nextset():
                        pass
                except Exception as error:
                    assert conflicting and getattr(error, "args", (None,))[0] == 1062, (
                        "TAXONOMY_MIGRATION_UNEXPECTED_FAILURE"
                    )
                else:
                    assert not conflicting, "已有跨分组重名应明确阻断迁移"
                if conflicting:
                    cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                    assert cursor.fetchone()[0] == 2
                    cursor.execute(f"SHOW INDEX FROM `{table}`")
                    names = {row[2] for row in cursor.fetchall()}
                    assert "uq_material_taxonomy_name" in names
                    assert "uq_material_taxonomy_kind_name" not in names
                    cases.append(MATERIAL_TAXONOMY_MIGRATION_CASES[0])
                else:
                    try:
                        insert(tenant, "TAG", "合同同名标签", "第三组")
                    except Exception as error:
                        assert getattr(error, "args", (None,))[0] == 1062
                    else:
                        raise AssertionError("分组不能绕过同类名称唯一约束")
                    insert(other_tenant, "TAG", "合同同名标签", "第一组")
                    insert(tenant, "CATEGORY", "合同同名标签", "")
                    admin.commit()
                    cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                    assert cursor.fetchone()[0] == 3
                    cases.append(MATERIAL_TAXONOMY_MIGRATION_CASES[1])
        finally:
            admin.rollback()
            for table in created:
                if not re.fullmatch(r"orbit_taxonomy_contract_[0-9a-f]{32}", table):
                    raise ValueError("标签专项临时表名无效，拒绝清理")
                cursor.execute(f"DROP TABLE `{table}`")

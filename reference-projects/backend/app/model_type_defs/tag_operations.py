from datetime import datetime, timedelta
from typing import Dict, List, Optional

from app.db.async_mysql import AsyncMySQL


async def add_tags_to_doris(db: AsyncMySQL, basenames: List[str], tags: List[str]):
    """
    使用Doris 3.0批量更新语句为广告添加标签
    使用ARRAY_DISTINCT和ARRAY_CONCAT确保标签唯一性
    """
    if not basenames or not tags:
        return True

    # 构建新标签数组
    new_tags = []
    for tag in tags:
        new_tags.append(f"'{tag}'")
    tags_array = ", ".join(new_tags)

    # 构建WHERE条件：广告名称在指定列表中
    ad_names_condition = "', '".join(basenames)
    select_sql = f"""
    SELECT unique_name
    FROM ad_materials
    WHERE unique_name IN ('{ad_names_condition}')
    """
    exist_ads = await db.fetchall(select_sql)
    exist_ads = {ad[0] for ad in exist_ads}
    # Doris 3.0批量更新SQL - 添加标签并去重
    update_sql = f"""
    UPDATE ad_materials
    SET tags = CASE
        WHEN tags IS NULL THEN ARRAY({tags_array})
        ELSE ARRAY_DISTINCT(ARRAY_CONCAT(tags, ARRAY({tags_array})))
    END
    WHERE unique_name IN ('{ad_names_condition}')
    """
    await db.execute(update_sql)
    return set(basenames) - exist_ads


async def insert_material_to_doris(db: AsyncMySQL, basename: str, tags: List[str]):
    """
    将新素材插入到 Doris 的 ad_materials 表
    如果已存在则更新 tags
    """
    if not basename:
        return

    # 构建 tags 数组
    if tags:
        tags_array = ", ".join(f"'{tag}'" for tag in tags)
        tags_value = f"ARRAY({tags_array})"
    else:
        tags_value = "NULL"

    # 使用 INSERT ... ON DUPLICATE KEY UPDATE 语法（Doris UNIQUE KEY 表支持 UPSERT）
    insert_sql = f"""
    INSERT INTO ad_materials (unique_name, tags)
    VALUES ('{basename}', {tags_value})
    """
    num = await db.execute(insert_sql)


async def insert_materials_to_doris(db: AsyncMySQL, basenames: List[str]):
    """批量把新素材插入 Doris ad_materials：一次多行 INSERT，避免逐条单插的事务/版本开销。
    tags 统一为 NULL，与 insert_material_to_doris(tags=[]) 行为一致。"""
    if not basenames:
        return
    values = ", ".join(f"('{b}', NULL)" for b in basenames)
    await db.execute(f"INSERT INTO ad_materials (unique_name, tags) VALUES {values}")


async def remove_tags_from_doris(db, basenames: List[str], tags: List[str]):
    """
    使用Doris 3.0批量更新语句从广告中移除标签
    使用简单的数组函数，避免复杂的lambda表达式
    """
    if not basenames or not tags:
        return True

    # 构建要移除的标签数组
    remove_tags = []
    for tag in tags:
        remove_tags.append(f"'{tag}'")
    remove_tags_array = ", ".join(remove_tags)

    # 构建WHERE条件：广告名称在指定列表中
    ad_names_condition = "', '".join(basenames)

    select_sql = f"""
    SELECT unique_name
    FROM ad_materials
    WHERE unique_name IN ('{ad_names_condition}')
    """
    exist_ads = await db.fetchall(select_sql)
    exist_ads = {ad[0] for ad in exist_ads}
    # Doris 3.0批量更新SQL - 移除标签
    # tags 列是 JSON 类型，需要先转换为 ARRAY
    update_sql = f"""
    UPDATE ad_materials
    SET tags = CASE
        WHEN tags IS NULL THEN NULL
        ELSE ARRAY_EXCEPT(CAST(tags AS ARRAY<VARCHAR>), ARRAY({remove_tags_array}))
    END
    WHERE unique_name IN ('{ad_names_condition}')
    """
    await db.execute(update_sql)
    return set(basenames) - exist_ads


def build_ad_where_conditions(
    base_conditions: List[str],
    game_platform: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    table_alias: str = "ad",
    date_field: str = "create_time",
) -> str:
    """
    构建广告数据查询的 WHERE 子句

    Args:
        base_conditions: 基础条件列表（如标签过滤条件）
        game_platform: 平台筛选
        start_date: 开始日期
        end_date: 结束日期
        table_alias: 表别名，默认为 "ad"

    Returns:
        完整的 WHERE 子句字符串

    Example:
        >>> build_ad_where_conditions(
        ...     base_conditions=["array_contains(m.tags, '1')"],
        ...     game_platform="Facebook",
        ...     start_date="2025-01-01",
        ...     end_date="2025-01-31"
        ... )
        "array_contains(m.tags, '1') AND ad.game_platform = 'Facebook' AND (ad.date BETWEEN '2025-01-01' AND '2025-01-31')"
    """
    conditions = base_conditions.copy()

    if game_platform:
        conditions.append(f"{table_alias}.game_platform = '{game_platform}'")

    if start_date and end_date:
        time_field = date_field if date_field in {"create_time", "date"} else "create_time"
        actual_end = end_date
        if time_field == "create_time" and start_date == end_date:
            actual_end = (
                datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y-%m-%d")
        conditions.append(
            f"({table_alias}.{time_field} BETWEEN '{start_date}' AND '{actual_end}')"
        )

    return " AND ".join(conditions)


def build_select_fields(stat_columns: Dict[str, str]) -> List[str]:
    """
    构建 SELECT 字段列表

    Args:
        stat_columns: 统计列字典，key为中文列名，value为SQL表达式

    Returns:
        SELECT 字段列表

    Example:
        >>> stat_cols = {"花费金额": "ROUND(SUM(ad.amount_spent), 2)"}
        >>> build_select_fields(stat_cols)
        ["ROUND(SUM(ad.amount_spent), 2) AS `花费金额`"]
    """
    return [f"{expr} AS `{field}`" for field, expr in stat_columns.items()]

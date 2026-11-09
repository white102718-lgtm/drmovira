"""
素材统计Excel导出脚本

功能：
1. 从MongoDB materials集合查询素材，按creative_editor分组
2. 提取每组的basename列表
3. 使用basename查询Doris的ad_hourly_detail表，统计2025年12月的数据
4. 生成Excel文件，包含汇总Sheet和各编辑器详细Sheet

运行方式：
    python script/export_materials_stats.py
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

import pandas as pd
from openpyxl import load_workbook

from app.db.clients import get_db
from app.db.mongo import cols

# 配置日志 - 输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def fetch_basenames_with_spending_in_december(db):
    """
    从Doris查询12月有消耗的素材basename列表

    Args:
        db: 数据库连接

    Returns:
        list: basename列表
    """
    logger.info("从Doris查询12月有消耗的素材...")

    sql = """
    SELECT DISTINCT unique_name
    FROM ad_hourly_detail
    WHERE level = 'ad'
      AND date >= '2026-01-01'
      AND date < '2026-01-31'
      AND amount_spent > 0
    """

    rows = await db.fetchall(sql, as_dict=True)
    basenames = [row['unique_name'] for row in rows]

    logger.info(f"找到{len(basenames)}个12月有消耗的素材")
    return basenames


async def fetch_materials_grouped_by_editor(collection, basenames):
    """
    从MongoDB按creative_editor分组获取指定basename的materials

    Args:
        collection: MongoDB materials集合
        basenames: 要查询的basename列表

    Returns:
        dict: {
            "编辑器A": [{"basename": "xxx", ...}, ...],
            "编辑器B": [...],
            "未分类": [...]  # 没有creative_editor的文档
        }
    """
    logger.info(f"从MongoDB查询{len(basenames)}个素材的信息...")
    grouped = defaultdict(list)

    cursor = collection.find(
        {"basename": {"$in": basenames}},
        projection={
            "basename": 1,
            "creative_editor": 1,
            "filename": 1,
        },
    )

    count = 0
    async for material in cursor:
        editor = material.get("creative_editor") or "未分类"
        grouped[editor].append(material)
        count += 1

    logger.info(f"成功获取{count}个素材，共{len(grouped)}个creative_editor分组")
    for editor_name, materials in grouped.items():
        logger.info(f"  - {editor_name}: {len(materials)}个素材")

    return dict(grouped)


async def fetch_ad_stats_for_basenames(
    db,
    basenames: List[str],
    batch_size: int = 100,
):
    """
    从Doris查询统计数据

    Args:
        db: 数据库连接
        basenames: basename列表
        batch_size: 批量查询大小

    Returns:
        dict: {
            "basename1": {"花费金额": 1234.56, "展示次数": 10000, ...},
            "basename2": {...}
        }
    """
    # 统计字段定义
    stat_columns = {
        "投手ID": "MAX(placer_id)",
        "花费金额": "ROUND(SUM(amount_spent), 2)",
    }

    results = {}
    total_batches = (len(basenames) + batch_size - 1) // batch_size

    # 分批查询（避免SQL过长）
    for i in range(0, len(basenames), batch_size):
        batch = basenames[i : i + batch_size]
        batch_num = i // batch_size + 1
        logger.info(f"批次 {batch_num}/{total_batches}: 查询{len(batch)}个basename...")

        in_clause = ", ".join(f"'{name}'" for name in batch)
        select_clause = ", ".join(
            f"{expr} AS `{col}`" for col, expr in stat_columns.items()
        )

        # 关键SQL - 使用date字段而非create_time
        sql = f"""
        SELECT
            unique_name,
            {select_clause}
        FROM ad_hourly_detail
        WHERE level = 'ad'
          AND unique_name IN ({in_clause})
          AND date >= '2025-12-01'
          AND date < '2026-01-01'
        GROUP BY unique_name
        """

        try:
            rows = await db.fetchall(sql, as_dict=True)

            for row in rows:
                basename = row.pop("unique_name")
                # 清理None值，区分数值字段和字符串字段
                cleaned_row = {}
                for k, v in row.items():
                    if k == "投手ID":
                        cleaned_row[k] = v if v is not None else ""
                    else:
                        cleaned_row[k] = v if v is not None else 0
                results[basename] = cleaned_row

            # 为没有数据的basename填充默认值
            for basename in batch:
                if basename not in results:
                    default_row = {}
                    for col in stat_columns.keys():
                        if col == "投手ID":
                            default_row[col] = ""
                        else:
                            default_row[col] = 0
                    results[basename] = default_row

            logger.info(
                f"批次 {batch_num}/{total_batches}: 完成，获得{len(rows)}条有效数据"
            )

        except Exception as e:
            logger.error(f"查询批次 {batch_num} 失败: {e}")
            # 出错时填充默认值
            for basename in batch:
                if basename not in results:
                    default_row = {}
                    for col in stat_columns.keys():
                        if col == "投手ID":
                            default_row[col] = ""
                        else:
                            default_row[col] = 0
                    results[basename] = default_row

    return results


async def aggregate_materials_stats(materials_groups, db):
    """
    聚合所有编辑器组的统计数据

    Args:
        materials_groups: 按编辑器分组的素材
        db: 数据库连接

    Returns:
        dict: {editor_name: DataFrame}
    """
    result = {}

    for editor_name, materials in materials_groups.items():
        logger.info(f"处理creative_editor: '{editor_name}' (共{len(materials)}个素材)")

        basenames = [m["basename"] for m in materials]
        stats_dict = await fetch_ad_stats_for_basenames(db, basenames)

        rows = []
        for basename in basenames:
            stats = stats_dict.get(basename, {})
            row = {"basename": basename, "creative_editor": editor_name}
            row.update(stats)
            rows.append(row)

        df = pd.DataFrame(rows)
        result[editor_name] = df
        logger.info(f"完成creative_editor '{editor_name}' 的数据聚合")

    return result


def create_summary_sheet(dataframes):
    """
    生成汇总Sheet，展示各creative_editor的总计

    Args:
        dataframes: 各编辑器的DataFrame字典

    Returns:
        DataFrame: 汇总数据
    """
    logger.info("生成汇总Sheet...")

    # 获取统计列名（排除basename和creative_editor）
    sample_df = next(iter(dataframes.values()))
    stat_columns = [
        col for col in sample_df.columns if col not in ["basename", "creative_editor"]
    ]

    summary_rows = []

    for editor_name, df in dataframes.items():
        row = {
            "creative_editor": editor_name,
            "素材数": len(df),
        }
        for col in stat_columns:
            if col in df.columns:
                # 区分数值字段和非数值字段
                if col == "投手ID":
                    # 投手ID统计去重数量
                    row[col] = df[col].nunique()
                else:
                    # 数值字段求和
                    row[col] = round(df[col].sum(), 2)
        summary_rows.append(row)

    # 添加全部总计行
    total_row = {
        "creative_editor": "全部总计",
        "素材数": sum(row["素材数"] for row in summary_rows),
    }
    for col in stat_columns:
        if col == "投手ID":
            # 投手ID：统计所有DataFrame中去重的投手ID总数
            all_placer_ids = set()
            for df in dataframes.values():
                if col in df.columns:
                    all_placer_ids.update(df[col].dropna().unique())
            total_row[col] = len(all_placer_ids)
        else:
            # 数值字段：求和
            total_row[col] = round(sum(row.get(col, 0) for row in summary_rows), 2)
    summary_rows.append(total_row)

    logger.info(f"汇总Sheet生成完成，共{len(summary_rows)}行")
    return pd.DataFrame(summary_rows)


def generate_excel_file(summary_df, detail_dataframes, output_dir="."):
    """
    生成Excel文件，包含汇总Sheet和详细Sheets

    Args:
        summary_df: 汇总DataFrame
        detail_dataframes: 详细数据字典
        output_dir: 输出目录

    Returns:
        str: 生成的文件路径
    """
    logger.info("开始生成Excel文件...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"materials_stats_{timestamp}.xlsx"
    filepath = Path(output_dir) / filename

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        # 第一个Sheet：汇总
        summary_df.to_excel(writer, sheet_name="汇总", index=False)
        logger.info("已写入Sheet: 汇总")

        # 后续Sheets：各编辑器详细数据
        for editor_name, df in detail_dataframes.items():
            # Sheet名称限制31字符
            sheet_name = (
                editor_name[:31] if len(editor_name) <= 31 else editor_name[:28] + "..."
            )
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            logger.info(f"已写入Sheet: {sheet_name}")

    # 样式优化：自动列宽和冻结首行
    logger.info("优化Excel样式...")
    wb = load_workbook(filepath)
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]

        # 自动列宽
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value or "")) > max_length:
                        max_length = len(str(cell.value or ""))
                except:
                    pass
            adjusted_width = min(max(max_length + 2, 10), 50)
            ws.column_dimensions[column_letter].width = adjusted_width

        # 冻结首行
        ws.freeze_panes = "A2"

    wb.save(filepath)
    logger.info("样式优化完成")

    return str(filepath)


async def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始生成Excel报表: 素材统计数据 (2025年12月)")
    logger.info("=" * 60)

    # 初始化数据库连接
    materials_collection = cols.materials
    db_gen = get_db()
    db = await db_gen.__anext__()

    try:
        # Step 1: 从Doris查询12月有消耗的素材
        basenames_with_spending = await fetch_basenames_with_spending_in_december(db)
        if not basenames_with_spending:
            logger.warning("12月没有找到有消耗的素材")
            return

        # Step 2: 从MongoDB查询这些素材的信息并按剪辑师分组
        materials_groups = await fetch_materials_grouped_by_editor(
            materials_collection, basenames_with_spending
        )
        if not materials_groups:
            logger.warning("未找到materials数据")
            return

        # Step 3: Doris统计查询
        detail_dfs = await aggregate_materials_stats(materials_groups, db)

        # Step 4: 生成汇总
        summary_df = create_summary_sheet(detail_dfs)

        # Step 5: 生成Excel
        output_path = generate_excel_file(summary_df, detail_dfs)

        logger.info("=" * 60)
        logger.info(f"报表生成完成! 文件位置: {output_path}")
        logger.info("=" * 60)
        return output_path

    except Exception as e:
        logger.error(f"报表生成失败: {e}", exc_info=True)
        raise
    finally:
        await db_gen.aclose()


if __name__ == "__main__":
    asyncio.run(main())

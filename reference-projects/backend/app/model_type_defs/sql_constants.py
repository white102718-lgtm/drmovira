"""
SQL相关的常量和辅助函数

包含SQL查询中常用的表达式、列定义等
"""
from typing import Dict


def get_ad_stat_columns(table_alias: str = "ad") -> Dict[str, str]:
    """
    获取广告统计列定义（SQL聚合表达式）

    Args:
        table_alias: 表别名，默认为 "ad"

    Returns:
        统计列字典，key为中文列名，value为对应的SQL聚合表达式

    Example:
        >>> from app.model_type_defs.sql_constants import get_ad_stat_columns
        >>> stat_cols = get_ad_stat_columns("ad")
        >>> # 返回: {"花费金额": "ROUND(SUM(ad.amount_spent), 2)", ...}
    """
    return {
        "花费金额": f"ROUND(SUM({table_alias}.amount_spent), 2)",
        "覆盖人数": f"SUM({table_alias}.reach)",
        "展示次数": f"SUM({table_alias}.impressions)",
        "点击数": f"SUM({table_alias}.clicks_all)",
        "点击率": f"ROUND(SUM({table_alias}.clicks_all)/NULLIF(SUM({table_alias}.impressions), 0), 4)",
        "点击成本": f"ROUND(SUM({table_alias}.amount_spent)/NULLIF(SUM({table_alias}.clicks_all), 0), 2)",
        "链接点击数": f"SUM({table_alias}.inline_link_clicks)",
        "安装数": f"SUM({table_alias}.app_installs)",
        "注册数": f"SUM({table_alias}.complete_registration)",
        "注册转化率": f"ROUND(SUM({table_alias}.complete_registration)/NULLIF(SUM({table_alias}.clicks_all), 0), 4)",
        "注册成本": f"ROUND(SUM({table_alias}.amount_spent)/NULLIF(SUM({table_alias}.complete_registration), 0), 2)",
        "订阅数": f"SUM({table_alias}.subscribe_website)",
        "订阅成本": f"ROUND(SUM({table_alias}.amount_spent)/NULLIF(SUM({table_alias}.subscribe_website), 0), 2)",
        "订阅价值": f"ROUND(SUM({table_alias}.subscribe_website_values), 2)",
        "购物数": f"SUM({table_alias}.purchases)",
        "购物率": f"ROUND(SUM({table_alias}.purchases)/NULLIF(SUM({table_alias}.complete_registration), 0), 4)",
        "购物成本": f"ROUND(SUM({table_alias}.amount_spent)/NULLIF(SUM({table_alias}.purchases), 0), 2)",
        "购物价值": f"ROUND(SUM({table_alias}.purchases_value), 2)",
        "购物roas": f"ROUND(SUM({table_alias}.purchases_value)/NULLIF(SUM({table_alias}.amount_spent), 0), 2)",
    }

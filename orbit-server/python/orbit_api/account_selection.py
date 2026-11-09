"""账户目录唯一筛选SQL构造；固定列与参数，不接受用户SQL片段。"""


def selection_sql(query):
    """query来自原account_details_contract.filters规范化结果；别名固定为a。"""
    clauses, params = [], {}
    if query["q"]:
        external = query["q"][4:] if query["q"].startswith("act_") else query["q"]
        if external.isascii() and external.isdigit():
            clauses.append("a.external_id=:external")
            params["external"] = external
        else:
            clauses.append("a.name_prefix LIKE :search ESCAPE '!'")
            params["search"] = (
                query["q"].replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            )
    for field in ("account_status", "auth_status", "owner_user_id", "vendor_id"):
        if query.get(field):
            clauses.append(f"a.{field}=:{field}")
            params[field] = query[field]
    return clauses, params

import asyncio

from app.db.clients import get_db
from app.db.mongo import cols

collection = cols.materials
tree_tags_collection = cols.tree_tags


async def main():
    tags = await tree_tags_collection.find().to_list()
    gen = get_db()
    db = await gen.__anext__()  # 拿到 yield 出来的 db
    for tag_doc in tags:
        docs = await collection.find(
            {"tags_new": tag_doc["_id"]}, projection={"_id":0,'basename':1}
        ).to_list()
        basenames = [doc['basename'] for doc in docs]
        if not basenames:
            continue
        in_clause = ", ".join(f"'{name}'" for name in basenames)
        sql=f"""
        UPDATE ad_materials
        SET tags = CASE
              WHEN tags IS NULL OR cardinality(tags) = 0
              THEN ['{tag_doc['_id']}']
              ELSE ARRAY_DISTINCT(ARRAY_CONCAT(tags, ['{tag_doc['_id']}']))
           END
        WHERE unique_name IN ({in_clause});
        """
        r = await db.execute(sql)
        pass


if __name__ == "__main__":
    asyncio.run(main())

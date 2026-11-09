"""
MongoDB Data Migration Script
Migrate data from production to development environment

Collections to migrate:
- agent_line_config
- platform_config
- personal_accounts
- fb_pixels
- fb_pages
- fb_businesses
- fb_ad_accounts
"""
import sys
sys.path.insert(0, "D:\\backend\\backend")

from pymongo import MongoClient
# 使用前需设置对应环境变量或 .env 文件
from app.conf import MongodbConf as ProdMongoConf
# 如需迁移到另一个环境，手动设置第二组连接信息
DevMongoConf = ProdMongoConf  # TODO: 迁移时需分别配置两个环境的连接

# Collections to migrate
COLLECTIONS_TO_MIGRATE = [
    "agent_line_config",
    "platform_config",
    "personal_accounts",
    "fb_pixels",
    "fb_pages",
    "fb_businesses",
    "fb_ad_accounts",
]

# Database name
DATABASE_NAME = "plat"


def get_prod_client():
    """Get production MongoDB client"""
    return MongoClient(ProdMongoConf.CONNECTION)


def get_dev_client():
    """Get development MongoDB client"""
    return MongoClient(DevMongoConf.CONNECTION)


def migrate_collection(prod_db, dev_db, collection_name, clear_before_insert=True):
    """
    Migrate a single collection from prod to dev

    Args:
        prod_db: Production database
        dev_db: Development database
        collection_name: Name of the collection to migrate
        clear_before_insert: Whether to clear the dev collection before inserting
    """
    prod_collection = prod_db[collection_name]
    dev_collection = dev_db[collection_name]

    # Get all documents from production
    documents = list(prod_collection.find())
    doc_count = len(documents)

    if doc_count == 0:
        print(f"  [{collection_name}] No documents found in production, skipping...")
        return 0

    # Clear development collection if requested
    if clear_before_insert:
        deleted = dev_collection.delete_many({})
        print(f"  [{collection_name}] Cleared {deleted.deleted_count} documents from dev")

    # Insert documents into development
    if documents:
        result = dev_collection.insert_many(documents)
        inserted_count = len(result.inserted_ids)
        print(f"  [{collection_name}] Migrated {inserted_count} documents")
        return inserted_count

    return 0


def migrate_all(clear_before_insert=True):
    """
    Migrate all collections from production to development

    Args:
        clear_before_insert: Whether to clear dev collections before inserting
    """
    print("=" * 60)
    print("MongoDB Data Migration: Production -> Development")
    print("=" * 60)
    print(f"\nSource (Prod): {ProdMongoConf.HOST}:{ProdMongoConf.PORT}")
    print(f"Target (Dev):  {DevMongoConf.HOST}:{DevMongoConf.PORT}")
    print(f"Database: {DATABASE_NAME}")
    print(f"Collections: {', '.join(COLLECTIONS_TO_MIGRATE)}")
    print(f"Clear before insert: {clear_before_insert}")
    print("-" * 60)

    prod_client = None
    dev_client = None

    try:
        # Connect to both databases
        print("\nConnecting to production MongoDB...")
        prod_client = get_prod_client()
        prod_db = prod_client[DATABASE_NAME]
        print("  Connected to production")

        print("Connecting to development MongoDB...")
        dev_client = get_dev_client()
        dev_db = dev_client[DATABASE_NAME]
        print("  Connected to development")

        # Migrate each collection
        print("\n" + "-" * 60)
        print("Starting migration...")
        print("-" * 60)

        total_migrated = 0
        results = {}

        for collection_name in COLLECTIONS_TO_MIGRATE:
            try:
                count = migrate_collection(
                    prod_db, dev_db, collection_name, clear_before_insert
                )
                results[collection_name] = {"status": "success", "count": count}
                total_migrated += count
            except Exception as e:
                results[collection_name] = {"status": "error", "error": str(e)}
                print(f"  [{collection_name}] ERROR: {e}")

        # Print summary
        print("\n" + "=" * 60)
        print("Migration Summary")
        print("=" * 60)

        for collection_name, result in results.items():
            if result["status"] == "success":
                print(f"  [OK] {collection_name}: {result['count']} documents")
            else:
                print(f"  [FAIL] {collection_name}: {result['error']}")

        print("-" * 60)
        print(f"Total documents migrated: {total_migrated}")
        print("=" * 60)

        return results

    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        raise

    finally:
        if prod_client:
            prod_client.close()
            print("\nClosed production connection")
        if dev_client:
            dev_client.close()
            print("Closed development connection")


def preview_counts():
    """Preview document counts in both environments without migrating"""
    print("=" * 60)
    print("Document Count Preview")
    print("=" * 60)

    prod_client = None
    dev_client = None

    try:
        prod_client = get_prod_client()
        dev_client = get_dev_client()

        prod_db = prod_client[DATABASE_NAME]
        dev_db = dev_client[DATABASE_NAME]

        print(f"\n{'Collection':<25} {'Prod':<10} {'Dev':<10}")
        print("-" * 45)

        for collection_name in COLLECTIONS_TO_MIGRATE:
            prod_count = prod_db[collection_name].count_documents({})
            dev_count = dev_db[collection_name].count_documents({})
            print(f"{collection_name:<25} {prod_count:<10} {dev_count:<10}")

        print("=" * 60)

    finally:
        if prod_client:
            prod_client.close()
        if dev_client:
            dev_client.close()


def migrate_single_collection(collection_name, clear_before_insert=True):
    """Migrate a single specified collection"""
    if collection_name not in COLLECTIONS_TO_MIGRATE:
        print(f"Collection '{collection_name}' is not in the migration list.")
        print(f"Available collections: {', '.join(COLLECTIONS_TO_MIGRATE)}")
        return

    print(f"Migrating single collection: {collection_name}")

    prod_client = None
    dev_client = None

    try:
        prod_client = get_prod_client()
        dev_client = get_dev_client()

        prod_db = prod_client[DATABASE_NAME]
        dev_db = dev_client[DATABASE_NAME]

        count = migrate_collection(prod_db, dev_db, collection_name, clear_before_insert)
        print(f"\nMigration complete: {count} documents")

    finally:
        if prod_client:
            prod_client.close()
        if dev_client:
            dev_client.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MongoDB Data Migration Tool")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview document counts without migrating"
    )
    parser.add_argument(
        "--collection",
        type=str,
        help="Migrate a single collection"
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear dev collection before inserting (append mode)"
    )

    args = parser.parse_args()

    if args.preview:
        preview_counts()
    elif args.collection:
        migrate_single_collection(args.collection, clear_before_insert=not args.no_clear)
    else:
        # Confirm before running full migration
        print("\n" + "!" * 60)
        print("WARNING: This will overwrite data in the development database!")
        print("!" * 60)
        confirm = input("\nType 'yes' to continue: ")

        if confirm.lower() == "yes":
            migrate_all(clear_before_insert=not args.no_clear)
        else:
            print("Migration cancelled.")

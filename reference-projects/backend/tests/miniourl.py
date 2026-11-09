from datetime import timedelta

from app.db.my_minio import buckets, minio_client

# 生成预签名URL
expiry = timedelta(seconds=10)  # 设置URL有效期为10分钟
bucket_name = buckets.materials

try:
    url = minio_client.presigned_get_object(
        bucket_name, "009e6bca-6dfd-4ab0-a674-b8d6490bcc41.mp4", expires=expiry
    )
    print("预签名URL:", url)
except Exception as err:
    print("生成预签名URL时出错:", err)

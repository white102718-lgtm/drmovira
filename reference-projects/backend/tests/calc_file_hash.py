import io
from datetime import timezone, timedelta

from bson import CodecOptions

from app.utils.file_util import calculate_hash, calculate_sha3_256


def t():
    file_path = r"D:\素材\素材库\IDX777\Pdfcfde79.png"

    # 以二进制模式读取文件并存入 BytesIO
    with open(file_path, "rb") as f:
        img_bytes = io.BytesIO(f.read())
    print(calculate_hash(img_bytes.read()))
    print(calculate_sha3_256(img_bytes.read()))


def main():
    from app.conf import MongodbConf, MinioConf
    from pymongo import MongoClient

    client = MongoClient(MongodbConf.CONNECTION)
    from minio import Minio

    minio_client = Minio(
        MinioConf.ENDPOINT,
        access_key=MinioConf.ACCESS_KEY,  # 访问密钥
        secret_key=MinioConf.SECRET_KEY,  # 秘密密钥
        secure=MinioConf.SECURE,  # 如果使用 HTTPS，请设置为 True
    )
    tz_cst = timezone(timedelta(hours=8))
    codec_options = CodecOptions(tz_aware=True, tzinfo=tz_cst)
    mongo_client = client.get_database("plat", codec_options=codec_options)
    collection = mongo_client["materials"]
    cursor = collection.find({"sha3_256": {"$exists": False}})
    for doc in cursor:
        file_object = minio_client.get_object(
            "materials",
            doc["filename"],
        )
        sha3_256 = calculate_sha3_256(file_object.read())
        collection.update_one(
            {"filename": doc["filename"]}, {"$set": {"sha3_256": sha3_256}}
        )
        print(doc)


if __name__ == "__main__":
    t()
    pass

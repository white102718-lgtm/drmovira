from minio import Minio

from app.conf import MinioConf

minio_client = Minio(
    MinioConf.ENDPOINT,
    access_key=MinioConf.ACCESS_KEY,
    secret_key=MinioConf.SECRET_KEY,
    secure=MinioConf.SECURE,
)


class Buckets:
    # 素材
    materials = "materials"
    tmp = "tmp"
    # 创意生成
    creative_origin = "creative-origin"
    creative_origin_img = "creative-origin-img"
    creative_generated = "creative-generated"
    creative_generated_img = "creative-generated-img"
    # 内容
    content = "content"
    # 公共素材（素材师/投放师共享模版库）
    material_commons = "material-commons"


buckets = Buckets()


def minio_init():
    all_buckets = [v for k, v in vars(Buckets).items() if not k.startswith("_")]
    existing_buckets = set(bucket.name for bucket in minio_client.list_buckets())

    for bucket_name in all_buckets:
        if bucket_name not in existing_buckets:
            minio_client.make_bucket(bucket_name)
            print(f"创建bucket: {bucket_name}")


if __name__ == "__main__":
    minio_init()

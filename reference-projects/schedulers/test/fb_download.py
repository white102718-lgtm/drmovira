"""
Facebook 广告素材下载示例（内存版本，使用生成器防止内存溢出）

使用 fb_utils.download_ad_creatives_to_memory() 函数根据 ad_id 下载广告创意素材到内存
"""
from utils.fb_utils import download_ad_creatives_to_memory

# 示例1：边下载边处理（推荐，节省内存）
def example_streaming():
    """流式处理：边下载边处理，不占用大量内存"""
    # Facebook 开发者信息
    dev = {
        "app_id": '25250843384550371',
        "app_secret": 'REDACTED_REFERENCE_SECRET',
        "access_token": 'REDACTED_REFERENCE_SECRET',
        "proxy": "3.0.92.186",  # 可选
    }

    # 要下载的广告列表（字符串列表）
    ad_ids = [
        '120237194752170050',
    ]

    print("🚀 开始下载广告素材（流式处理）...\n")

    # 使用生成器，边下载边处理
    success_count = 0
    failed_count = 0

    for ad_id, content in download_ad_creatives_to_memory(ad_ids, dev):
        if content:
            print(f"✅ {ad_id}: 下载成功，大小 {len(content)} bytes")

            # 在这里可以立即处理文件内容
            # 例如：保存到数据库、上传到云存储、计算哈希等
            # 处理完后 content 会被垃圾回收，释放内存

            success_count += 1
        else:
            print(f"❌ {ad_id}: 下载失败")
            failed_count += 1

    print(f"\n📊 统计：成功 {success_count} 个，失败 {failed_count} 个")


# 示例2：收集到字典（如果需要全部数据在内存中）
def example_collect_all():
    """收集所有结果到字典（需要足够内存）"""
    dev = {
        "app_id": "1289103879583010",
        "app_secret": "REDACTED_REFERENCE_SECRET",
        "access_token": "REDACTED_REFERENCE_SECRET",
        "proxy": "3.0.92.186",
    }

    ad_ids = ["120239479977390492"]

    print("🚀 开始下载广告素材（收集全部）...\n")

    # 直接收集所有结果到字典
    results = dict(download_ad_creatives_to_memory(ad_ids, dev))

    print(f"\n📊 下载完成，共 {len(results)} 个广告")

    for ad_id, content in results.items():
        if content:
            print(f"✅ {ad_id}: {len(content)} bytes")
        else:
            print(f"❌ {ad_id}: 下载失败")


if __name__ == "__main__":
    from utils.common import set_local_proxy

    set_local_proxy()
    # 运行流式处理示例（推荐）
    example_streaming()

    # 如果需要收集全部结果，取消下面的注释
    # example_collect_all()

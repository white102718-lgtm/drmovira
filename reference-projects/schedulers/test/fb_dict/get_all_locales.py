"""
获取 Facebook 广告所有支持的语言编码
"""
import sys
import os
import json
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.targetingsearch import TargetingSearch

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.common import set_local_proxy

# 开发配置
DEV_CONFIG = {
    "app_id": "1156297120038785",
    "app_secret": "REDACTED_REFERENCE_SECRET",
    "access_token": "REDACTED_REFERENCE_SECRET",
}


def get_all_locales():
    """获取所有支持的语言编码"""
    set_local_proxy()

    FacebookAdsApi.init(
        DEV_CONFIG["app_id"],
        DEV_CONFIG["app_secret"],
        DEV_CONFIG["access_token"]
    )

    print("正在查询所有语言编码...")

    params = {
        'type': 'adlocale',
        'limit': 2000  # 获取尽可能多的结果
    }

    locales = TargetingSearch.search(params=params)

    result = []
    locale_dict = {}

    for locale in locales:
        key = int(locale['key'])
        name = locale['name']
        result.append({
            'key': key,
            'name': name
        })
        locale_dict[key] = name

    # 按编码排序
    result.sort(key=lambda x: x['key'])

    # 保存到 JSON 文件
    output_file = os.path.join(os.path.dirname(__file__), 'facebook_locales.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 共找到 {len(result)} 种语言")
    print(f"✅ 已保存到: {output_file}\n")

    # 打印前50个常用语言
    print("=" * 80)
    print("常用语言列表（前50个）:")
    print("=" * 80)
    print(f"{'编码':<6} | {'语言名称'}")
    print("-" * 80)

    for i, locale in enumerate(result[:50]):
        print(f"{locale['key']:<6} | {locale['name']}")

    if len(result) > 50:
        print(f"\n... 还有 {len(result) - 50} 种语言，完整列表请查看 {output_file}")

    return result


def search_locale(keyword):
    """搜索特定语言"""
    set_local_proxy()

    FacebookAdsApi.init(
        DEV_CONFIG["app_id"],
        DEV_CONFIG["app_secret"],
        DEV_CONFIG["access_token"]
    )

    print(f"\n搜索关键词: '{keyword}'")
    print("=" * 80)

    params = {
        'type': 'adlocale',
        'q': keyword
    }

    locales = TargetingSearch.search(params=params)

    if not locales:
        print("未找到匹配的语言")
        return []

    result = []
    print(f"{'编码':<6} | {'语言名称'}")
    print("-" * 80)

    for locale in locales:
        key = int(locale['key'])
        name = locale['name']
        result.append({'key': key, 'name': name})
        print(f"{key:<6} | {name}")

    print(f"\n✅ 共找到 {len(result)} 个匹配结果")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='获取 Facebook 广告语言编码')
    parser.add_argument('-s', '--search', type=str, help='搜索特定语言，如: chinese, spanish, english')
    parser.add_argument('-a', '--all', action='store_true', help='获取所有语言编码')

    args = parser.parse_args()

    if args.search:
        # 搜索特定语言
        search_locale(args.search)
    elif args.all:
        # 获取所有语言
        get_all_locales()
    else:
        # 默认：获取所有语言
        get_all_locales()

        # 显示常用搜索示例
        print("\n" + "=" * 80)
        print("💡 使用提示:")
        print("=" * 80)
        print("1. 获取所有语言: python get_all_locales.py --all")
        print("2. 搜索中文:     python get_all_locales.py --search chinese")
        print("3. 搜索西班牙语: python get_all_locales.py --search spanish")
        print("4. 搜索英语:     python get_all_locales.py --search english")
        print("=" * 80)

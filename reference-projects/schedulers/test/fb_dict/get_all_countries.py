"""
获取 Facebook 广告所有支持的国家/地区编码
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


def get_all_countries():
    """获取所有支持的国家/地区编码"""
    set_local_proxy()

    FacebookAdsApi.init(
        DEV_CONFIG["app_id"],
        DEV_CONFIG["app_secret"],
        DEV_CONFIG["access_token"]
    )

    print("正在查询所有国家/地区编码...")

    params = {
        'type': 'adgeolocation',
        'location_types': ['country'],
        'limit': 5000  # 获取尽可能多的结果
    }

    countries = TargetingSearch.search(params=params)

    result = []
    country_dict = {}

    for country in countries:
        # country 返回格式: {'key': 'US', 'name': 'United States', 'type': 'country', 'country_code': 'US'}
        country_code = country.get('country_code') or country.get('key')
        name = country.get('name', '')

        result.append({
            'code': country_code,
            'name': name,
            'type': country.get('type', 'country')
        })
        country_dict[country_code] = name

    # 按国家代码排序
    result.sort(key=lambda x: x['code'])

    # 保存到 JSON 文件
    output_file = os.path.join(os.path.dirname(__file__), 'facebook_countries.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 共找到 {len(result)} 个国家/地区")
    print(f"✅ 已保存到: {output_file}\n")

    # 打印前50个常用国家
    print("=" * 80)
    print("常用国家/地区列表（前50个）:")
    print("=" * 80)
    print(f"{'国家代码':<10} | {'国家名称'}")
    print("-" * 80)

    for i, country in enumerate(result[:50]):
        print(f"{country['code']:<10} | {country['name']}")

    if len(result) > 50:
        print(f"\n... 还有 {len(result) - 50} 个国家/地区，完整列表请查看 {output_file}")

    # 打印常用国家代码
    print("\n" + "=" * 80)
    print("💡 常用国家代码快速参考:")
    print("=" * 80)
    common_countries = ['US', 'CN', 'JP', 'GB', 'CA', 'AU', 'DE', 'FR', 'KR', 'IN', 'BR', 'MX', 'ES', 'IT', 'RU']
    for code in common_countries:
        if code in country_dict:
            print(f"{code:<4} - {country_dict[code]}")

    return result


def search_country(keyword):
    """搜索特定国家/地区"""
    set_local_proxy()

    FacebookAdsApi.init(
        DEV_CONFIG["app_id"],
        DEV_CONFIG["app_secret"],
        DEV_CONFIG["access_token"]
    )

    print(f"\n搜索关键词: '{keyword}'")
    print("=" * 80)

    params = {
        'type': 'adgeolocation',
        'location_types': ['country'],
        'q': keyword
    }

    countries = TargetingSearch.search(params=params)

    if not countries:
        print("未找到匹配的国家/地区")
        return []

    result = []
    print(f"{'国家代码':<10} | {'国家名称'}")
    print("-" * 80)

    for country in countries:
        country_code = country.get('country_code') or country.get('key')
        name = country.get('name', '')
        result.append({'code': country_code, 'name': name})
        print(f"{country_code:<10} | {name}")

    print(f"\n✅ 共找到 {len(result)} 个匹配结果")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='获取 Facebook 广告国家/地区编码')
    parser.add_argument('-s', '--search', type=str, help='搜索特定国家/地区，如: china, united states, japan')
    parser.add_argument('-a', '--all', action='store_true', help='获取所有国家/地区编码')

    args = parser.parse_args()

    if args.search:
        # 搜索特定国家
        search_country(args.search)
    elif args.all:
        # 获取所有国家
        get_all_countries()
    else:
        # 默认：获取所有国家
        get_all_countries()

        # 显示常用搜索示例
        print("\n" + "=" * 80)
        print("💡 使用提示:")
        print("=" * 80)
        print("1. 获取所有国家: python get_all_countries.py --all")
        print("2. 搜索中国:     python get_all_countries.py --search china")
        print("3. 搜索美国:     python get_all_countries.py --search united")
        print("4. 搜索日本:     python get_all_countries.py --search japan")
        print("=" * 80)

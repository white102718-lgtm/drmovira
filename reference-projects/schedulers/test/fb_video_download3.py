import json
import time
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.advideo import AdVideo
from facebook_business.exceptions import FacebookRequestError

from utils.common import set_local_proxy

# ===================== 配置信息 =====================
account = {
    "app_id": "1156297120038785",
    "app_secret": "REDACTED_REFERENCE_SECRET",
    "access_token": "REDACTED_REFERENCE_SECRET",
    "proxy": "13.250.117.58",
}
ad_ids = [{"ad_id": "120243734204000399", "ad_name": "xxxx"}]

# set_local_proxy()

# 初始化 SDK
FacebookAdsApi.init(
    app_id=account["app_id"],
    app_secret=account["app_secret"],
    access_token=account["access_token"],
    api_version="v20.0",
)

# ===================== 获取 video_id =====================
def get_video_id_from_ad(ad_id):
    try:
        # Clean ad_id if it has extra quotes
        clean_ad_id = ad_id.strip("'")
        
        ad = Ad(clean_ad_id)
        ad_data = ad.api_get(fields=['creative'])
        
        if 'creative' not in ad_data:
            print(f"[⚠️] Ad {ad_id} has no creative")
            return None
            
        creative_id = ad_data['creative']['id']

        creative = AdCreative(creative_id)
        # Fetch object_story_spec to find video data
        creative_data = creative.api_get(fields=['object_story_spec', 'thumbnail_url'])
        
        # Method 1: Check object_story_spec -> video_data
        video_id = creative_data.get('object_story_spec', {}).get('video_data', {}).get('video_id')
        
        if not video_id:
             print(f"[⚠️] No video_id found in creative {creative_id}")
             
        return video_id
    except FacebookRequestError as e:
        print(f"[❌] Facebook请求错误: {e.api_error_message()}")
        return None
    except Exception as e:
        print(f"[❌] 获取广告 {ad_id} video_id 出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

# ===================== 获取最高质量视频 URL (使用 AdVideo) =====================
def get_best_video_source(video_id, retries=3):
    if not video_id:
        return None

    for attempt in range(retries):
        try:
            video = AdVideo(video_id)
            # Use SDK to get fields
            data = video.api_get(fields=['source', 'format'])
            
            # Data is already a dict-like object (AbstractObject)
            formats = data.get("format", [])
            
            # Filter formats that have a valid 'url'
            valid_formats = [f for f in formats if f.get("url")]

            # 选择最高质量视频：先比宽度，再比码率
            if valid_formats:
                best = max(
                    valid_formats, key=lambda f: (f.get("width", 0), f.get("bitrate", 0))
                )
                return best.get("url")
            
            # fallback to source if no format found
            if "source" in data:
                 return data["source"]
            
            print(f"[⚠️] No video URL found in formats or source. Formats: {len(formats)}")
            return None

        except FacebookRequestError as e:
            print(f"[❌] Facebook API Error: {e.api_error_message()}")
            return None
        except Exception as e:
            print(f"[⚠️] 获取视频 info 失败 ({attempt+1}/{retries}): {e}")
            time.sleep(3)

    print(f"[❌] 视频 {video_id} 多次请求失败")
    return None

# ===================== 主程序 =====================
def main():
    results = []

    for ad in ad_ids:
        ad_id = ad['ad_id']
        ad_name = ad['ad_name']
        print(f"\n➡️ 处理广告: {ad_name} ({ad_id})")

        video_id = get_video_id_from_ad(ad_id)
        if not video_id:
            print("[⚠️] 广告没有视频或获取 video_id 失败")
            continue
        print(f"🎬 视频 ID: {video_id}")

        best_video_url = get_best_video_source(video_id)
        if best_video_url:
            print(f"✅ 最高清晰度视频 URL: {best_video_url}")
            results.append({
                "ad_id": ad_id,
                "ad_name": ad_name,
                "video_id": video_id,
                "video_url": best_video_url
            })
        else:
            print("[❌] 无法获取视频原文件 URL")

    if results:
        output_file = "fb_ad_videos_3.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已保存结果到 {output_file}")
    else:
        print("\n⚠️ 没有获取到任何视频信息")

if __name__ == "__main__":
    main()

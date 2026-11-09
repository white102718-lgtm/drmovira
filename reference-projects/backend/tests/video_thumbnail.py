import tempfile

import cv2

from app.utils.file_util import extract_first_frame_from_memory

# 示例使用
if __name__ == "__main__":
    # with open(r"C:\Users\Mayn\Desktop\ampV2f8f25a6.mp4", "rb") as f:
    with open(r"C:\Users\Mayn\Desktop\imgP30049b07.jpg", "rb") as f:
        video_bytes = f.read()
    thumbnail = extract_first_frame_from_memory(video_bytes, scale_factor=0.1)
    cv2.imwrite("thumbnail.jpg", thumbnail)
    print("缩略图已保存为 'thumbnail.jpg'")

#!/usr/bin/env python3
import os
import subprocess
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2


# ---------- 1. FFmpeg 检测 ----------
def find_ffmpeg():
    """跨平台检测FFmpeg路径"""
    # 常见FFmpeg路径
    possible_paths = [
        "ffmpeg",  # 系统PATH中
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"D:\soft\ffmpeg-master-latest-win64-gpl-shared\bin\ffmpeg.exe",
    ]

    for path in possible_paths:
        try:
            result = subprocess.run(
                [path, "-version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return path
        except (
            subprocess.TimeoutExpired,
            FileNotFoundError,
            subprocess.SubprocessError,
        ):
            continue
    return None


# ---------- 2. GUI 选择区域 ----------
class ROISelector:
    def __init__(self, img_bgr):
        self.img = img_bgr.copy()
        self.clone = img_bgr.copy()
        self.x0, self.y0, self.x1, self.y1 = -1, -1, -1, -1
        self.drawing = False
        self.confirmed = False
        self.scale_factor = 1.0
        self.display_img = None
        self.display_clone = None

    def _mouse_cb_scaled(self, event, x, y, flags, param):
        """处理缩放后的鼠标事件"""
        # 将显示坐标转换为原始图像坐标
        orig_x = int(x * self.scale_factor)
        orig_y = int(y * self.scale_factor)

        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.x0, self.y0 = orig_x, orig_y
            self.x1, self.y1 = orig_x, orig_y
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            self.x1, self.y1 = orig_x, orig_y
            # 在显示图像上绘制
            vis = self.display_clone.copy()
            display_x0 = int(self.x0 / self.scale_factor)
            display_y0 = int(self.y0 / self.scale_factor)
            display_x1 = int(self.x1 / self.scale_factor)
            display_y1 = int(self.y1 / self.scale_factor)
            cv2.rectangle(
                vis, (display_x0, display_y0), (display_x1, display_y1), (0, 255, 0), 2
            )
            # 显示原始坐标信息
            info = f"({self.x0},{self.y0}) -> ({self.x1},{self.y1}) Size: {abs(self.x1-self.x0)}x{abs(self.y1-self.y0)}"
            cv2.putText(
                vis, info, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1
            )
            cv2.imshow("选择水印区域, 按enter确认, 按esc退出", vis)
        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            # 更新固定框显示
            display_x0 = int(self.x0 / self.scale_factor)
            display_y0 = int(self.y0 / self.scale_factor)
            display_x1 = int(self.x1 / self.scale_factor)
            display_y1 = int(self.y1 / self.scale_factor)
            cv2.rectangle(
                self.display_clone,
                (display_x0, display_y0),
                (display_x1, display_y1),
                (0, 255, 0),
                2,
            )
            info = f"Selected: {abs(self.x1-self.x0)}x{abs(self.y1-self.y0)} at ({min(self.x0,self.x1)},{min(self.y0,self.y1)})"
            cv2.putText(
                self.display_clone,
                info,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
            )
            cv2.imshow("选择水印区域, 按enter确认, 按esc退出", self.display_clone)

    def _mouse_cb(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.x0, self.y0 = x, y
            self.x1, self.y1 = x, y
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            self.x1, self.y1 = x, y
            vis = self.clone.copy()
            # 绘制选择框
            cv2.rectangle(vis, (self.x0, self.y0), (self.x1, self.y1), (0, 255, 0), 2)
            # 显示坐标信息
            info = f"({self.x0},{self.y0}) -> ({self.x1},{self.y1}) Size: {abs(self.x1-self.x0)}x{abs(self.y1-self.y0)}"
            cv2.putText(
                vis, info, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
            )
        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            # 更新固定框显示
            cv2.rectangle(
                self.clone, (self.x0, self.y0), (self.x1, self.y1), (0, 255, 0), 2
            )
            info = f"Selected: {abs(self.x1-self.x0)}x{abs(self.y1-self.y0)} at ({min(self.x0,self.x1)},{min(self.y0,self.y1)})"
            cv2.putText(
                self.clone,
                info,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

    def select(self):
        window_name = "选择水印区域, 按enter确认, 按esc退出"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        # 计算合适的显示尺寸，保持纵横比
        img_h, img_w = self.img.shape[:2]
        max_width, max_height = 1200, 800

        # 计算缩放比例
        scale_w = max_width / img_w
        scale_h = max_height / img_h
        scale = min(scale_w, scale_h, 1.0)  # 不放大，只缩小

        # 如果需要缩放
        if scale < 1.0:
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)
            display_img = cv2.resize(self.img, (new_w, new_h))
            display_clone = cv2.resize(self.clone, (new_w, new_h))
            self.scale_factor = 1.0 / scale  # 记录缩放因子用于坐标转换
        else:
            display_img = self.img.copy()
            display_clone = self.clone.copy()
            new_w, new_h = img_w, img_h
            self.scale_factor = 1.0

        # 更新显示图像
        self.display_img = display_img
        self.display_clone = display_clone

        cv2.resizeWindow(window_name, new_w, new_h)
        cv2.setMouseCallback(window_name, self._mouse_cb_scaled)

        # 添加使用说明
        help_img = display_img.copy()
        cv2.imshow(window_name, help_img)
        while True:
            # 确保窗口处于焦点状态
            cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)
            cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 0)

            k = cv2.waitKey(30) & 0xFF

            # 检查窗口是否被关闭
            try:
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except:
                break

            if k == 13 or k == ord("\r"):  # Enter键
                self.confirmed = True
                break
            elif k == 27:  # Esc键
                break
            elif k == ord("q") or k == ord("Q"):  # 添加Q键退出
                break
            elif k != 255:  # 如果按了其他键，显示键值用于调试
                print(
                    f"按下了键: {k} (字符: {chr(k) if 32 <= k <= 126 else '不可显示'})"
                )

        cv2.destroyAllWindows()
        cv2.waitKey(1)

        if not self.confirmed or self.x0 < 0 or self.y0 < 0:
            print("未确认选择或未选择区域")
            return None

        # 确保坐标正确
        x0, x1 = sorted([self.x0, self.x1])
        y0, y1 = sorted([self.y0, self.y1])
        w, h = x1 - x0, y1 - y0

        print(f"选择的区域: x={x0}, y={y0}, w={w}, h={h}")

        # 检查选择区域大小
        if w < 10 or h < 10:
            messagebox.showwarning("警告", "选择区域太小，请重新选择！")
            return None

        return x0, y0, w, h


# ---------- 3. 进度窗口 ----------
class ProgressWindow:
    def __init__(self, parent=None):
        self.root = tk.Tk() if parent is None else tk.Toplevel(parent)
        self.root.title("水印处理进度")
        self.root.geometry("400x180")
        self.root.resizable(False, False)

        # 居中显示
        self.root.transient(parent)
        if parent:
            self.root.grab_set()

        # 进度标签
        self.status_label = tk.Label(self.root, text="正在处理...", font=("Arial", 12))
        self.status_label.pack(pady=15)

        # 详细信息标签
        self.detail_label = tk.Label(
            self.root, text="初始化...", font=("Arial", 10), fg="gray"
        )
        self.detail_label.pack(pady=5)

        # 进度条
        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(pady=10, padx=20, fill="x")
        self.progress.start(20)

        # 取消按钮
        self.cancel_button = tk.Button(
            self.root, text="取消", command=self.cancel, bg="lightcoral", fg="white"
        )
        self.cancel_button.pack(pady=10)

        self.cancelled = False

        # 强制显示窗口
        self.root.lift()
        self.root.focus_force()
        self.root.update()

    def update_status(self, status, detail=""):
        try:
            self.status_label.config(text=status)
            if detail:
                self.detail_label.config(text=detail)
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            pass  # 窗口可能已被关闭

    def cancel(self):
        self.cancelled = True
        print("用户点击取消按钮")

    def close(self):
        try:
            self.progress.stop()
            self.root.destroy()
        except tk.TclError:
            pass  # 窗口可能已被关闭


# ---------- 4. 主流程 ----------
def pick_video_and_delogo():
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    # 检查FFmpeg
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        messagebox.showerror(
            "错误",
            "未找到FFmpeg！\n请确保FFmpeg已安装并在系统PATH中，\n或将其放在以下路径之一：\n"
            "• C:\\ffmpeg\\bin\\ffmpeg.exe\n"
            "• /usr/bin/ffmpeg\n"
            "• /usr/local/bin/ffmpeg",
        )
        return

    # 选择视频文件
    video_path = filedialog.askopenfilename(
        title="选择视频文件",
        filetypes=[
            ("视频文件", "*.mp4;*.avi;*.mov;*.mkv;*.wmv;*.flv;*.webm"),
            ("MP4文件", "*.mp4"),
            ("AVI文件", "*.avi"),
            ("MOV文件", "*.mov"),
            ("MKV文件", "*.mkv"),
            ("所有文件", "*.*"),
        ],
    )
    if not video_path:
        return

    try:
        # 读首帧
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError("无法打开视频文件")

        ret, first_frame = cap.read()
        cap.release()

        if not ret or first_frame is None:
            raise ValueError("无法读取视频首帧")

        # 检查视频分辨率
        height, width = first_frame.shape[:2]
        if width < 100 or height < 100:
            raise ValueError(f"视频分辨率过小：{width}x{height}")

        print(f"视频首帧尺寸: {width}x{height}")

    except Exception as e:
        messagebox.showerror("错误", f"读取视频失败：{str(e)}")
        return

    # 选择水印区域
    print("开始选择水印区域...")
    roi = ROISelector(first_frame).select()
    if roi is None:
        messagebox.showinfo("提示", "未选择区域或已取消")
        return

    x, y, w, h = roi

    # 确认处理
    if not messagebox.askyesno(
        "确认",
        f"将要处理的水印区域：\n"
        f"位置：({x}, {y})\n"
        f"大小：{w} x {h}\n"
        f"是否继续处理？",
    ):
        return

    # 生成输出文件名
    video_path_obj = Path(video_path)
    output_path = str(
        video_path_obj.parent / f"{video_path_obj.stem}_no_logo{video_path_obj.suffix}"
    )

    # 显示进度窗口
    progress_window = ProgressWindow(root)
    progress_window.update_status("正在移除水印...", "准备FFmpeg命令")

    # 构建高质量FFmpeg命令
    cmd = [
        ffmpeg_path,  # FFmpeg可执行文件路径
        "-y",  # 覆盖输出文件（不询问）
        "-i",  # 输入文件标志
        video_path,  # 输入视频文件路径
        "-vf",  # 视频滤镜标志
        f"delogo=x={x}:y={y}:w={w}:h={h}:show=0",  # 去水印滤镜
        "-c:a",  # 音频编码器设置
        "copy",  # 直接复制音频流（不重新编码）
        output_path,  # 输出文件路径
    ]

    def run_ffmpeg():
        try:
            print(f"执行FFmpeg命令: {' '.join(cmd)}")

            # 直接运行，不使用管道避免阻塞
            process = subprocess.Popen(cmd)

            # 监控进程
            while process.poll() is None:
                if progress_window.cancelled:
                    print("用户取消，终止FFmpeg进程")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return False, "用户取消"
                time.sleep(0.5)
                progress_window.update_status(
                    "正在处理视频...", f"FFmpeg进程运行中 PID: {process.pid}"
                )

            print(f"FFmpeg进程结束，返回码: {process.returncode}")

            if process.returncode == 0:
                if os.path.exists(output_path):
                    print(f"输出文件创建成功: {output_path}")
                    return True, output_path
                else:
                    return False, "FFmpeg执行成功但未找到输出文件"
            else:
                # 重新运行获取错误信息
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=60
                    )
                    return (
                        False,
                        f"FFmpeg错误 (返回码{result.returncode}):\n{result.stderr}",
                    )
                except subprocess.TimeoutExpired:
                    return False, "FFmpeg处理超时"

        except Exception as e:
            print(f"运行FFmpeg时发生异常: {e}")
            return False, f"处理失败：{str(e)}"

    # 运行FFmpeg (简化，不使用线程)
    print("开始处理视频...")
    result_success, result_message = run_ffmpeg()

    progress_window.close()

    if result_success:
        file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB

        # 询问是否打开目录
        if messagebox.askyesno(
            "处理完成",
            f"水印移除完成！\n"
            f"输出文件：{output_path}\n"
            f"文件大小：{file_size:.1f} MB\n\n"
            f"是否打开文件所在目录？",
        ):
            try:
                if os.name == "nt":  # Windows
                    os.startfile(os.path.dirname(output_path))
                elif os.name == "posix":  # Linux/Mac
                    subprocess.run(["xdg-open", os.path.dirname(output_path)])
            except Exception as e:
                messagebox.showerror("错误", f"无法打开目录：{str(e)}")
    else:
        messagebox.showerror("错误", result_message)


if __name__ == "__main__":
    pick_video_and_delogo()

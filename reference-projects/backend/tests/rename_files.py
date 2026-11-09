import hashlib
import random
import string
from pathlib import Path
from tkinter import Tk
from tkinter.filedialog import askdirectory

# 定义文件类型对应的首字母
FILE_PREFIX = {
    "images": "P",
    "videos": "V",
}

# 支持的文件类型
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".wmv", ".mkv", ".flv"}


def calculate_hash(file_path: Path) -> str:
    """计算文件内容的完整 MD5 哈希值

    Args:
        file_path: 文件路径

    Returns:
        完整的MD5哈希值（32位十六进制字符串）
    """
    # Python 3.11+ 使用 file_digest，直接使用 open() 返回的文件对象
    with open(file_path, "rb") as f:
        return hashlib.file_digest(f, "md5").hexdigest()


def get_file_prefix(file_extension: str) -> str | None:
    """根据文件扩展名返回前缀"""
    if file_extension in IMAGE_EXTENSIONS:
        return FILE_PREFIX["images"]
    elif file_extension in VIDEO_EXTENSIONS:
        return FILE_PREFIX["videos"]
    return None


def generate_random_suffix(length: int = 4) -> str:
    """生成随机数字字符串作为后缀"""
    return "".join(random.choices(string.digits, k=length))


def count_all_files(directory: Path) -> int:
    """统计目录及其所有子目录中的文件总数"""
    return sum(1 for item in directory.rglob("*") if item.is_file())


def should_skip_file(file_path: Path) -> bool:
    """判断文件是否应该跳过（已经符合命名规则）"""
    basename = file_path.stem
    # 检查是否以 P 或 V 开头且基础名称长度为 9
    if file_path.name[0] in ["P", "V"] and len(basename) == 9:
        return True
    return False


def rename_files_in_directory(directory: Path, simple_check: bool) -> None:
    """重命名指定目录下的文件

    Args:
        directory: 要处理的目录
        simple_check: True=简单检查(跳过已符合规则的文件), False=全面检查(检查所有文件)
    """
    hash_registry = {}  # 用于记录哈希值及对应文件路径

    # 统计总文件数
    total_files = count_all_files(directory)
    print(f"目录及子目录中共有 {total_files} 个文件")

    if simple_check:
        print("模式: 简单检查 - 仅检查不符合命名规则(以P或V开头,并且总长度=9)的文件")
    else:
        print("模式: 全面检查 - 检查所有文件")

    # 递归遍历所有文件
    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue

        # 简单检查模式下跳过已符合规则的文件
        if simple_check and should_skip_file(file_path):
            continue

        file_extension = file_path.suffix.lower()
        if (
            file_extension not in IMAGE_EXTENSIONS
            and file_extension not in VIDEO_EXTENSIONS
        ):
            continue

        # 检查文件类型是否支持
        prefix = get_file_prefix(file_extension)
        if prefix is None:
            print(f"跳过文件: {file_path.name}")
            continue

        # 计算文件哈希
        file_hash = calculate_hash(file_path)
        hash_prefix = file_hash[:8]  # 取前8位哈希值
        new_file_name = f"{prefix}{hash_prefix}{file_extension}"
        new_file_path = file_path.parent / new_file_name

        # 检查哈希值冲突
        if hash_prefix in hash_registry:
            existing_file = hash_registry[hash_prefix]
            if existing_file.exists() and calculate_hash(existing_file) == file_hash:
                print(f"重复文件!: [{file_path}] 和 [{existing_file}]")
            else:
                # 哈希前8位相同但内容不同，添加随机后缀
                random_suffix = generate_random_suffix()
                unique_file_name = (
                    f"{prefix}{hash_prefix}_{random_suffix}{file_extension}"
                )
                unique_file_path = file_path.parent / unique_file_name
                file_path.rename(unique_file_path)
                print(f"重复前缀重命名文件: {file_path.name} -> {unique_file_name}")
                # 更新 hash_registry 中的路径
                hash_registry[hash_prefix] = unique_file_path
        else:
            # 没有冲突，正常记录并重命名
            hash_registry[hash_prefix] = file_path
            if file_path != new_file_path:
                if new_file_path.exists():
                    print(f"已经存在该文件!{file_path} -> {new_file_path}")
                    continue
                file_path.rename(new_file_path)
                print(f"重命名: {file_path.name} -> {new_file_name}")


if __name__ == "__main__":
    # 创建一个Tkinter根窗口，并立即隐藏它
    root = Tk()
    root.withdraw()  # 隐藏主窗口

    # 弹出文件夹选择对话框
    directory_str = askdirectory(title="请选择要递归重命名的文件夹")

    if not directory_str:  # 如果用户没有选择任何目录或取消了选择
        print("没有选择文件夹!")
    else:
        directory = Path(directory_str)
        print(f"重命名文件及子文件: {directory}")

        # 询问用户是否进行简单检查
        user_input = (
            input(
                "是否进行全面检查？\n"
                "直接按 Enter=全面检查\n"
                "按 n 然后 Enter=简单检查(只检查以P或V开头,并且总长度=9的文件): "
            )
            .strip()
            .lower()
        )
        simple_check = user_input.lower() == "n"

        rename_files_in_directory(directory, simple_check)
    print("程序执行完成！")
    input("请关闭该窗口或者按 Enter 键退出...")

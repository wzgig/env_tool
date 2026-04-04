import argparse
import shutil
import struct
import subprocess
import sys
from pathlib import Path

def run_cmd(cmd: list[str]) -> int:
    """
    执行传入的命令列表，并打印执行信息。
    返回子进程的退出码。
    """
    print(f"\n>>> {' '.join(cmd)}\n")
    result = subprocess.run(cmd, check=False)
    return result.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="打包 EnvTool 为 EXE")
    parser.add_argument(
        "--target",
        choices=["all", "console", "gui"],
        default="gui",
        help="打包目标：all=同时打包 console+gui，console=仅控制台版，gui=仅图形版",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="不清理 build/dist 目录",
    )
    return parser.parse_args()


def ensure_brand_icon(project_root: Path) -> Path:
    """生成内置 ICO 图标（16x16），用于 PyInstaller 的 EXE 品牌图标。"""
    icon_dir = project_root / "assets" / "icons"
    icon_dir.mkdir(parents=True, exist_ok=True)
    icon_path = icon_dir / "envtool.ico"

    # ICO 文件头
    width, height = 16, 16
    xor_size = width * height * 4
    and_size = height * 4  # 1bpp mask，按 32bit 对齐
    image_size = 40 + xor_size + and_size

    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, image_size, 22)

    # BITMAPINFOHEADER
    info = struct.pack(
        "<IIIHHIIIIII",
        40,
        width,
        height * 2,
        1,
        32,
        0,
        xor_size,
        0,
        0,
        0,
        0,
    )

    # 纯色蓝底 + 白色内方块（BGRA，底向上）
    blue = bytes([0xE3, 0x71, 0x00, 0xFF])
    white = bytes([0xFF, 0xFF, 0xFF, 0xFF])
    pixels = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            if 4 <= x <= 11 and 4 <= y <= 11:
                if 6 <= x <= 9 and 6 <= y <= 9:
                    pixels.extend(blue)
                else:
                    pixels.extend(white)
            else:
                pixels.extend(blue)

    and_mask = b"\x00" * and_size
    icon_path.write_bytes(header + entry + info + bytes(pixels) + and_mask)
    return icon_path


def build_console(project_root: Path, icon_path: Path) -> int:
    entry_file = project_root / "env_manager.py"
    if not entry_file.exists():
        print(f"未找到入口文件: {entry_file}")
        return 2

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        "EnvTool",
        "--icon",
        str(icon_path),
        "--specpath",
        str(project_root / "build" / "spec"),
        str(entry_file),
    ]
    return run_cmd(cmd)


def build_gui(project_root: Path, icon_path: Path) -> int:
    entry_file = project_root / "env_tool_gui.py"
    if not entry_file.exists():
        print(f"未找到入口文件: {entry_file}")
        return 2

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "EnvToolGUI",
        "--icon",
        str(icon_path),
        "--add-data",
        f"{project_root / 'env_manager.py'};.",
        "--specpath",
        str(project_root / "build" / "spec"),
        str(entry_file),
    ]
    return run_cmd(cmd)


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parent

    print("[1/4] 安装/升级 PyInstaller")
    code = run_cmd([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])
    if code != 0:
        print("安装 PyInstaller 失败。")
        return code

    print("[2/4] 处理构建目录")
    if not args.no_clean:
        for folder_name in ("build", "dist"):
            folder = project_root / folder_name
            if folder.exists():
                shutil.rmtree(folder, ignore_errors=True)
    else:
        print("已跳过清理目录。")

    icon_path = ensure_brand_icon(project_root)
    print(f"已准备图标资源: {icon_path}")

    print("[3/4] 开始打包")
    build_codes: list[int] = []
    if args.target in ("all", "console"):
        print("\n--- 打包控制台版 EnvTool.exe ---")
        build_codes.append(build_console(project_root, icon_path))

    if args.target in ("all", "gui"):
        print("\n--- 打包图形版 EnvToolGUI.exe ---")
        build_codes.append(build_gui(project_root, icon_path))

    if any(code != 0 for code in build_codes):
        print("\n至少一个目标打包失败。")
        return 1

    print("[4/4] 输出构建结果")
    console_exe = project_root / "dist" / "EnvTool.exe"
    gui_exe = project_root / "dist" / "EnvToolGUI.exe"

    if console_exe.exists():
        print(f"控制台版: {console_exe}")
    if gui_exe.exists():
        print(f"图形版: {gui_exe}")

    if not console_exe.exists() and not gui_exe.exists():
        print("打包流程结束，但未找到输出 EXE。")
        return 1

    print("\n打包完成。可直接分发 EXE（目标机器需安装 Python）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

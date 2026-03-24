import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str]) -> int:
    print(f"\n>>> {' '.join(cmd)}\n")
    result = subprocess.run(cmd, check=False)
    return result.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="打包 EnvTool 为 EXE")
    parser.add_argument(
        "--target",
        choices=["all", "console", "gui"],
        default="all",
        help="打包目标：all=同时打包 console+gui，console=仅控制台版，gui=仅图形版",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="不清理 build/dist 目录",
    )
    return parser.parse_args()


def build_console(project_root: Path) -> int:
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
        "--specpath",
        str(project_root / "build" / "spec"),
        str(entry_file),
    ]
    return run_cmd(cmd)


def build_gui(project_root: Path) -> int:
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

    print("[3/4] 开始打包")
    build_codes: list[int] = []
    if args.target in ("all", "console"):
        print("\n--- 打包控制台版 EnvTool.exe ---")
        build_codes.append(build_console(project_root))

    if args.target in ("all", "gui"):
        print("\n--- 打包图形版 EnvToolGUI.exe ---")
        build_codes.append(build_gui(project_root))

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

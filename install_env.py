import argparse
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from common import (
    current_python,
    print_header,
    resolve_group_names,
    save_json_report,
    unique_preserve_order,
)
from package_config import PACKAGE_GROUPS


PIP_BASE_CMD = [sys.executable, "-m", "pip"]
PIP_COMMON_FLAGS = [
    "--disable-pip-version-check",
    "--no-input",
]


@dataclass
class InstallResult:
    package: str
    ok: bool
    group: Optional[str] = None
    skipped: bool = False
    error: Optional[str] = None


@dataclass
class InstallSummary:
    success: List[InstallResult] = field(default_factory=list)
    failed: List[InstallResult] = field(default_factory=list)
    skipped: List[InstallResult] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "success": [asdict(x) for x in self.success],
            "failed": [asdict(x) for x in self.failed],
            "skipped": [asdict(x) for x in self.skipped],
            "success_count": len(self.success),
            "failed_count": len(self.failed),
            "skipped_count": len(self.skipped),
        }


def run_command(
    cmd: List[str],
    dry_run: bool = False,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    print(f"\n>>> 执行命令: {' '.join(cmd)}\n")

    if dry_run:
        print("[DRY-RUN] 仅预览，不实际执行。")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    try:
        return subprocess.run(
            cmd,
            check=False,
            text=True,
            capture_output=capture_output,
        )
    except KeyboardInterrupt:
        print("\n用户中断执行。")
        raise
    except Exception as e:
        stderr = f"{type(e).__name__}: {e}"
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr=stderr)


def upgrade_pip(dry_run: bool = False) -> bool:
    cmd = PIP_BASE_CMD + ["install", "--upgrade", "pip"] + PIP_COMMON_FLAGS
    result = run_command(cmd, dry_run=dry_run, capture_output=True)
    if result.returncode != 0 and result.stderr:
        print(result.stderr.strip())
    return result.returncode == 0


def is_package_installed(package_name: str) -> bool:
    cmd = PIP_BASE_CMD + ["show", package_name]
    result = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def install_packages(packages: List[str], dry_run: bool = False) -> subprocess.CompletedProcess:
    if not packages:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    cmd = PIP_BASE_CMD + ["install"] + packages + PIP_COMMON_FLAGS
    return run_command(cmd, dry_run=dry_run, capture_output=True)


def install_one_package(package_name: str, dry_run: bool = False) -> subprocess.CompletedProcess:
    return install_packages([package_name], dry_run=dry_run)


def install_group(
    group_name: str,
    packages: List[str],
    summary: InstallSummary,
    skip_installed: bool = False,
    dry_run: bool = False,
) -> None:
    print_header(f"开始安装分组: {group_name}")

    packages = unique_preserve_order(packages)
    to_install: List[str] = []

    for pkg in packages:
        if skip_installed and not dry_run and is_package_installed(pkg):
            print(f"已安装，跳过: {pkg}")
            summary.skipped.append(
                InstallResult(package=pkg, ok=True, group=group_name, skipped=True)
            )
        else:
            to_install.append(pkg)

    if not to_install:
        print(f"分组 {group_name} 无需安装。")
        return

    print(f"本组待安装包数量: {len(to_install)}")
    print("先尝试批量安装...")

    batch_result = install_packages(to_install, dry_run=dry_run)
    if batch_result.returncode == 0:
        print(f"分组 {group_name} 批量安装成功。")
        for pkg in to_install:
            summary.success.append(InstallResult(package=pkg, ok=True, group=group_name))
        return

    print(f"分组 {group_name} 批量安装失败，改为逐个安装。")
    if batch_result.stderr:
        print("批量安装错误摘要：")
        print(batch_result.stderr.strip()[:2000])

    for pkg in to_install:
        result = install_one_package(pkg, dry_run=dry_run)
        if result.returncode == 0:
            print(f"安装成功: {pkg}")
            summary.success.append(InstallResult(package=pkg, ok=True, group=group_name))
        else:
            error_text = (result.stderr or "").strip()[:1000] or "未知错误"
            print(f"安装失败: {pkg}")
            print(error_text)
            summary.failed.append(
                InstallResult(
                    package=pkg,
                    ok=False,
                    group=group_name,
                    error=error_text,
                )
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="一键安装常用 Python 环境依赖")
    parser.add_argument(
        "--groups",
        nargs="*",
        default=None,
        help="指定安装分组；不传则安装默认分组（不含 optional_ai）",
    )
    parser.add_argument(
        "--include-optional-ai",
        action="store_true",
        help="包含 optional_ai 分组",
    )
    parser.add_argument(
        "--skip-pip-upgrade",
        action="store_true",
        help="跳过 pip 升级",
    )
    parser.add_argument(
        "--skip-installed",
        action="store_true",
        help="跳过已安装包",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印命令，不实际执行安装",
    )
    parser.add_argument(
        "--json-report",
        default=None,
        help="把安装结果写入 JSON 文件，例如 report_install.json",
    )
    return parser.parse_args()


def print_summary(summary: InstallSummary) -> None:
    print_header("安装结果汇总")

    print(f"成功数量: {len(summary.success)}")
    for item in summary.success:
        print(f"  [OK] {item.package} (group={item.group})")

    print(f"\n失败数量: {len(summary.failed)}")
    if summary.failed:
        for item in summary.failed:
            print(f"  [FAILED] {item.package} (group={item.group})")
    else:
        print("  无")

    print(f"\n跳过数量: {len(summary.skipped)}")
    if summary.skipped:
        for item in summary.skipped:
            print(f"  [SKIPPED] {item.package} (group={item.group})")
    else:
        print("  无")


def main() -> int:
    args = parse_args()

    print_header("Python 环境安装脚本")
    print(f"当前 Python 路径: {current_python()}")

    try:
        selected_groups = resolve_group_names(
            groups=args.groups,
            include_optional_ai=args.include_optional_ai,
        )
    except ValueError as e:
        print(f"参数错误: {e}")
        return 2

    print("\n本次安装分组:")
    for group_name in selected_groups:
        print(f"  - {group_name}")

    summary = InstallSummary()

    if not args.skip_pip_upgrade:
        print_header("[1/3] 升级 pip")
        pip_ok = upgrade_pip(dry_run=args.dry_run)
        if not pip_ok:
            print("警告：pip 升级失败，但继续安装其他包。")
    else:
        print_header("[1/3] 已跳过 pip 升级")

    print_header("[2/3] 开始安装依赖")
    for group_name in selected_groups:
        install_group(
            group_name=group_name,
            packages=PACKAGE_GROUPS[group_name],
            summary=summary,
            skip_installed=args.skip_installed,
            dry_run=args.dry_run,
        )

    print_header("[3/3] 输出安装结果")
    print_summary(summary)

    if args.json_report:
        report = {
            "python": current_python(),
            "selected_groups": selected_groups,
            **summary.to_dict(),
        }
        save_json_report(args.json_report, report)
        print(f"\n已写入 JSON 报告: {args.json_report}")

    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
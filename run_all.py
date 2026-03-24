import argparse
import subprocess
import sys
from typing import List


def run_cmd(cmd: List[str]) -> int:
    print(f"\n>>> 执行: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, check=False)
    return result.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="一键安装并检查 Python 环境")
    parser.add_argument(
        "--groups",
        nargs="*",
        default=None,
        help="指定分组",
    )
    parser.add_argument(
        "--include-optional-ai",
        action="store_true",
        help="包含 optional_ai",
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
        help="只打印命令，不实际执行",
    )
    parser.add_argument(
        "--install-json-report",
        default="report_install.json",
        help="安装结果 JSON 报告路径",
    )
    parser.add_argument(
        "--check-json-report",
        default="report_check.json",
        help="检查结果 JSON 报告路径",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    install_cmd = [sys.executable, "install_env.py"]
    check_cmd = [sys.executable, "check_env.py"]

    if args.groups:
        install_cmd += ["--groups", *args.groups]
        check_cmd += ["--groups", *args.groups]

    if args.include_optional_ai:
        install_cmd.append("--include-optional-ai")
        check_cmd.append("--include-optional-ai")

    if args.skip_pip_upgrade:
        install_cmd.append("--skip-pip-upgrade")

    if args.skip_installed:
        install_cmd.append("--skip-installed")

    if args.dry_run:
        install_cmd.append("--dry-run")

    if args.install_json_report:
        install_cmd += ["--json-report", args.install_json_report]

    if args.check_json_report:
        check_cmd += ["--json-report", args.check_json_report]

    print("=" * 72)
    print("步骤 1/2：执行安装")
    print("=" * 72)
    install_code = run_cmd(install_cmd)

    if install_code not in (0, 1):
        print(f"安装阶段出现参数或运行错误，退出码: {install_code}")
        return install_code

    print("\n" + "=" * 72)
    print("步骤 2/2：执行检查")
    print("=" * 72)
    check_code = run_cmd(check_cmd)

    if install_code == 1 or check_code == 1:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
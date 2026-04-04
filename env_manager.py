import argparse
import importlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import venv
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

try:
    from importlib.metadata import version as pkg_version
except ImportError:
    from importlib_metadata import version as pkg_version  # type: ignore


# =========================
# 包分组配置
# =========================
PACKAGE_GROUPS: Dict[str, List[str]] = {
    "daily_common": [
        "numpy",
        "pandas",
        "matplotlib",
        "seaborn",
        "jupyter",
        "notebook",
        "ipykernel",
        "requests",
        "openpyxl",
        "xlrd",
        "xlsxwriter",
        "python-docx",
        "tqdm",
    ],
    "scientific_research": [
        "scipy",
        "scikit-learn",
        "statsmodels",
        "sympy",
        "networkx",
    ],
    "visualization": [
        "plotly",
        "bokeh",
    ],
    "data_processing": [
        "pyyaml",
        "beautifulsoup4",
        "lxml",
    ],
    "optional_ai": [
        "torch",
        "transformers",
        "datasets",
    ],
}

DEFAULT_GROUPS = [
    "daily_common",
    "scientific_research",
    "visualization",
    "data_processing",
]

# pip 包名 -> import 名
IMPORT_NAME_MAP: Dict[str, str] = {
    "pyyaml": "yaml",
    "beautifulsoup4": "bs4",
    "python-docx": "docx",
    "scikit-learn": "sklearn",
}

PIP_COMMON_FLAGS = [
    "--disable-pip-version-check",
    "--no-input",
]

APP_VERSION = "1.2.0"
GITHUB_REPO_OWNER = "wzgig"
GITHUB_REPO_NAME = "env_tool"


@dataclass
class PipInstallOptions:
    index_url: Optional[str] = None
    extra_index_urls: List[str] = field(default_factory=list)
    trusted_hosts: List[str] = field(default_factory=list)
    timeout: Optional[int] = None
    retries: Optional[int] = None


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def can_run_python_cmd(cmd: List[str]) -> bool:
    try:
        result = subprocess.run(
            cmd + ["-c", "import sys;print(sys.executable)"],
            check=False,
            text=True,
            capture_output=True,
            timeout=8,
        )
        return result.returncode == 0
    except Exception:
        return False


def split_python_spec(spec: str) -> List[str]:
    """把用户输入的 Python 命令规范化为参数列表。"""
    text = (spec or "").strip()
    if not text:
        return []
    try:
        return shlex.split(text, posix=False)
    except Exception:
        return [text]


def discover_py_launcher_pythons() -> List[List[str]]:
    """通过 `py -0p` 枚举已安装 Python 路径（Windows）。"""
    if not shutil.which("py"):
        return []

    try:
        result = subprocess.run(
            ["py", "-0p"],
            check=False,
            text=True,
            capture_output=True,
            timeout=8,
        )
    except Exception:
        return []

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    commands: List[List[str]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.search(r"([A-Za-z]:\\[^\s]+python\.exe)", line, re.IGNORECASE)
        if match:
            commands.append([match.group(1)])
    return commands


def discover_common_windows_pythons() -> List[List[str]]:
    """扫描常见安装目录中的 python.exe。"""
    candidates: List[List[str]] = []
    roots: List[Path] = []

    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        roots.append(Path(local_app) / "Programs" / "Python")

    program_files = os.environ.get("ProgramFiles")
    if program_files:
        roots.append(Path(program_files) / "Python")

    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if program_files_x86:
        roots.append(Path(program_files_x86) / "Python")

    for root in roots:
        if not root.exists():
            continue
        for python_exe in root.glob("Python*/python.exe"):
            candidates.append([str(python_exe)])

    return candidates


def discover_python_commands() -> List[List[str]]:
    """发现可作为目标环境的 Python 命令，按优先级排序。"""
    candidates: List[List[str]] = []

    env_python = os.environ.get("ENV_TOOL_PYTHON", "").strip()
    if env_python:
        parsed = split_python_spec(env_python)
        if parsed:
            candidates.append(parsed)

    exe_path = Path(sys.executable).resolve()
    candidates.extend(
        [
            [str(exe_path.parent / "python.exe")],
            [str(exe_path.parent.parent / "python.exe")],
        ]
    )

    # 优先 `py -3`，避免落到 Python 2
    if shutil.which("py"):
        candidates.append(["py", "-3"])
    if shutil.which("python"):
        candidates.append(["python"])
    if shutil.which("python3"):
        candidates.append(["python3"])

    candidates.extend(discover_py_launcher_pythons())
    candidates.extend(discover_common_windows_pythons())

    deduped: List[List[str]] = []
    seen = set()
    for cmd in candidates:
        if not cmd:
            continue
        key = "\u0000".join(x.lower() for x in cmd)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cmd)
    return deduped


def resolve_python_cmd(user_python: Optional[str] = None) -> List[str]:
    """
    选择用于安装/检查第三方库的目标 Python 命令。
    - 源码运行默认使用当前解释器
    - exe 运行默认自动探测系统 Python
    """
    if user_python:
        cmd = split_python_spec(user_python)
        if not cmd:
            raise RuntimeError("--python 不能为空")
        if can_run_python_cmd(cmd):
            return cmd
        raise RuntimeError(f"指定的 Python 不可用: {user_python}")

    # 非打包运行时，默认直接使用当前 Python
    if not is_frozen_app():
        return [sys.executable]

    candidates = discover_python_commands()

    for cmd in candidates:
        if can_run_python_cmd(cmd):
            return cmd

    raise RuntimeError(
        "未找到可用的 Python 解释器。请安装 Python，或使用 --python 显式指定。"
    )


def pip_base_cmd(python_cmd: List[str]) -> List[str]:
    return python_cmd + ["-m", "pip"]


def pip_install_extra_flags(options: Optional[PipInstallOptions] = None) -> List[str]:
    if options is None:
        return []

    flags: List[str] = []

    if options.index_url:
        flags.extend(["--index-url", options.index_url])

    for url in unique_preserve_order(options.extra_index_urls):
        flags.extend(["--extra-index-url", url])

    for host in unique_preserve_order(options.trusted_hosts):
        flags.extend(["--trusted-host", host])

    if options.timeout is not None:
        flags.extend(["--timeout", str(options.timeout)])

    if options.retries is not None:
        flags.extend(["--retries", str(options.retries)])

    return flags


# =========================
# 数据结构
# =========================
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


@dataclass
class CheckResult:
    package: str
    import_name: str
    ok: bool
    version: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CheckSummary:
    passed: List[CheckResult] = field(default_factory=list)
    failed: List[CheckResult] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "passed": [x.to_dict() for x in self.passed],
            "failed": [x.to_dict() for x in self.failed],
            "passed_count": len(self.passed),
            "failed_count": len(self.failed),
        }


# =========================
# 通用工具
# =========================
def print_header(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        value = str(item).strip()
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def current_python() -> str:
    return sys.executable


def render_python_cmd(python_cmd: List[str]) -> str:
    return " ".join(python_cmd)


def normalize_version_tag(tag: str) -> str:
    text = str(tag or "").strip()
    if text.lower().startswith("v"):
        text = text[1:]
    return text


def save_json_report(path: str, data: Dict) -> None:
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_group_names(
    groups: Optional[List[str]],
    include_optional_ai: bool = False,
) -> List[str]:
    if groups:
        invalid = [g for g in groups if g not in PACKAGE_GROUPS]
        if invalid:
            raise ValueError(
                f"无效分组: {invalid}\n可选分组: {list(PACKAGE_GROUPS.keys())}"
            )
        selected = groups[:]
    else:
        selected = DEFAULT_GROUPS[:]

    if include_optional_ai and "optional_ai" not in selected:
        selected.append("optional_ai")

    return unique_preserve_order(selected)


def resolve_packages(args: argparse.Namespace) -> List[str]:
    if args.only:
        return unique_preserve_order(args.only)

    groups = resolve_group_names(
        groups=args.groups,
        include_optional_ai=args.include_optional_ai,
    )

    packages: List[str] = []
    for group_name in groups:
        packages.extend(PACKAGE_GROUPS[group_name])
    return unique_preserve_order(packages)


def package_to_group_map(
    selected_groups: List[str],
    custom_packages: Optional[List[str]] = None,
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}

    if custom_packages:
        for pkg in custom_packages:
            mapping[pkg] = "__custom__"
        return mapping

    for group_name in selected_groups:
        for pkg in PACKAGE_GROUPS[group_name]:
            mapping[pkg] = group_name
    return mapping


def run_command(
    cmd: List[str],
    dry_run: bool = False,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    print(f"\n>>> 执行命令: {' '.join(cmd)}\n")

    if dry_run:
        print("[DRY-RUN] 仅预览，不实际执行。")
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="",
            stderr="",
        )

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
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr=f"{type(e).__name__}: {e}",
        )


# =========================
# 安装逻辑
# =========================
def upgrade_pip(
    python_cmd: List[str],
    dry_run: bool = False,
    options: Optional[PipInstallOptions] = None,
) -> bool:
    cmd = (
        pip_base_cmd(python_cmd)
        + ["install", "--upgrade", "pip"]
        + pip_install_extra_flags(options)
        + PIP_COMMON_FLAGS
    )
    result = run_command(cmd, dry_run=dry_run, capture_output=True)
    if result.returncode != 0 and result.stderr:
        print(result.stderr.strip())
    return result.returncode == 0


def is_package_installed(package_name: str, python_cmd: List[str]) -> bool:
    cmd = pip_base_cmd(python_cmd) + ["show", package_name]
    result = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def install_packages(
    packages: List[str],
    python_cmd: List[str],
    dry_run: bool = False,
    options: Optional[PipInstallOptions] = None,
) -> subprocess.CompletedProcess:
    if not packages:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    cmd = (
        pip_base_cmd(python_cmd)
        + ["install"]
        + packages
        + pip_install_extra_flags(options)
        + PIP_COMMON_FLAGS
    )
    return run_command(cmd, dry_run=dry_run, capture_output=True)


def install_one_package(
    package_name: str,
    python_cmd: List[str],
    dry_run: bool = False,
    options: Optional[PipInstallOptions] = None,
) -> subprocess.CompletedProcess:
    return install_packages(
        [package_name],
        python_cmd=python_cmd,
        dry_run=dry_run,
        options=options,
    )


def install_selected_packages(
    packages: List[str],
    pkg_group_map: Dict[str, str],
    python_cmd: List[str],
    skip_installed: bool = False,
    dry_run: bool = False,
    options: Optional[PipInstallOptions] = None,
) -> InstallSummary:
    summary = InstallSummary()

    grouped_packages: Dict[str, List[str]] = {}
    for pkg in packages:
        group_name = pkg_group_map.get(pkg, "__custom__")
        grouped_packages.setdefault(group_name, []).append(pkg)

    for group_name, group_packages in grouped_packages.items():
        print_header(f"开始安装分组: {group_name}")

        to_install: List[str] = []
        for pkg in unique_preserve_order(group_packages):
            if skip_installed and not dry_run and is_package_installed(pkg, python_cmd):
                print(f"已安装，跳过: {pkg}")
                summary.skipped.append(
                    InstallResult(package=pkg, ok=True, group=group_name, skipped=True)
                )
            else:
                to_install.append(pkg)

        if not to_install:
            print(f"分组 {group_name} 无需安装。")
            continue

        print(f"本组待安装包数量: {len(to_install)}")
        print("先尝试批量安装...")

        batch_result = install_packages(
            to_install,
            python_cmd=python_cmd,
            dry_run=dry_run,
            options=options,
        )
        if batch_result.returncode == 0:
            print(f"分组 {group_name} 批量安装成功。")
            for pkg in to_install:
                summary.success.append(
                    InstallResult(package=pkg, ok=True, group=group_name)
                )
            continue

        print(f"分组 {group_name} 批量安装失败，改为逐个安装。")
        if batch_result.stderr:
            print("批量安装错误摘要：")
            print(batch_result.stderr.strip()[:2000])

        for pkg in to_install:
            result = install_one_package(
                pkg,
                python_cmd=python_cmd,
                dry_run=dry_run,
                options=options,
            )
            if result.returncode == 0:
                print(f"安装成功: {pkg}")
                summary.success.append(
                    InstallResult(package=pkg, ok=True, group=group_name)
                )
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

    return summary


def install_selected_packages_offline(
    packages: List[str],
    pkg_group_map: Dict[str, str],
    python_cmd: List[str],
    wheel_dir: str,
    skip_installed: bool = False,
    dry_run: bool = False,
    options: Optional[PipInstallOptions] = None,
) -> InstallSummary:
    summary = InstallSummary()

    grouped_packages: Dict[str, List[str]] = {}
    for pkg in packages:
        group_name = pkg_group_map.get(pkg, "__custom__")
        grouped_packages.setdefault(group_name, []).append(pkg)

    for group_name, group_packages in grouped_packages.items():
        print_header(f"开始离线安装分组: {group_name}")

        to_install: List[str] = []
        for pkg in unique_preserve_order(group_packages):
            if skip_installed and not dry_run and is_package_installed(pkg, python_cmd):
                print(f"已安装，跳过: {pkg}")
                summary.skipped.append(
                    InstallResult(package=pkg, ok=True, group=group_name, skipped=True)
                )
            else:
                to_install.append(pkg)

        if not to_install:
            print(f"分组 {group_name} 无需安装。")
            continue

        print(f"本组待安装包数量: {len(to_install)}")
        print(f"离线 wheel 仓库: {wheel_dir}")

        batch_result = offline_install_packages(
            to_install,
            python_cmd=python_cmd,
            wheel_dir=wheel_dir,
            dry_run=dry_run,
            options=options,
        )
        if batch_result.returncode == 0:
            print(f"分组 {group_name} 离线批量安装成功。")
            for pkg in to_install:
                summary.success.append(InstallResult(package=pkg, ok=True, group=group_name))
            continue

        print(f"分组 {group_name} 离线批量安装失败。")
        if batch_result.stderr:
            print(batch_result.stderr.strip()[:2000])

        for pkg in to_install:
            result = offline_install_packages(
                [pkg],
                python_cmd=python_cmd,
                wheel_dir=wheel_dir,
                dry_run=dry_run,
                options=options,
            )
            if result.returncode == 0:
                print(f"安装成功: {pkg}")
                summary.success.append(InstallResult(package=pkg, ok=True, group=group_name))
            else:
                error_text = (result.stderr or result.stdout or "未知错误").strip()[:1000]
                print(f"安装失败: {pkg}")
                print(error_text)
                summary.failed.append(
                    InstallResult(package=pkg, ok=False, group=group_name, error=error_text)
                )

    return summary


def print_install_summary(summary: InstallSummary) -> None:
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


# =========================
# 检查逻辑
# =========================
def resolve_import_name(package_name: str) -> str:
    return IMPORT_NAME_MAP.get(package_name, package_name)


def get_installed_version(package_name: str) -> str:
    try:
        return pkg_version(package_name)
    except Exception:
        return "unknown"


def get_installed_version_by_python(package_name: str, python_cmd: List[str]) -> str:
    cmd = python_cmd + [
        "-c",
        (
            "import sys; "
            "from importlib.metadata import version as v; "
            "name=sys.argv[1]; "
            "print(v(name), end='')"
        ),
        package_name,
    ]
    result = run_command(cmd, dry_run=False, capture_output=True)
    if result.returncode == 0:
        return (result.stdout or "").strip() or "unknown"
    return "unknown"


def check_jupyter_cli(python_cmd: List[str]) -> None:
    result = run_command(
        python_cmd + ["-m", "jupyter", "--version"],
        dry_run=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "jupyter CLI 不可用").strip())


def export_requirements_snapshot(
    python_cmd: List[str],
    output_path: str,
    dry_run: bool = False,
) -> bool:
    cmd = pip_base_cmd(python_cmd) + ["freeze"]
    result = run_command(cmd, dry_run=dry_run, capture_output=True)
    if result.returncode != 0:
        print((result.stderr or "导出 requirements 失败").strip())
        return False

    if dry_run:
        print(f"[DRY-RUN] 将写入快照文件: {output_path}")
        return True

    Path(output_path).write_text(result.stdout or "", encoding="utf-8")
    print(f"已导出环境快照: {output_path}")
    return True


def restore_from_snapshot(
    python_cmd: List[str],
    snapshot_file: str,
    dry_run: bool = False,
    options: Optional[PipInstallOptions] = None,
) -> bool:
    path = Path(snapshot_file)
    if not path.exists():
        print(f"未找到快照文件: {path}")
        return False

    cmd = (
        pip_base_cmd(python_cmd)
        + ["install", "-r", str(path)]
        + pip_install_extra_flags(options)
        + PIP_COMMON_FLAGS
    )
    result = run_command(cmd, dry_run=dry_run, capture_output=True)
    if result.returncode != 0:
        print((result.stderr or result.stdout or "从快照恢复失败").strip())
        return False

    print(f"已从快照恢复: {path}")
    return True


def offline_install_packages(
    packages: List[str],
    python_cmd: List[str],
    wheel_dir: str,
    dry_run: bool = False,
    options: Optional[PipInstallOptions] = None,
) -> subprocess.CompletedProcess:
    wheel_path = Path(wheel_dir)
    if not wheel_path.exists():
        return subprocess.CompletedProcess(
            args=[],
            returncode=2,
            stdout="",
            stderr=f"未找到 wheel 仓库目录: {wheel_path}",
        )

    cmd = (
        pip_base_cmd(python_cmd)
        + ["install", "--no-index", "--find-links", str(wheel_path)]
        + packages
        + pip_install_extra_flags(options)
        + PIP_COMMON_FLAGS
    )
    return run_command(cmd, dry_run=dry_run, capture_output=True)


def create_venv_environment(venv_path: str, with_pip: bool = True) -> Path:
    target = Path(venv_path).expanduser().resolve()
    builder = venv.EnvBuilder(with_pip=with_pip, clear=False, symlinks=False, upgrade_deps=False)
    builder.create(str(target))
    return target


def venv_python_path(venv_path: str) -> Path:
    base = Path(venv_path).expanduser().resolve()
    if os.name == "nt":
        return base / "Scripts" / "python.exe"
    return base / "bin" / "python"


def diagnose_environment(
    python_cmd: List[str],
    packages: List[str],
    output_path: str,
    dry_run: bool = False,
) -> bool:
    report: Dict = {
        "app_version": APP_VERSION,
        "current_python": current_python(),
        "target_python_cmd": python_cmd,
        "platform": sys.platform,
        "executable": sys.executable,
        "python_version": sys.version,
        "pip_version": None,
        "network": {},
        "packages": [],
    }

    pip_result = run_command(pip_base_cmd(python_cmd) + ["--version"], dry_run=dry_run, capture_output=True)
    if pip_result.returncode == 0:
        report["pip_version"] = (pip_result.stdout or pip_result.stderr or "").strip()

    for url in [
        "https://pypi.org/simple/",
        "https://github.com/",
    ]:
        try:
            req = Request(url, headers={"User-Agent": f"EnvTool/{APP_VERSION}"})
            with urlopen(req, timeout=6) as resp:
                report["network"][url] = {"ok": True, "status": getattr(resp, "status", 200)}
        except Exception as e:
            report["network"][url] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    for pkg in unique_preserve_order(packages):
        result = check_one_package(pkg, python_cmd=python_cmd if python_cmd != [sys.executable] else None)
        report["packages"].append(result.to_dict())

    if dry_run:
        print(f"[DRY-RUN] 将写入诊断报告: {output_path}")
        return True

    Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入诊断报告: {output_path}")
    return True


def get_latest_github_release(repo_owner: str, repo_name: str) -> Optional[Dict]:
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
    req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"EnvTool/{APP_VERSION}"})
    try:
        with urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        print(f"更新检查失败: {e}")
    except Exception as e:
        print(f"更新检查失败: {type(e).__name__}: {e}")
    return None


def check_for_updates(repo_owner: str, repo_name: str) -> Dict:
    latest = get_latest_github_release(repo_owner, repo_name)
    if not latest:
        return {"ok": False, "current_version": APP_VERSION, "latest_version": None, "update_available": False}

    latest_tag = str(latest.get("tag_name", "")).strip()
    update_available = bool(latest_tag and normalize_version_tag(latest_tag) != normalize_version_tag(APP_VERSION))
    return {
        "ok": True,
        "current_version": APP_VERSION,
        "latest_version": latest_tag,
        "update_available": update_available,
        "release_name": latest.get("name"),
        "html_url": latest.get("html_url"),
        "assets": [
            {
                "name": asset.get("name"),
                "browser_download_url": asset.get("browser_download_url"),
                "size": asset.get("size"),
            }
            for asset in latest.get("assets", [])
            if isinstance(asset, dict)
        ],
    }


def check_one_package_by_python(package_name: str, python_cmd: List[str]) -> CheckResult:
    version = get_installed_version_by_python(package_name, python_cmd)
    import_name = resolve_import_name(package_name)

    try:
        if package_name == "jupyter":
            check_jupyter_cli(python_cmd)
            return CheckResult(
                package=package_name,
                import_name="jupyter(cli)",
                ok=True,
                version=version,
            )

        check_cmd = python_cmd + [
            "-c",
            (
                "import importlib,sys;"
                "name=sys.argv[1];"
                "importlib.import_module(name)"
            ),
            import_name,
        ]
        result = run_command(check_cmd, dry_run=False, capture_output=True)
        if result.returncode == 0:
            return CheckResult(
                package=package_name,
                import_name=import_name,
                ok=True,
                version=version,
            )

        error_text = (result.stderr or result.stdout or "导入失败").strip()
        return CheckResult(
            package=package_name,
            import_name=import_name,
            ok=False,
            version=version,
            error=error_text[:1000],
        )
    except Exception as e:
        return CheckResult(
            package=package_name,
            import_name="jupyter(cli)" if package_name == "jupyter" else import_name,
            ok=False,
            version=version,
            error=f"{type(e).__name__}: {e}",
        )


def smoke_test_numpy(module) -> None:
    arr = module.array([1, 2, 3])
    assert int(arr.sum()) == 6


def smoke_test_pandas(module) -> None:
    df = module.DataFrame({"a": [1, 2], "b": [3, 4]})
    assert int(df["a"].sum()) == 3


def smoke_test_matplotlib(module) -> None:
    module.use("Agg")
    plt = importlib.import_module("matplotlib.pyplot")

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.plot([1, 2], [3, 4])
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    _ = buf.getvalue()


def smoke_test_seaborn(module) -> None:
    module.set_theme()


def smoke_test_notebook(module) -> None:
    assert module is not None


def smoke_test_ipykernel(module) -> None:
    assert module is not None


def smoke_test_requests(module) -> None:
    session = module.Session()
    req = module.Request("GET", "https://example.com")
    prepped = session.prepare_request(req)
    assert prepped.method == "GET"


def smoke_test_openpyxl(module) -> None:
    wb = module.Workbook()
    ws = wb.active
    ws["A1"] = "ok"
    assert ws["A1"].value == "ok"


def smoke_test_xlrd(module) -> None:
    assert module is not None


def smoke_test_xlsxwriter(module) -> None:
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = os.path.join(temp_dir, "test.xlsx")
        workbook = module.Workbook(file_path)
        worksheet = workbook.add_worksheet()
        worksheet.write("A1", "ok")
        workbook.close()

        assert os.path.exists(file_path)
        assert os.path.getsize(file_path) > 0


def smoke_test_docx(module) -> None:
    doc = module.Document()
    doc.add_paragraph("ok")
    assert len(doc.paragraphs) >= 1


def smoke_test_tqdm(module) -> None:
    list(module.tqdm(range(3), disable=True))


def smoke_test_scipy(module) -> None:
    det = module.linalg.det([[1, 0], [0, 1]])
    assert round(float(det), 6) == 1.0


def smoke_test_sklearn(module) -> None:
    linear_model = importlib.import_module("sklearn.linear_model")
    LinearRegression = getattr(linear_model, "LinearRegression")

    X = [[1], [2], [3]]
    y = [2, 4, 6]
    model = LinearRegression().fit(X, y)
    pred = model.predict([[4]])[0]
    assert pred > 0


def smoke_test_statsmodels(module) -> None:
    np = importlib.import_module("numpy")
    sm = importlib.import_module("statsmodels.api")

    X = np.array([1, 2, 3, 4], dtype=float)
    y = np.array([2, 4, 6, 8], dtype=float)
    X = sm.add_constant(X)
    model = sm.OLS(y, X).fit()
    assert len(model.params) == 2


def smoke_test_sympy(module) -> None:
    x = module.Symbol("x")
    expr = module.expand((x + 1) ** 2)
    assert str(expr) == "x**2 + 2*x + 1"


def smoke_test_networkx(module) -> None:
    g = module.Graph()
    g.add_edge("a", "b")
    assert g.number_of_edges() == 1


def smoke_test_plotly(module) -> None:
    go = importlib.import_module("plotly.graph_objects")
    fig = go.Figure(data=go.Scatter(x=[1, 2], y=[3, 4]))
    _ = fig.to_dict()


def smoke_test_bokeh(module) -> None:
    figure = getattr(importlib.import_module("bokeh.plotting"), "figure")
    p = figure(title="demo")
    p.line([1, 2], [3, 4])
    assert p.title.text == "demo"


def smoke_test_yaml(module) -> None:
    dumped = module.safe_dump({"a": 1}, allow_unicode=True)
    loaded = module.safe_load(dumped)
    assert loaded["a"] == 1


def smoke_test_bs4(module) -> None:
    soup = module.BeautifulSoup("<html><body><p>ok</p></body></html>", "html.parser")
    assert soup.p.text == "ok"


def smoke_test_lxml(module) -> None:
    etree = importlib.import_module("lxml.etree")
    root = etree.fromstring(b"<root><a>1</a></root>")
    assert root.tag == "root"


def smoke_test_torch(module) -> None:
    x = module.tensor([1, 2, 3])
    assert x.sum().item() == 6


def smoke_test_transformers(module) -> None:
    assert getattr(module, "AutoConfig", None) is not None


def smoke_test_datasets(module) -> None:
    ds = module.Dataset.from_dict({"x": [1, 2], "y": [3, 4]})
    assert len(ds) == 2


SMOKE_TESTS: Dict[str, Callable] = {
    "numpy": smoke_test_numpy,
    "pandas": smoke_test_pandas,
    "matplotlib": smoke_test_matplotlib,
    "seaborn": smoke_test_seaborn,
    "notebook": smoke_test_notebook,
    "ipykernel": smoke_test_ipykernel,
    "requests": smoke_test_requests,
    "openpyxl": smoke_test_openpyxl,
    "xlrd": smoke_test_xlrd,
    "xlsxwriter": smoke_test_xlsxwriter,
    "python-docx": smoke_test_docx,
    "tqdm": smoke_test_tqdm,
    "scipy": smoke_test_scipy,
    "scikit-learn": smoke_test_sklearn,
    "statsmodels": smoke_test_statsmodels,
    "sympy": smoke_test_sympy,
    "networkx": smoke_test_networkx,
    "plotly": smoke_test_plotly,
    "bokeh": smoke_test_bokeh,
    "pyyaml": smoke_test_yaml,
    "beautifulsoup4": smoke_test_bs4,
    "lxml": smoke_test_lxml,
    "torch": smoke_test_torch,
    "transformers": smoke_test_transformers,
    "datasets": smoke_test_datasets,
}


def check_one_package(package_name: str, python_cmd: Optional[List[str]] = None) -> CheckResult:
    if python_cmd:
        return check_one_package_by_python(package_name, python_cmd)

    version = get_installed_version(package_name)

    try:
        if package_name == "jupyter":
            check_jupyter_cli([sys.executable])
            return CheckResult(
                package=package_name,
                import_name="jupyter(cli)",
                ok=True,
                version=version,
            )

        import_name = resolve_import_name(package_name)
        module = importlib.import_module(import_name)

        smoke_test = SMOKE_TESTS.get(package_name)
        if smoke_test:
            smoke_test(module)

        return CheckResult(
            package=package_name,
            import_name=import_name,
            ok=True,
            version=version,
        )
    except Exception as e:
        import_name = "jupyter(cli)" if package_name == "jupyter" else resolve_import_name(package_name)
        return CheckResult(
            package=package_name,
            import_name=import_name,
            ok=False,
            version=version,
            error=f"{type(e).__name__}: {e}",
        )


def check_selected_packages(
    packages: List[str],
    python_cmd: Optional[List[str]] = None,
) -> CheckSummary:
    summary = CheckSummary()

    print_header("开始逐个检查")
    for package_name in packages:
        result = check_one_package(package_name, python_cmd=python_cmd)
        if result.ok:
            print(
                f"[OK] {result.package} (import={result.import_name}, version={result.version})"
            )
            summary.passed.append(result)
        else:
            print(
                f"[FAILED] {result.package} (import={result.import_name}) -> {result.error}"
            )
            summary.failed.append(result)

    return summary


def print_check_summary(summary: CheckSummary) -> None:
    print_header("检查结果汇总")

    print(f"通过数量: {len(summary.passed)}")
    for item in summary.passed:
        print(
            f"  [OK] {item.package:<18} import={item.import_name:<14} version={item.version}"
        )

    print(f"\n失败数量: {len(summary.failed)}")
    if summary.failed:
        for item in summary.failed:
            print(
                f"  [FAILED] {item.package:<18} import={item.import_name:<14} error={item.error}"
            )
    else:
        print("  无")


# =========================
# 参数与主流程
# =========================
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="单文件版 Python 环境安装与检查工具（当前 Python 解释器）"
    )
    parser.add_argument(
        "--mode",
        choices=["all", "install", "check", "snapshot", "restore", "offline", "venv", "diagnose", "update-check"],
        default="all",
        help="运行模式：all=安装后检查，install=只安装，check=只检查，snapshot=导出环境快照，restore=快照恢复，offline=离线安装，venv=创建虚拟环境，diagnose=诊断报告，update-check=检查更新",
    )
    parser.add_argument(
        "--groups",
        nargs="*",
        default=None,
        help="指定分组，不传则使用默认分组（不含 optional_ai）",
    )
    parser.add_argument(
        "--include-optional-ai",
        action="store_true",
        help="包含 optional_ai 分组",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="只处理指定包，例如 --only numpy pandas scipy",
    )
    parser.add_argument(
        "--skip-pip-upgrade",
        action="store_true",
        help="安装时跳过 pip 升级",
    )
    parser.add_argument(
        "--skip-installed",
        action="store_true",
        help="安装时跳过已安装的包",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印安装命令，不实际安装；检查阶段仍会真实执行",
    )
    parser.add_argument(
        "--json-report",
        default=None,
        help="把最终结果写入 JSON 文件，例如 report.json",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="指定目标 Python 路径（用于安装/检查），例如 C:\\Python313\\python.exe",
    )
    parser.add_argument(
        "--pause-on-exit",
        action="store_true",
        help="程序结束前等待回车（适合双击 exe 使用）",
    )
    parser.add_argument(
        "--snapshot-file",
        default="requirements_snapshot.txt",
        help="快照模式输出文件路径，默认 requirements_snapshot.txt",
    )
    parser.add_argument(
        "--wheel-dir",
        default=None,
        help="离线安装使用的 wheel 仓库目录",
    )
    parser.add_argument(
        "--venv-path",
        default=None,
        help="创建虚拟环境的目录路径",
    )
    parser.add_argument(
        "--diag-output",
        default="diagnostic_report.json",
        help="诊断模式输出路径，默认 diagnostic_report.json",
    )
    parser.add_argument(
        "--repo-owner",
        default=GITHUB_REPO_OWNER,
        help="用于检查更新的 GitHub 仓库 owner",
    )
    parser.add_argument(
        "--repo-name",
        default=GITHUB_REPO_NAME,
        help="用于检查更新的 GitHub 仓库名",
    )
    parser.add_argument(
        "--index-url",
        default=None,
        help="pip 主镜像源，例如 https://pypi.tuna.tsinghua.edu.cn/simple",
    )
    parser.add_argument(
        "--extra-index-url",
        nargs="*",
        default=None,
        help="pip 额外镜像源，可传多个",
    )
    parser.add_argument(
        "--trusted-host",
        nargs="*",
        default=None,
        help="pip 信任域名，可传多个，例如 pypi.tuna.tsinghua.edu.cn",
    )
    parser.add_argument(
        "--pip-timeout",
        type=int,
        default=None,
        help="pip 网络超时（秒）",
    )
    parser.add_argument(
        "--pip-retries",
        type=int,
        default=None,
        help="pip 重试次数",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parent

    print_header("Python 环境安装 / 检查工具")
    print(f"程序版本: {APP_VERSION}")
    print(f"当前运行时路径: {current_python()}")
    print(f"运行模式: {args.mode}")

    try:
        python_cmd = resolve_python_cmd(args.python)
    except RuntimeError as e:
        print(f"解释器错误: {e}")
        return 2

    print(f"目标 Python 命令: {render_python_cmd(python_cmd)}")

    pip_options = PipInstallOptions(
        index_url=(args.index_url or "").strip() or None,
        extra_index_urls=unique_preserve_order(args.extra_index_url or []),
        trusted_hosts=unique_preserve_order(args.trusted_host or []),
        timeout=args.pip_timeout,
        retries=args.pip_retries,
    )

    if args.mode == "snapshot":
        print_header("[快照阶段]")
        ok = export_requirements_snapshot(
            python_cmd=python_cmd,
            output_path=args.snapshot_file,
            dry_run=args.dry_run,
        )
        return 0 if ok else 1

    if args.mode == "restore":
        print_header("[恢复阶段]")
        ok = restore_from_snapshot(
            python_cmd=python_cmd,
            snapshot_file=args.snapshot_file,
            dry_run=args.dry_run,
            options=pip_options,
        )
        return 0 if ok else 1

    try:
        packages = resolve_packages(args)
        selected_groups = None if args.only else resolve_group_names(
            groups=args.groups,
            include_optional_ai=args.include_optional_ai,
        )
    except ValueError as e:
        print(f"参数错误: {e}")
        return 2

    print("\n本次目标包:")
    for pkg in packages:
        print(f"  - {pkg}")

    install_summary: Optional[InstallSummary] = None
    check_summary: Optional[CheckSummary] = None
    venv_result: Dict = {}

    if args.mode == "offline":
        print_header("[离线安装阶段]")
        wheel_dir = args.wheel_dir or ""
        if not wheel_dir:
            print("参数错误：离线安装需要 --wheel-dir 指定本地 wheel 仓库。")
            return 2

        pkg_group_map = package_to_group_map(
            selected_groups=selected_groups or [],
            custom_packages=packages if args.only else None,
        )
        install_summary = install_selected_packages_offline(
            packages=packages,
            pkg_group_map=pkg_group_map,
            python_cmd=python_cmd,
            wheel_dir=wheel_dir,
            skip_installed=args.skip_installed,
            dry_run=args.dry_run,
            options=pip_options,
        )
        print_install_summary(install_summary)

    elif args.mode == "venv":
        print_header("[虚拟环境阶段]")
        venv_dir = args.venv_path or str((project_root / ".envtool_venv").resolve())
        try:
            created = create_venv_environment(venv_dir, with_pip=True)
            venv_python = venv_python_path(str(created))
            print(f"已创建虚拟环境: {created}")
            print(f"虚拟环境 Python: {venv_python}")
            venv_result = {
                "venv_path": str(created),
                "venv_python": str(venv_python),
            }

            if packages:
                print_header("在虚拟环境中安装选定包")
                venv_summary = install_selected_packages(
                    packages=packages,
                    pkg_group_map=package_to_group_map(selected_groups=selected_groups or [], custom_packages=packages if args.only else None),
                    python_cmd=[str(venv_python)],
                    skip_installed=args.skip_installed,
                    dry_run=args.dry_run,
                    options=pip_options,
                )
                print_install_summary(venv_summary)
                install_summary = venv_summary
        except Exception as e:
            print(f"创建虚拟环境失败: {type(e).__name__}: {e}")
            return 1

    elif args.mode == "diagnose":
        print_header("[诊断阶段]")
        diag_packages = packages
        ok = diagnose_environment(
            python_cmd=python_cmd,
            packages=diag_packages,
            output_path=args.diag_output,
            dry_run=args.dry_run,
        )
        if not ok:
            return 1
        if args.json_report:
            save_json_report(
                args.json_report,
                {
                    "mode": "diagnose",
                    "app_version": APP_VERSION,
                    "current_python": current_python(),
                    "target_python_cmd": python_cmd,
                    "diagnostic_output": args.diag_output,
                },
            )
        return 0

    elif args.mode == "update-check":
        print_header("[更新检查]")
        update_info = check_for_updates(args.repo_owner, args.repo_name)
        print(f"当前版本: {update_info.get('current_version')}")
        print(f"最新版本: {update_info.get('latest_version')}")
        print(f"是否有更新: {'是' if update_info.get('update_available') else '否'}")
        if update_info.get("html_url"):
            print(f"Release 页面: {update_info.get('html_url')}")
        if update_info.get("assets"):
            print("可下载资产:")
            for asset in update_info["assets"]:
                print(f"  - {asset.get('name')}: {asset.get('browser_download_url')}")
        if args.json_report:
            save_json_report(args.json_report, update_info)
            print(f"\n已写入 JSON 报告: {args.json_report}")
        return 0

    if args.mode in ("all", "install"):
        print_header("[安装阶段]")

        if not args.skip_pip_upgrade:
            print_header("先升级 pip")
            pip_ok = upgrade_pip(
                python_cmd=python_cmd,
                dry_run=args.dry_run,
                options=pip_options,
            )
            if not pip_ok:
                print("警告：pip 升级失败，但继续安装其他包。")
        else:
            print("已跳过 pip 升级。")

        pkg_group_map = package_to_group_map(
            selected_groups=selected_groups or [],
            custom_packages=packages if args.only else None,
        )

        install_summary = install_selected_packages(
            packages=packages,
            pkg_group_map=pkg_group_map,
            python_cmd=python_cmd,
            skip_installed=args.skip_installed,
            dry_run=args.dry_run,
            options=pip_options,
        )
        print_install_summary(install_summary)

    if args.mode in ("all", "check"):
        print_header("[检查阶段]")
        subprocess_mode = python_cmd != [sys.executable]
        check_summary = check_selected_packages(
            packages,
            python_cmd=python_cmd if subprocess_mode else None,
        )
        print_check_summary(check_summary)

    if args.json_report:
        report = {
            "python": current_python(),
            "target_python_cmd": python_cmd,
            "mode": args.mode,
            "selected_groups": selected_groups,
            "packages": packages,
            "install": install_summary.to_dict() if install_summary else None,
            "check": check_summary.to_dict() if check_summary else None,
        }
        if args.mode == "offline":
            report["workflow"] = {
                "type": "offline",
                "wheel_dir": args.wheel_dir,
            }
        if args.mode == "venv":
            report["workflow"] = {
                "type": "venv",
                "venv_path": args.venv_path,
                "venv_result": venv_result,
            }
        save_json_report(args.json_report, report)
        print(f"\n已写入 JSON 报告: {args.json_report}")

    install_failed = bool(install_summary and install_summary.failed)
    check_failed = bool(check_summary and check_summary.failed)

    return 1 if install_failed or check_failed else 0


if __name__ == "__main__":
    exit_code = main()
    if "--pause-on-exit" in sys.argv:
        try:
            input("\n执行完毕，按回车键退出...")
        except EOFError:
            pass
    sys.exit(exit_code)
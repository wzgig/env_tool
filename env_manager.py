import argparse
import importlib
import io
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

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

PIP_BASE_CMD = [sys.executable, "-m", "pip"]
PIP_COMMON_FLAGS = [
    "--disable-pip-version-check",
    "--no-input",
]


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


def install_selected_packages(
    packages: List[str],
    pkg_group_map: Dict[str, str],
    skip_installed: bool = False,
    dry_run: bool = False,
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
            if skip_installed and not dry_run and is_package_installed(pkg):
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

        batch_result = install_packages(to_install, dry_run=dry_run)
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
            result = install_one_package(pkg, dry_run=dry_run)
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


def check_jupyter_cli() -> None:
    result = run_command(
        [sys.executable, "-m", "jupyter", "--version"],
        dry_run=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "jupyter CLI 不可用").strip())


def smoke_test_numpy(module) -> None:
    arr = module.array([1, 2, 3])
    assert int(arr.sum()) == 6


def smoke_test_pandas(module) -> None:
    df = module.DataFrame({"a": [1, 2], "b": [3, 4]})
    assert int(df["a"].sum()) == 3


def smoke_test_matplotlib(module) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

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
    import scipy.linalg
    det = scipy.linalg.det([[1, 0], [0, 1]])
    assert round(float(det), 6) == 1.0


def smoke_test_sklearn(module) -> None:
    from sklearn.linear_model import LinearRegression

    X = [[1], [2], [3]]
    y = [2, 4, 6]
    model = LinearRegression().fit(X, y)
    pred = model.predict([[4]])[0]
    assert pred > 0


def smoke_test_statsmodels(module) -> None:
    import numpy as np
    import statsmodels.api as sm

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
    import plotly.graph_objects as go
    fig = go.Figure(data=go.Scatter(x=[1, 2], y=[3, 4]))
    _ = fig.to_dict()


def smoke_test_bokeh(module) -> None:
    from bokeh.plotting import figure
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
    from lxml import etree
    root = etree.fromstring(b"<root><a>1</a></root>")
    assert root.tag == "root"


def smoke_test_torch(module) -> None:
    x = module.tensor([1, 2, 3])
    assert x.sum().item() == 6


def smoke_test_transformers(module) -> None:
    from transformers import AutoConfig
    assert AutoConfig is not None


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


def check_one_package(package_name: str) -> CheckResult:
    version = get_installed_version(package_name)

    try:
        if package_name == "jupyter":
            check_jupyter_cli()
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


def check_selected_packages(packages: List[str]) -> CheckSummary:
    summary = CheckSummary()

    print_header("开始逐个检查")
    for package_name in packages:
        result = check_one_package(package_name)
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
        choices=["all", "install", "check"],
        default="all",
        help="运行模式：all=安装后检查，install=只安装，check=只检查",
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print_header("Python 环境安装 / 检查工具")
    print(f"当前 Python 路径: {current_python()}")
    print(f"运行模式: {args.mode}")

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

    if args.mode in ("all", "install"):
        print_header("[安装阶段]")

        if not args.skip_pip_upgrade:
            print_header("先升级 pip")
            pip_ok = upgrade_pip(dry_run=args.dry_run)
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
            skip_installed=args.skip_installed,
            dry_run=args.dry_run,
        )
        print_install_summary(install_summary)

    if args.mode in ("all", "check"):
        print_header("[检查阶段]")
        check_summary = check_selected_packages(packages)
        print_check_summary(check_summary)

    if args.json_report:
        report = {
            "python": current_python(),
            "mode": args.mode,
            "selected_groups": selected_groups,
            "packages": packages,
            "install": install_summary.to_dict() if install_summary else None,
            "check": check_summary.to_dict() if check_summary else None,
        }
        save_json_report(args.json_report, report)
        print(f"\n已写入 JSON 报告: {args.json_report}")

    install_failed = bool(install_summary and install_summary.failed)
    check_failed = bool(check_summary and check_summary.failed)

    return 1 if install_failed or check_failed else 0


if __name__ == "__main__":
    sys.exit(main())
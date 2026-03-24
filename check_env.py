import argparse
import importlib
import io
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional

from common import (
    current_python,
    print_header,
    resolve_group_names,
    resolve_packages_from_groups,
    save_json_report,
    unique_preserve_order,
)
from package_config import IMPORT_NAME_MAP


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


def resolve_import_name(package_name: str) -> str:
    return IMPORT_NAME_MAP.get(package_name, package_name)


def get_module_version(module, package_name: str) -> str:
    version = getattr(module, "__version__", None)
    if version:
        return str(version)

    try:
        from importlib.metadata import version as pkg_version
        return pkg_version(package_name)
    except Exception:
        return "unknown"


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


def smoke_test_seaborn(module) -> None:
    module.set_theme()


def smoke_test_jupyter(module) -> None:
    assert module is not None


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
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
        workbook = module.Workbook(tmp.name)
        worksheet = workbook.add_worksheet()
        worksheet.write("A1", "ok")
        workbook.close()


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
    "jupyter": smoke_test_jupyter,
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
    import_name = resolve_import_name(package_name)

    try:
        module = importlib.import_module(import_name)
        version = get_module_version(module, package_name)

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
        return CheckResult(
            package=package_name,
            import_name=import_name,
            ok=False,
            error=f"{type(e).__name__}: {e}",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查 Python 库是否可正常使用")
    parser.add_argument(
        "--groups",
        nargs="*",
        default=None,
        help="指定检查分组；不传则检查默认分组（不含 optional_ai）",
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
        help="仅检查指定包，例如 --only numpy pandas torch",
    )
    parser.add_argument(
        "--json-report",
        default=None,
        help="把检查结果写入 JSON 文件，例如 report_check.json",
    )
    return parser.parse_args()


def print_summary(summary: CheckSummary) -> None:
    print_header("检查结果汇总")

    print(f"通过数量: {len(summary.passed)}")
    for item in summary.passed:
        print(
            f"  [OK] {item.package:<18} import={item.import_name:<12} version={item.version}"
        )

    print(f"\n失败数量: {len(summary.failed)}")
    if summary.failed:
        for item in summary.failed:
            print(
                f"  [FAILED] {item.package:<18} import={item.import_name:<12} error={item.error}"
            )
    else:
        print("  无")


def main() -> int:
    args = parse_args()

    print_header("Python 库可用性检查脚本")
    print(f"当前 Python 路径: {current_python()}")

    if args.only:
        packages = unique_preserve_order(args.only)
        selected_groups = None
    else:
        try:
            selected_groups = resolve_group_names(
                groups=args.groups,
                include_optional_ai=args.include_optional_ai,
            )
        except ValueError as e:
            print(f"参数错误: {e}")
            return 2

        packages = resolve_packages_from_groups(selected_groups)

    print("\n本次待检查包:")
    for pkg in packages:
        print(f"  - {pkg}")

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

    print_summary(summary)

    if args.json_report:
        report = {
            "python": current_python(),
            "selected_groups": selected_groups,
            "checked_packages": packages,
            **summary.to_dict(),
        }
        save_json_report(args.json_report, report)
        print(f"\n已写入 JSON 报告: {args.json_report}")

    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
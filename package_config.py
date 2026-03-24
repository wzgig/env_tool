from typing import Dict, List

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

# pip 包名 -> import 名
IMPORT_NAME_MAP: Dict[str, str] = {
    "pyyaml": "yaml",
    "beautifulsoup4": "bs4",
    "python-docx": "docx",
    "scikit-learn": "sklearn",
}

DEFAULT_GROUPS = [
    "daily_common",
    "scientific_research",
    "visualization",
    "data_processing",
]
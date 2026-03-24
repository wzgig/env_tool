import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List

from package_config import DEFAULT_GROUPS, PACKAGE_GROUPS


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


def resolve_group_names(
    groups: List[str] | None,
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


def resolve_packages_from_groups(group_names: List[str]) -> List[str]:
    packages: List[str] = []
    for group_name in group_names:
        packages.extend(PACKAGE_GROUPS[group_name])
    return unique_preserve_order(packages)


def current_python() -> str:
    return sys.executable


def save_json_report(path: str, data: Dict) -> None:
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
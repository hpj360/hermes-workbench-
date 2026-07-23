#!/usr/bin/env python3
"""resolve.py - 解析 DTCG alias 引用 {path.to.token}"""

import re
from typing import Any, Dict, List, Tuple

ALIAS_RE = re.compile(r"\{([^}]+)\}")


def flatten_dtcg(obj: Dict, prefix: str = "") -> List[Tuple[str, Any, Dict]]:
    """递归展开 DTCG 格式为 [(path, value, metadata)]"""
    out = []
    for k, v in obj.items():
        if k.startswith("$"):
            continue
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict) and "$value" in v:
            meta = {k2: v2 for k2, v2 in v.items() if k2 != "$value"}
            out.append((path, v["$value"], meta))
        elif isinstance(v, dict):
            out.extend(flatten_dtcg(v, path))
    return out


def resolve_aliases(tokens: List[Tuple[str, Any, Dict]]) -> Dict[str, Any]:
    """解析 alias 引用"""
    # 先建立索引
    path_to_val: Dict[str, Any] = {}
    for path, val, _ in tokens:
        path_to_val[path] = val

    resolved: Dict[str, Any] = {}
    for path, val, meta in tokens:
        if isinstance(val, str):
            m = ALIAS_RE.fullmatch(val.strip())
            if m:
                ref = m.group(1)
                if ref in path_to_val:
                    resolved[path] = path_to_val[ref]
                    continue
        resolved[path] = val
    return resolved


def is_color(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    s = value.strip()
    return s.startswith("#") or s.lower().startswith("rgb") or s.lower().startswith("hsl")

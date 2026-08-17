"""Static contract: every bump_rate_counter scope is declared in SQL + Python."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.core.rate_counter_scopes import RATE_COUNTER_SCOPES

REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = Path(__file__).resolve().parents[1] / "app"
MIGRATIONS = REPO_ROOT / "supabase" / "migrations"
MANIFEST_MIGRATIONS = (
    MIGRATIONS / "20260813160000_rate_counter_scope_manifest.sql",
    MIGRATIONS / "20260817200000_rate_counter_event_access_unlock_scope.sql",
)

_INSERT_BLOCK = re.compile(
    r"insert into private\.rate_counter_scope_manifest \(scope\) values\s*(.*?);",
    re.IGNORECASE | re.DOTALL,
)
_SCOPE_TOKEN = re.compile(r"'([a-z0-9_]+)'")


def _manifest_scopes() -> frozenset[str]:
    found: set[str] = set()
    for path in MANIFEST_MIGRATIONS:
        text = path.read_text(encoding="utf-8")
        for block in _INSERT_BLOCK.findall(text):
            found.update(_SCOPE_TOKEN.findall(block))
    return frozenset(found)


def _str_const(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_func_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _kw(node: ast.Call, name: str) -> ast.AST | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _fstring_format(node: ast.JoinedStr) -> tuple[str, str] | None:
    """Return (format, name) for f-strings with exactly one Name interpolation."""
    fmt = ""
    names: list[str] = []
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            fmt += part.value
        elif isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name):
            fmt += "{}"
            names.append(part.value.id)
        else:
            return None
    if len(names) != 1:
        return None
    return fmt, names[0]


def _assigned_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
        node.targets[0], ast.Name
    ):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def _literal_call_kwargs(tree: ast.Module, func_name: str, kw: str) -> set[str]:
    values: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_func_name(node) != func_name:
            continue
        raw = _kw(node, kw)
        literal = _str_const(raw) if raw is not None else None
        if literal is not None:
            values.add(literal)
    return values


def _policy_assignments(tree: ast.AST) -> dict[str, str]:
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        name = _assigned_name(node)
        value = node.value if isinstance(node, ast.Assign) else node.value
        if name is None or not isinstance(value, ast.Call):
            continue
        if _call_func_name(value) != "RateLimitPolicy":
            continue
        scope_node = _kw(value, "scope")
        literal = _str_const(scope_node) if scope_node is not None else None
        if literal is not None:
            found[name] = literal
    return found


def _containing_function(
    tree: ast.Module, target: ast.AST
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    candidates: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(func):
            if child is target:
                candidates.append(func)
                break
    if not candidates:
        return None
    return max(candidates, key=lambda func: func.lineno)


def discover_python_scopes() -> tuple[frozenset[str], list[str]]:
    """Return resolved scopes and unresolved location messages."""
    sources = sorted(API_ROOT.rglob("*.py"))
    trees: dict[Path, ast.Module] = {}
    policy_names: dict[str, str] = {}
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        trees[path] = tree
        policy_names.update(_policy_assignments(tree))

    resolved: set[str] = set(policy_names.values())
    unresolved: list[str] = []

    for path, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_func_name(node) != "bump_rate_counter":
                continue
            scope_node = _kw(node, "scope")
            if scope_node is None:
                unresolved.append(f"{path}:{node.lineno}: bump_rate_counter missing scope=")
                continue

            literal = _str_const(scope_node)
            if literal is not None:
                resolved.add(literal)
                continue

            if isinstance(scope_node, ast.Attribute) and scope_node.attr == "scope":
                if isinstance(scope_node.value, ast.Name) and scope_node.value.id in policy_names:
                    resolved.add(policy_names[scope_node.value.id])
                    continue
                unresolved.append(
                    f"{path}:{node.lineno}: unresolved policy attribute {ast.dump(scope_node)}"
                )
                continue

            func = _containing_function(tree, node)
            if func is None:
                unresolved.append(f"{path}:{node.lineno}: bump_rate_counter outside a function")
                continue

            if func.name == "incr" and isinstance(scope_node, ast.Name):
                # PostgresRateLimitStorage rebuilds limiter keys; RateLimitPolicy covers those.
                continue

            if isinstance(scope_node, ast.Name):
                values = _literal_call_kwargs(tree, func.name, scope_node.id)
                if not values:
                    unresolved.append(
                        f"{path}:{node.lineno}: unresolved Name "
                        f"{scope_node.id} in {func.name}"
                    )
                    continue
                resolved.update(values)
                continue

            if isinstance(scope_node, ast.JoinedStr):
                parsed = _fstring_format(scope_node)
                if parsed is None:
                    unresolved.append(f"{path}:{node.lineno}: unresolved f-string scope")
                    continue
                fmt, name = parsed
                values = _literal_call_kwargs(tree, func.name, name)
                if not values:
                    unresolved.append(
                        f"{path}:{node.lineno}: unresolved f-string {{{name}}} in {func.name}"
                    )
                    continue
                resolved.update(fmt.format(value) for value in values)
                continue

            unresolved.append(
                f"{path}:{node.lineno}: unsupported scope expression {type(scope_node).__name__}"
            )

    return frozenset(resolved), unresolved


def test_python_registry_matches_sql_manifest() -> None:
    sql_scopes = _manifest_scopes()
    assert sql_scopes == RATE_COUNTER_SCOPES, (
        "Python RATE_COUNTER_SCOPES drifted from SQL manifest: "
        f"only_python={sorted(RATE_COUNTER_SCOPES - sql_scopes)} "
        f"only_sql={sorted(sql_scopes - RATE_COUNTER_SCOPES)}"
    )


def test_every_bump_rate_counter_scope_is_declared() -> None:
    discovered, unresolved = discover_python_scopes()
    assert unresolved == [], "Unresolved bump_rate_counter scopes:\n" + "\n".join(unresolved)
    missing = discovered - RATE_COUNTER_SCOPES
    assert missing == set(), (
        "Python bump_rate_counter/RateLimitPolicy scopes missing from RATE_COUNTER_SCOPES: "
        f"{sorted(missing)}"
    )
    assert "event_access_unlock_ip" in discovered
    assert "discovery_read_ip" in discovered
    assert "analytics_collect_ip" in discovered

"""A tiny, whitelisted expression evaluator for rule conditions.

Rule files are edited by an AI agent, so they must never be able to run
arbitrary Python. Only comparisons, boolean logic, arithmetic, attribute
access on `person` and `params`, literals and a few pure functions are allowed.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}
_FUNCS = {"min": min, "max": max, "abs": abs, "len": len}
_ROOTS = {"person", "params"}


class RuleExpressionError(ValueError):
    pass


class Namespace:
    """Attribute access over a dict, with a clear error for unknown names."""

    def __init__(self, label: str, values: dict[str, Any]):
        self._label = label
        self._values = values

    def get(self, name: str) -> Any:
        if name not in self._values:
            raise RuleExpressionError(f"unknown {self._label} field '{name}'")
        return self._values[name]


def names_used(expr: str) -> set[tuple[str, str]]:
    """Return {(root, attribute)} pairs referenced by an expression."""
    tree = _parse(expr)
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            used.add((node.value.id, node.attr))
    return used


def _parse(expr: str) -> ast.Expression:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise RuleExpressionError(f"invalid expression {expr!r}: {e.msg}") from e
    for node in ast.walk(tree):
        allowed = (
            ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub,
            ast.BinOp, ast.Compare, ast.Name, ast.Attribute, ast.Constant, ast.List,
            ast.Tuple, ast.Load, ast.Call, ast.IfExp,
            *_BIN_OPS.keys(), *_CMP_OPS.keys(),
        )
        if not isinstance(node, allowed):
            raise RuleExpressionError(f"'{type(node).__name__}' is not allowed in rule expressions")
        if isinstance(node, ast.Name) and node.id not in _ROOTS | set(_FUNCS) | {"True", "False", "None"}:
            raise RuleExpressionError(f"unknown name '{node.id}'")
        if isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id in _FUNCS) or node.keywords:
                raise RuleExpressionError("only min, max, abs and len may be called")
        if isinstance(node, ast.Attribute) and not (isinstance(node.value, ast.Name) and node.value.id in _ROOTS):
            raise RuleExpressionError("attributes are only allowed on person and params")
    return tree


def evaluate(expr: str, person: dict[str, Any], params: dict[str, Any]) -> Any:
    tree = _parse(expr)
    env = {"person": Namespace("person", person), "params": Namespace("parameter", params)}
    return _eval(tree.body, env)


def _eval(node: ast.AST, env: dict[str, Namespace]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(e, env) for e in node.elts]
    if isinstance(node, ast.Attribute):
        return env[node.value.id].get(node.attr)  # type: ignore[union-attr]
    if isinstance(node, ast.Name):
        return {"True": True, "False": False, "None": None}[node.id]
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_eval(v, env) for v in node.values)
        return any(_eval(v, env) for v in node.values)
    if isinstance(node, ast.UnaryOp):
        val = _eval(node.operand, env)
        return (not val) if isinstance(node.op, ast.Not) else -val
    if isinstance(node, ast.BinOp):
        return _BIN_OPS[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, env)
            if not _CMP_OPS[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        return _eval(node.body, env) if _eval(node.test, env) else _eval(node.orelse, env)
    if isinstance(node, ast.Call):
        return _FUNCS[node.func.id](*[_eval(a, env) for a in node.args])  # type: ignore[union-attr]
    raise RuleExpressionError(f"cannot evaluate {type(node).__name__}")

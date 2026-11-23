"""Formules des stats personnalisées : compteurs, nombres, + - * / et parenthèses.

L'analyse passe par l'arbre syntaxique Python avec une liste blanche stricte :
aucun appel de fonction, attribut ou autre construction n'est accepté.
"""

from __future__ import annotations

import ast
import operator
from functools import lru_cache

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


class FormulaError(ValueError):
    pass


@lru_cache(maxsize=512)
def compile_formula(expr: str, known: frozenset[str]) -> ast.Expression:
    expr = (expr or "").strip()
    if not expr:
        raise FormulaError("formule vide")
    if len(expr) > 300:
        raise FormulaError("formule trop longue")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise FormulaError(f"formule illisible : {expr}")
    unknown = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.USub, ast.UAdd, ast.Load)):
            continue
        if isinstance(node, tuple(_OPS)):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            continue
        if isinstance(node, ast.Name):
            if node.id not in known:
                unknown.append(node.id)
            continue
        raise FormulaError(f"élément non autorisé dans la formule : {type(node).__name__}")
    if unknown:
        raise FormulaError("compteur(s) inconnu(s) : " + ", ".join(sorted(set(unknown))))
    return tree


def _eval(node: ast.AST, values: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, values)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return float(values.get(node.id, 0.0))
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, values)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left, values), _eval(node.right, values)
        if isinstance(node.op, ast.Div) and right == 0:
            return 0.0
        return _OPS[type(node.op)](left, right)
    raise FormulaError("formule invalide")


def evaluate(expr: str, values: dict[str, float], known: frozenset[str]) -> float:
    return _eval(compile_formula(expr, known), values)

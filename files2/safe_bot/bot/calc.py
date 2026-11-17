"""آلة حاسبة آمنة: تحليل AST فقط، بلا eval، مع حدود على الحجم والأسس."""
from __future__ import annotations

import ast
import operator
import re

MAX_LEN = 80
_ALLOWED_CHARS = re.compile(r"[0-9+\-*/%().\s]+")
_BIN = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_PREP = str.maketrans({"×": "*", "÷": "/", "^": "**", "،": "", "٫": ".", "x": "*", "X": "*"})
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


class CalcError(ValueError):
    pass


def _eval(node: ast.AST, depth: int = 0):
    if depth > 20:
        raise CalcError("تعبير معقّد جدًا")
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        if abs(node.value) > 1e15:
            raise CalcError("رقم كبير جدًا")
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
        return _UN[type(node.op)](_eval(node.operand, depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left, depth + 1), _eval(node.right, depth + 1)
        if isinstance(node.op, ast.Pow) and (abs(right) > 64 or abs(left) > 1e6):
            raise CalcError("أس كبير جدًا")
        try:
            result = _BIN[type(node.op)](left, right)
        except ZeroDivisionError:
            raise CalcError("لا يمكن القسمة على صفر") from None
        except OverflowError:
            raise CalcError("الناتج كبير جدًا") from None
        if isinstance(result, complex) or abs(result) > 1e30:
            raise CalcError("ناتج غير مدعوم")
        return result
    raise CalcError("تعبير غير مسموح")


def calculate(expr: str) -> str:
    s = expr.translate(_AR_DIGITS).translate(_PREP).strip()
    if not s or len(s) > MAX_LEN or not _ALLOWED_CHARS.fullmatch(s):
        raise CalcError("اكتب عملية حسابية بسيطة مثل: 5*(3+2)")
    try:
        tree = ast.parse(s, mode="eval")
    except (SyntaxError, ValueError, RecursionError):
        raise CalcError("صيغة غير صحيحة") from None
    value = _eval(tree.body)
    if isinstance(value, float):
        value = int(value) if value.is_integer() else round(value, 10)
    return str(value)

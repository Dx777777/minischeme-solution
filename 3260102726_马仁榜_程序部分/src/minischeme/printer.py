"""打印：值 → 文本。

两种模式，对应 spec §8：
  * ``to_repr``    顶层结果和 ``display`` 之外的场合：字符串**带引号**，
                   换行/制表符打印成 ``\\n`` ``\\t`` 转义形式。
  * ``to_display`` ``display`` 专用：字符串原样输出，不带引号也不转义。

其余类型两种模式完全一样。过程统一打印成 ``#<procedure>``（spec §8 表）。
"""

from .datatypes import NIL, BuiltinProcedure, Closure, Pair, Symbol

__all__ = ["to_repr", "to_display", "escape_string"]

_PROCEDURE_TEXT = "#<procedure>"


def to_repr(value):
    """规范形式的文本表示（字符串带引号）。"""
    return _render(value, display=False)


def to_display(value):
    """display 形式的文本表示（字符串不带引号、不转义）。"""
    return _render(value, display=True)


def escape_string(text):
    """把字符串内容转成字面量里的转义写法。"""
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        else:
            out.append(ch)
    return "".join(out)


def _render(value, display):
    # 布尔必须在数字之前判断：Python 里 bool 是 int 的子类。
    if value is True:
        return "#t"
    if value is False:
        return "#f"
    if value is None:
        # 只有内置输出过程（display/newline）会返回 None，正常不会打印到。
        return ""
    if isinstance(value, Symbol):
        return value.name
    if isinstance(value, str):
        return value if display else '"' + escape_string(value) + '"'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _format_float(value)
    if value is NIL:
        return "()"
    if isinstance(value, Pair):
        return _render_pair(value, display)
    if isinstance(value, (BuiltinProcedure, Closure)):
        return _PROCEDURE_TEXT
    return str(value)          # 兜底：绝不让打印阶段抛异常


def _format_float(value):
    """浮点打印：0.5 -> "0.5"，7.0 -> "7.0"。

    Python 3 里 float 的 repr 就是最短往返表示，和 str 等价，
    这里用 repr 更明确地表达"要能读回来的字面量形式"。
    """
    return repr(value)


def _render_pair(pair, display):
    """点对链打印成 ``(1 2 3)``；尾巴不是 () 时打印成 ``(1 . 2)``。"""
    parts = []
    node = pair
    while isinstance(node, Pair):
        parts.append(_render(node.car, display))
        node = node.cdr
    if node is NIL:
        return "(" + " ".join(parts) + ")"
    # 不规范列表：(1 2 . 3)
    return "(" + " ".join(parts) + " . " + _render(node, display) + ")"

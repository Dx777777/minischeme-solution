"""内置过程（spec §5）与初始全局环境。

内置过程和特殊形式的区别：**参数先全部求值，再调用**。所以这里的每个
函数签名都是 ``fn(args: list) -> 值``，参数checking 也在这一层做。

分类：算术、比较、布尔、列表、谓词、输出。
"""

import sys

from .datatypes import (
    NIL, BuiltinProcedure, Pair,
    is_boolean, is_integer, is_list, is_null, is_number, is_pair,
    is_procedure, is_string, is_symbol, list_to_pairs,
)
from .environment import Environment
from .errors import SchemeArityError, SchemeArithmeticError, SchemeTypeError
from . import printer

__all__ = ["make_global_env", "BUILTIN_NAMES"]


# ==========================================================================
# 参数检查与共用的数值/列表工具
# ==========================================================================

def _need(name, args, count):
    """要求正好 count 个参数。"""
    if len(args) != count:
        raise SchemeArityError(
            f"{name} 需要 {count} 个参数，实际给了 {len(args)} 个"
        )


def _need_at_least(name, args, count):
    if len(args) < count:
        raise SchemeArityError(
            f"{name} 至少需要 {count} 个参数，实际给了 {len(args)} 个"
        )


def _check_number(name, value):
    if not is_number(value):
        raise SchemeTypeError(f"{name} 需要数字，但得到 {printer.to_repr(value)}")
    return value


def _check_integer(name, value):
    if not is_integer(value):
        raise SchemeTypeError(f"{name} 需要整数，但得到 {printer.to_repr(value)}")
    return value


def _check_pair(name, value):
    if not isinstance(value, Pair):
        raise SchemeTypeError(
            f"{name} 需要点对（非空列表），但得到 {printer.to_repr(value)}"
        )
    return value


def _proper_list(name, value):
    """把真列表还原成 Python 列表；否则报错。"""
    if not is_list(value):
        raise SchemeTypeError(
            f"{name} 需要一个真列表，但得到 {printer.to_repr(value)}"
        )
    items = []
    node = value
    while isinstance(node, Pair):
        items.append(node.car)
        node = node.cdr
    return items


def _truncate_divide(a, b):
    """向零截断的整除：(/ -7 2) → -3（不是 Python // 的 -4）。"""
    if b == 0:
        raise SchemeArithmeticError("除数为零")
    quotient = abs(a) // abs(b)
    return -quotient if (a < 0) != (b < 0) else quotient


# ==========================================================================
# 算术
# ==========================================================================

def _add(args):
    total = 0
    for value in args:
        total += _check_number("+", value)
    return total


def _sub(args):
    _need_at_least("-", args, 1)
    values = [_check_number("-", v) for v in args]
    if len(values) == 1:
        return -values[0]
    result = values[0]
    for value in values[1:]:
        result -= value
    return result


def _mul(args):
    total = 1
    for value in args:
        total *= _check_number("*", value)
    return total


def _div(args):
    """(/ a b ...)：整数相除得整数商；单参数取倒数是浮点（spec §5）。"""
    _need_at_least("/", args, 1)
    values = [_check_number("/", v) for v in args]

    if len(values) == 1:
        divisor = values[0]
        if divisor == 0:
            raise SchemeArithmeticError("除数为零")
        return 1 / divisor                    # 一定是浮点：(/ 2) → 0.5

    result = values[0]
    for divisor in values[1:]:
        if divisor == 0:
            raise SchemeArithmeticError("除数为零")
        if is_integer(result) and is_integer(divisor):
            result = _truncate_divide(result, divisor)
        else:
            result = result / divisor
    return result


def _modulo(args):
    _need("modulo", args, 2)
    a = _check_number("modulo", args[0])
    b = _check_number("modulo", args[1])
    if b == 0:
        raise SchemeArithmeticError("modulo 的除数为零")
    if is_integer(a) and is_integer(b):
        return a % b                          # Python % 取模符号跟随除数，与 Scheme 一致
    return a % b


def _quotient(args):
    _need("quotient", args, 2)
    a = _check_number("quotient", args[0])
    b = _check_number("quotient", args[1])
    if is_integer(a) and is_integer(b):
        return _truncate_divide(a, b)
    if b == 0:
        raise SchemeArithmeticError("quotient 的除数为零")
    quotient = abs(a) / abs(b)
    quotient = int(quotient)
    return -quotient if (a < 0) != (b < 0) else quotient


def _expt(args):
    _need("expt", args, 2)
    base = _check_number("expt", args[0])
    power = _check_number("expt", args[1])
    if base == 0 and power < 0:
        raise SchemeArithmeticError("expt 的底数为零且指数为负")
    return base ** power


def _abs(args):
    _need("abs", args, 1)
    return abs(_check_number("abs", args[0]))


# ==========================================================================
# 比较（链式：相邻两两都成立才为真）
# ==========================================================================

def _chain(name, args, ok):
    """通用链式比较：(< 2 3 4) → 2<3 且 3<4。

    spec §5 说明比较"支持数字与符号"：同类型才比较，数字按数值、
    符号按名字、字符串按内容；0/1 个参数恒为真。
    """
    if len(args) < 2:
        return True
    for left, right in zip(args, args[1:]):
        if not _comparable(name, left, right):
            raise SchemeTypeError(
                f"{name} 不支持比较 {printer.to_repr(left)} 与 "
                f"{printer.to_repr(right)}"
            )
        if not ok(left, right):
            return False
    return True


def _comparable(name, left, right):
    """两个值是否是同类可比较的值（数字/符号/字符串）。"""
    if is_symbol(left) and is_symbol(right):
        return True
    if is_string(left) and is_string(right):
        return True
    return is_number(left) and is_number(right)


def _comparison_value(value):
    """比较时用的键：符号取名字，字符串取内容，数字取自身。"""
    if is_symbol(value):
        return value.name
    return value


def _eq(args):
    """(= a b ...)：同类才比；不同类型直接判假（(equal? #t 1) 的坑）。"""
    if len(args) < 2:
        return True
    for left, right in zip(args, args[1:]):
        if _comparable("=", left, right):
            if _comparison_value(left) != _comparison_value(right):
                return False
        elif not equal_values(left, right):
            return False
    return True


def _lt(args):
    return _chain("<", args, lambda a, b: _comparison_value(a) < _comparison_value(b))


def _gt(args):
    return _chain(">", args, lambda a, b: _comparison_value(a) > _comparison_value(b))


def _le(args):
    return _chain("<=", args, lambda a, b: _comparison_value(a) <= _comparison_value(b))


def _ge(args):
    return _chain(">=", args, lambda a, b: _comparison_value(a) >= _comparison_value(b))


# ==========================================================================
# 布尔
# ==========================================================================

def _not(args):
    _need("not", args, 1)
    return args[0] is False


# ==========================================================================
# 列表
# ==========================================================================

def _cons(args):
    _need("cons", args, 2)
    return Pair(args[0], args[1])


def _car(args):
    _need("car", args, 1)
    return _check_pair("car", args[0]).car


def _cdr(args):
    _need("cdr", args, 1)
    return _check_pair("cdr", args[0]).cdr


def _list(args):
    return list_to_pairs(args)


def _length(args):
    _need("length", args, 1)
    return len(_proper_list("length", args[0]))


def _append(args):
    """(append l1 l2 ...)：除最后一个参数外都必须是真列表。"""
    if not args:
        return NIL
    result = args[-1]
    for value in reversed(args[:-1]):
        items = _proper_list("append", value)
        for item in reversed(items):
            result = Pair(item, result)
    return result


# ==========================================================================
# 谓词
# ==========================================================================

def _null_p(args):
    _need("null?", args, 1)
    return is_null(args[0])


def _pair_p(args):
    _need("pair?", args, 1)
    return is_pair(args[0])


def _list_p(args):
    _need("list?", args, 1)
    return is_list(args[0])


def _number_p(args):
    _need("number?", args, 1)
    return is_number(args[0])


def _boolean_p(args):
    _need("boolean?", args, 1)
    return is_boolean(args[0])


def _symbol_p(args):
    _need("symbol?", args, 1)
    return is_symbol(args[0])


def _string_p(args):
    _need("string?", args, 1)
    return is_string(args[0])


def _procedure_p(args):
    _need("procedure?", args, 1)
    return is_procedure(args[0])


def _zero_p(args):
    _need("zero?", args, 1)
    return _check_number("zero?", args[0]) == 0


def _even_p(args):
    _need("even?", args, 1)
    return _check_integer("even?", args[0]) % 2 == 0


def _odd_p(args):
    _need("odd?", args, 1)
    return _check_integer("odd?", args[0]) % 2 != 0


def _eq_p(args):
    """eq?：符号/数字/布尔/字符串按值；列表等复合数据按同一性（spec §5）。"""
    _need("eq?", args, 2)
    return is_identical(args[0], args[1])


def is_identical(left, right):
    if left is right:                 # 同一对象（含 NIL 单例）一定相等
        return True
    if is_symbol(left) and is_symbol(right):
        return left.name == right.name
    if is_boolean(left) or is_boolean(right):
        return left is right          # 布尔只与自己同一
    if is_number(left) and is_number(right):
        return left == right
    if is_string(left) and is_string(right):
        return left == right
    return False                      # 两个不同的点对/闭包 → #f


def _equal_p(args):
    """equal?：结构相等，逐层比较。"""
    _need("equal?", args, 2)
    return equal_values(args[0], args[1])


def equal_values(left, right):
    """结构相等。**先比类型再比值**，避免 Python 的 True == 1。"""
    if left is right:
        return True
    if is_boolean(left) or is_boolean(right):
        return left is right
    if is_number(left) and is_number(right):
        return left == right
    if is_symbol(left) and is_symbol(right):
        return left.name == right.name
    if is_string(left) and is_string(right):
        return left == right
    if is_null(left) and is_null(right):
        return True
    if isinstance(left, Pair) and isinstance(right, Pair):
        return equal_values(left.car, right.car) and equal_values(left.cdr, right.cdr)
    return False


# ==========================================================================
# 输出
# ==========================================================================

def _display(args):
    """打印一个值（字符串不带引号），不换行；结果是 None，不打印（spec §2）。"""
    _need("display", args, 1)
    sys.stdout.write(printer.to_display(args[0]))
    return None


def _newline(args):
    _need("newline", args, 0)
    sys.stdout.write("\n")
    return None


# ==========================================================================
# 组装初始环境
# ==========================================================================

_BUILTINS = (
    # 算术
    ("+", _add),
    ("-", _sub),
    ("*", _mul),
    ("/", _div),
    ("modulo", _modulo),
    ("quotient", _quotient),
    ("expt", _expt),
    ("abs", _abs),
    # 比较
    ("=", _eq),
    ("<", _lt),
    (">", _gt),
    ("<=", _le),
    (">=", _ge),
    # 布尔
    ("not", _not),
    # 列表
    ("cons", _cons),
    ("car", _car),
    ("cdr", _cdr),
    ("list", _list),
    ("length", _length),
    ("append", _append),
    # 列表谓词
    ("null?", _null_p),
    ("pair?", _pair_p),
    ("list?", _list_p),
    # 类型谓词
    ("number?", _number_p),
    ("boolean?", _boolean_p),
    ("symbol?", _symbol_p),
    ("string?", _string_p),
    ("procedure?", _procedure_p),
    ("zero?", _zero_p),
    ("even?", _even_p),
    ("odd?", _odd_p),
    ("eq?", _eq_p),
    ("equal?", _equal_p),
    # 输出
    ("display", _display),
    ("newline", _newline),
)

BUILTIN_NAMES = tuple(name for name, _ in _BUILTINS)


def make_global_env():
    """按 spec §2："初始环境为空"，只有这里的标准内置过程和常量。"""
    env = Environment()
    for name, function in _BUILTINS:
        env.define(name, BuiltinProcedure(name, function))
    return env

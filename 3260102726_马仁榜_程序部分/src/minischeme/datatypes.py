"""mini-Scheme 的值类型，以及一组类型判定工具。

设计要点（都是 spec 里点名的坑）：

* ``Symbol`` **不是** ``str`` 的子类。如果用 str 表示符号，
  ``(equal? 'a "a")`` 和 ``(eq? 'a "a")`` 都会错误地判真（spec §11）。
* ``NIL`` 是空表的单例对象。这保证 ``(eq? '() '())`` 判真
  （同一性比较），而两个分别构造的 ``(1)`` 是不同对象，判假（spec §5）。
* ``Pair`` 不定义 ``__eq__``，因此 ``==`` 就是同一性比较，
  正好是 ``eq?`` 对复合数据要的语义；结构比较交给 ``equal?`` 单独实现。
* 布尔是 Python 的 bool，而 bool 是 int 的子类，所以判定"是数字"时必须
  显式排除布尔（``(equal? #t 1)`` 的坑）。
"""

from .errors import SchemeError

__all__ = [
    "Symbol", "Nil", "NIL", "Pair", "BuiltinProcedure", "Closure",
    "is_true", "is_number", "is_integer", "is_boolean", "is_symbol",
    "is_string", "is_null", "is_pair", "is_procedure", "is_list",
    "list_to_pairs", "pair_to_list", "iter_pairs",
]


class Symbol:
    """符号：表示"名字"。按名字比较，可作字典键。"""

    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return isinstance(other, Symbol) and other.name == self.name

    def __hash__(self):
        return hash(("mini-scheme-symbol", self.name))

    def __repr__(self):
        return f"Symbol({self.name!r})"


class Nil:
    """空表 ``()`` 的类型。全解释器只应该存在一个实例：``NIL``。"""

    __slots__ = ()

    def __repr__(self):
        return "NIL"


NIL = Nil()


class Pair:
    """点对（cons cell）：列表就是一串点对。"""

    __slots__ = ("car", "cdr")

    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

    def __repr__(self):
        return f"Pair({self.car!r}, {self.cdr!r})"


class BuiltinProcedure:
    """内置过程：一个 Python 可调用对象 + 名字（只为报错信息）。"""

    __slots__ = ("name", "fn")

    def __init__(self, name, fn):
        self.name = name
        self.fn = fn

    def __repr__(self):
        return f"#<procedure {self.name}>"


class Closure:
    """用户函数（lambda）：参数名表 + 函数体 + **定义时**的环境。

    保存定义时的环境就是词法作用域（闭包）的全部秘密（spec §9）。
    """

    __slots__ = ("params", "body", "env", "name")

    def __init__(self, params, body, env, name=None):
        self.params = params          # list[str]
        self.body = body              # list[表达式]
        self.env = env                # 定义时的 Environment
        self.name = name              # define 简写时记下名字，便于调试

    def __repr__(self):
        return f"#<procedure {self.name}>" if self.name else "#<procedure>"


# --------------------------------------------------------------------------
# 类型判定：全解释器统一从这里取，避免各处 isinstance 写法不一致。
# --------------------------------------------------------------------------

def is_true(value):
    """mini-Scheme 的"真"：**只有 #f 是假**，0、()、"" 都是真（spec §4.4）。"""
    return value is not False


def is_number(value):
    """是数字吗。注意排除 bool：Python 里 True == 1。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_integer(value):
    """是整数吗（同样排除 bool）。"""
    return isinstance(value, int) and not isinstance(value, bool)


def is_boolean(value):
    return isinstance(value, bool)


def is_symbol(value):
    return isinstance(value, Symbol)


def is_string(value):
    return isinstance(value, str)


def is_null(value):
    return value is NIL


def is_pair(value):
    return isinstance(value, Pair)


def is_procedure(value):
    return isinstance(value, (BuiltinProcedure, Closure))


# --------------------------------------------------------------------------
# 点对链与 Python 列表之间的转换
# --------------------------------------------------------------------------

def list_to_pairs(items, tail=NIL):
    """把 Python 列表变成点对链，tail 是链尾（默认空表）。"""
    node = tail
    for item in reversed(items):
        node = Pair(item, node)
    return node


def iter_pairs(value, who="列表操作"):
    """惰性遍历点对链的前半部分，遇到非点对的尾巴就报错。

    用于只关心元素、后续自己会检查尾巴的场景。
    """
    node = value
    while isinstance(node, Pair):
        yield node.car
        node = node.cdr
    if node is not NIL:
        raise SchemeError(f"{who}：期望真列表，但遇到不规范的尾部（点对链未以 () 结束）")


def pair_to_list(value, who="列表操作"):
    """把真列表转成 Python 列表；不是真列表就报错。"""
    return list(iter_pairs(value, who))


def is_list(value):
    """是否"真列表"：() 或者一串以 () 结尾的点对（spec §5 的 list?）。"""
    node = value
    while isinstance(node, Pair):
        node = node.cdr
    return node is NIL

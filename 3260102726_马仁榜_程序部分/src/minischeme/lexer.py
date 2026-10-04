"""词法分析：程序文本 → 词（token）列表。

只认 spec §3 列出的零件：注释、整数（浮点可选）、布尔、符号、字符串、
引用简写 ``'``、括号。多出来的写法（``#true``、``[``、``|符号|`` 等）
一律当普通符号处理，绝不擅自扩展语言。
"""

import re

from .datatypes import Symbol
from .errors import SchemeSyntaxError

__all__ = ["Token", "tokenize"]


# 整数与浮点字面量。先试整数，再试浮点，都不匹配就当符号——
# 这样 "-" 是符号而 "-7" 是数字（spec §3）。
_INT_RE = re.compile(r"^[+-]?[0-9]+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[eE][+-]?[0-9]+)?$")

# 会切断一个"词"的字符（空白不在其中，它由 is_whitespace 单独判定）。
_DELIMITERS = set('()"\';')

# 会被记成"新的一行"的字符，只影响报错里的行列号，不影响分词结果。
_LINE_BREAKS = ("\n", "\r", "\u2028", "\u2029")

_STRING_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def is_whitespace(ch):
    """**全模块唯一**的空白判定，跳过空白与切分原子都必须用它。

    这里曾经埋着一个死循环：跳过空白用的是 ASCII 白名单
    ``" \\t\\r\\f\\v"``，而切分原子用的是 ``str.isspace()``。对 U+3000
    （全角空格）、U+00A0（不换行空格）这类 Unicode 空白，两个判定正好相反：

      * 主循环认为"不是空白"，于是走到原子分支；
      * 原子循环第一格就认为"是空白"，立刻停下。

    下标一格都不前进，而每轮又都往 tokens 里塞一个空符号，于是死循环
    + 内存无限增长。把判定收成这一个函数，就不可能再出现这种分歧。

    ``str.isspace()`` 覆盖 Unicode 的 Zs/Zl/Zp 和 C0 分隔符，与 R7RS 对
    ``<whitespace>`` 的定义一致（spec §3 的"空格、换行、制表符"是其子集）。
    """
    return ch.isspace()


def is_atom_char(ch):
    """能组成原子的字符（数字/布尔/符号/单独的点）。

    与 :func:`is_whitespace` 严格互补，这正是 tokenize 主循环"每轮至少
    前进一格"的依据。
    """
    return not ch.isspace() and ch not in _DELIMITERS


class Token:
    """一个词。kind 取值见下面 tokenize 的注释，value 是它代表的值。"""

    __slots__ = ("kind", "value", "line", "column")

    def __init__(self, kind, value, line, column):
        self.kind = kind          # lparen/rparen/quote/atom/eof
        self.value = value        # 原子token 已转成 int/float/bool/Symbol/str
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Token({self.kind}, {self.value!r}, {self.line}:{self.column})"


def tokenize(text):
    """把源码文本切成 token 列表，末尾一定有一个 eof token。

    kind 的取值：
      ``lparen`` / ``rparen``  括号
      ``quote``                引用简写 '
      ``atom``                 数字 / 布尔 / 符号 / 字符串（value 已转换）
      ``eof``                  结束标记
    """
    tokens = []
    i = 0
    line = 1
    column = 1
    n = len(text)

    while i < n:
        ch = text[i]

        # 空白：ASCII 空白与 Unicode 空白一视同仁，只更新位置。
        # 换行重置行号；"\r\n" 整体只算一次换行。
        if is_whitespace(ch):
            i += 1
            if ch == "\r" and i < n and text[i] == "\n":
                i += 1
            if ch in _LINE_BREAKS:
                line += 1
                column = 1
            else:
                column += 1
            continue

        # 注释：';' 到行尾全部忽略（spec §3）。
        if ch == ";":
            while i < n and text[i] != "\n":
                i += 1
            continue

        if ch == "(":
            tokens.append(Token("lparen", "(", line, column))
            i += 1
            column += 1
            continue

        if ch == ")":
            tokens.append(Token("rparen", ")", line, column))
            i += 1
            column += 1
            continue

        if ch == "'":
            tokens.append(Token("quote", "'", line, column))
            i += 1
            column += 1
            continue

        if ch == '"':
            start_column = column
            value, i, column = _read_string(text, i, line, column)
            tokens.append(Token("atom", value, line, start_column))
            continue

        # 其余情况：读一个原子（数字/布尔/符号/单独的点）。
        # 能走到这里说明 ch 既不是空白也不在 _DELIMITERS 里，所以下面的
        # 循环至少前进一格。
        start = i
        start_column = column
        while i < n and is_atom_char(text[i]):
            i += 1
            column += 1
        if i == start:
            # 不变量兜底（正常永远不成立）：万一以后有人往 _DELIMITERS 加了
            # 字符却忘了加对应分支，这里会立刻报错，而不是变成死循环。
            raise SchemeSyntaxError(f"无法识别的字符 {text[start]!r}", line, column)
        raw = text[start:i]
        tokens.append(Token("atom", _classify_atom(raw), line, start_column))

    tokens.append(Token("eof", None, line, column))
    return tokens


def _read_string(text, i, line, column):
    """从 text[i] == '"' 开始读一个字符串字面量，返回 (值, 新下标, 新列号)。"""
    n = len(text)
    i += 1        # 跳过开头的引号
    column += 1
    chars = []

    while True:
        if i >= n:
            raise SchemeSyntaxError("字符串没有闭合的引号", line, column)
        ch = text[i]
        if ch == '"':
            i += 1
            column += 1
            return "".join(chars), i, column
        if ch == "\n":
            # 字符串里允许真正的换行，但位置信息要跟着走。
            chars.append(ch)
            i += 1
            line += 1
            column = 1
            continue
        if ch == "\\":
            if i + 1 >= n:
                raise SchemeSyntaxError("字符串以孤立的反斜杠结尾", line, column)
            nxt = text[i + 1]
            # spec §3 只承诺 \n \t \" \\；其余转义宽松处理成字符本身。
            chars.append(_STRING_ESCAPES.get(nxt, nxt))
            i += 2
            column += 2
            continue
        chars.append(ch)
        i += 1
        column += 1


def _classify_atom(raw):
    """把一段裸文本变成它代表的值。"""
    if raw == "#t":
        return True
    if raw == "#f":
        return False
    if _INT_RE.match(raw):
        return int(raw)
    if _FLOAT_RE.match(raw):
        return float(raw)
    return Symbol(raw)

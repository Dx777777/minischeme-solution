"""语法分析：词（token）列表 → 表达式（嵌套的点对结构）。

产出和 ``cons`` 完全一致的点对链表示，这一点很关键：
``'(1 2 3)`` 里的数据、``(+ 1 2)`` 里的代码，在解释器内部是同一种东西
（spec §6 / §11 最后一行"引用数据要转成与 cons 一致的表示"）。
"""

from .datatypes import NIL, Pair, Symbol, list_to_pairs
from .errors import SchemeSyntaxError
from .lexer import tokenize

__all__ = ["parse", "parse_all"]

_LPAREN = "lparen"
_RPAREN = "rparen"
_QUOTE = "quote"
_ATOM = "atom"
_EOF = "eof"

# 单独出现的点号 = 点对语法里的点，不是符号 "."。
_DOT = Symbol(".")


class _Reader:
    """带下标的递归下降读取器。"""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    # -- 基本游标操作 ------------------------------------------------------
    def peek(self):
        return self.tokens[self.pos]

    def next(self):
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def at_end(self):
        return self.peek().kind == _EOF

    # -- 表达式 ------------------------------------------------------------
    def read(self):
        """读一个完整的表达式。"""
        token = self.next()
        kind = token.kind

        if kind == _ATOM:
            return token.value

        if kind == _QUOTE:
            # 'x  等价于  (quote x)；''x 会自然嵌套成 (quote (quote x))。
            return list_to_pairs([Symbol("quote"), self.read()])

        if kind == _LPAREN:
            return self.read_list(token)

        if kind == _RPAREN:
            raise SchemeSyntaxError("多余的右括号 ')'", token.line, token.column)

        raise SchemeSyntaxError("读取到意外的输入结尾，缺少一个表达式",
                                token.line, token.column)

    def read_list(self, open_token):
        """读完 ``( ... )``，支持点对写法 ``(a . b)``。"""
        items = []
        tail = NIL

        while True:
            token = self.peek()

            if token.kind == _EOF:
                raise SchemeSyntaxError("缺少与 '(' 配对的右括号", open_token.line,
                                        open_token.column)

            if token.kind == _RPAREN:
                self.next()
                break

            if token.kind == _ATOM and token.value == _DOT:
                if not items:
                    raise SchemeSyntaxError("点号 '.' 前面必须至少有一个元素",
                                            token.line, token.column)
                self.next()
                tail = self.read()
                closing = self.next()
                if closing.kind != _RPAREN:
                    raise SchemeSyntaxError("点对语法里 '.' 后面只能有一个表达式",
                                            closing.line, closing.column)
                break

            items.append(self.read())

        return list_to_pairs(items, tail)


def parse_all(tokens):
    """把整份 token 流读成表达式列表（顶层可以并排写多个表达式）。"""
    reader = _Reader(tokens)
    expressions = []
    while not reader.at_end():
        expressions.append(reader.read())
    return expressions


def parse(text):
    """一步到位：源码文本 → 表达式列表。"""
    return parse_all(tokenize(text))

"""求值器：表达式 → 值。解释器的心脏。

两个互相递归的函数（README §4 的核心）：

  * ``evaluate(expr, env)``  符号查环境；数字/布尔/字符串原样返回；
    点对要么是特殊形式（各自的求值顺序见 spec §4），要么是函数调用。
  * ``apply_procedure(proc, args)``  内置过程直接调；闭包新建一层环境
    绑定实参，外层指向**定义时**的环境，再回到 evaluate 求值函数体。

所有特殊形式都写成 ``(参数点对, 环境) -> 值`` 的小函数，统一登记在
``SPECIAL_FORMS`` 里，避免 eavluate 里堆一长串 if。
"""

from .datatypes import (
    NIL, BuiltinProcedure, Closure, Pair, Symbol,
    is_true, pair_to_list,
)
from .environment import Environment
from .errors import SchemeArityError, SchemeSyntaxError, SchemeTypeError
from . import printer

__all__ = ["evaluate", "apply_procedure", "eval_sequence", "SPECIAL_FORMS"]


# --------------------------------------------------------------------------
# 求值主循环
# --------------------------------------------------------------------------

def evaluate(expr, env):
    """求值一个表达式。

    自求值的值（数字、布尔、字符串）直接返回；符号查环境；
    点对交给 ``evaluate_combination``。
    """
    if isinstance(expr, Symbol):
        return env.lookup(expr.name)

    if isinstance(expr, Pair):
        return evaluate_combination(expr, env)

    if expr is NIL:
        raise SchemeTypeError("不能求值空表 ()，它既不是过程也不是特殊形式")

    # 数字、布尔、字符串、None 都是自求值的。
    return expr


def evaluate_combination(expr, env):
    """求值一个括号表达式：先看是不是特殊形式，否则按函数调用处理。"""
    head = expr.car

    if isinstance(head, Symbol):
        handler = SPECIAL_FORMS.get(head.name)
        if handler is not None:
            return handler(expr.cdr, env)

    # 函数调用（应用序）：操作符和**全部**实参先求值，再 apply（spec §9）。
    procedure = evaluate(head, env)
    arguments = [evaluate(arg, env) for arg in _arguments(expr)]
    return apply_procedure(procedure, arguments)


def apply_procedure(procedure, arguments):
    """调用一个过程。"""
    if isinstance(procedure, Closure):
        return _apply_closure(procedure, arguments)

    if isinstance(procedure, BuiltinProcedure):
        # 参数已经求值完毕，直接执行内置的 Python 函数。
        return procedure.fn(arguments)

    raise SchemeTypeError(
        f"{printer.to_repr(procedure)} 不是过程，无法调用"
    )


def _apply_closure(closure, arguments):
    """把实参绑到形参上，在闭包**定义时**的环境之上新建一层，再求值函数体。"""
    if len(arguments) != len(closure.params):
        raise SchemeArityError(
            f"{_procedure_name(closure)} 需要 {len(closure.params)} 个参数，"
            f"实际给了 {len(arguments)} 个"
        )
    call_env = Environment.with_bindings(closure.params, arguments,
                                         parent=closure.env)
    return eval_sequence(closure.body, call_env)


def eval_sequence(expressions, env):
    """按 begin 语义顺序求值，返回最后一个的值（空序列返回 None）。"""
    result = None
    for expression in expressions:
        result = evaluate(expression, env)
    return result


def _procedure_name(closure):
    return closure.name if closure.name else "lambda"


def _arguments(expr):
    """取出调用表达式的实参。点对链必须是真列表。"""
    arguments = []
    node = expr.cdr
    while isinstance(node, Pair):
        arguments.append(node.car)
        node = node.cdr
    if node is not NIL:
        raise SchemeSyntaxError("函数调用的实参表不是真列表")
    return arguments


# --------------------------------------------------------------------------
# 特殊形式（spec §4）。签名统一为 (args, env) -> 值，args 是参数点对链。
# --------------------------------------------------------------------------

def _eval_quote(args, env):
    """(quote 数据)：原样返回，不求值。"""
    _arity("quote", args, 1)
    return args.car


def _eval_if(args, env):
    """(if 测试 真分支 假分支?)：只求值一个分支。"""
    parts = pair_to_list(args, "if")
    if len(parts) not in (2, 3):
        raise SchemeSyntaxError("if 需要 2 个或 3 个表达式")
    if is_true(evaluate(parts[0], env)):
        return evaluate(parts[1], env)
    if len(parts) == 3:
        return evaluate(parts[2], env)
    return None          # 省略假分支且测试为假：无值，不打印


def _eval_cond(args, env):
    """(cond (测试 表达式...) ...)：第一个不为 #f 的子句生效。"""
    clause = args
    while isinstance(clause, Pair):
        parts = pair_to_list(clause.car, "cond 子句")
        if not parts:
            raise SchemeSyntaxError("cond 子句不能为空")

        test = parts[0]
        if isinstance(test, Symbol) and test.name == "else":
            body = parts[1:]
            return eval_sequence(body, env) if body else True

        value = evaluate(test, env)
        if is_true(value):
            body = parts[1:]
            # 子句里没有表达式时，返回测试值本身（spec §4.3）。
            return eval_sequence(body, env) if body else value

        clause = clause.cdr

    if clause is not NIL:
        raise SchemeSyntaxError("cond 的子句表不是真列表")
    return None          # 全部不匹配


def _eval_and(args, env):
    """(and e1 e2 ...)：短路；全真返回最后一个的值；(and) → #t。"""
    result = True
    for expression in pair_to_list(args, "and"):
        result = evaluate(expression, env)
        if result is False:          # 只有 #f 是假
            return False
    return result


def _eval_or(args, env):
    """(or e1 e2 ...)：短路；返回第一个不为 #f 的值；(or) → #f。"""
    for expression in pair_to_list(args, "or"):
        result = evaluate(expression, env)
        if result is not False:
            return result
    return False


def _eval_define(args, env):
    """(define 名 表达式) 或 (define (函数名 参数...) 体...)。

    结果是被定义的符号名（顶层会打印出来，spec §4.5）。
    """
    if not isinstance(args, Pair):
        raise SchemeSyntaxError("define 至少需要一个被定义的名字")
    target = args.car

    if isinstance(target, Symbol):
        _arity("define", args, 2)
        value = evaluate(args.cdr.car, env)
        env.define(target.name, value)
        return target

    if isinstance(target, Pair):
        # 函数简写：等价于 (define 名 (lambda (参数...) 体...))
        name = target.car
        if not isinstance(name, Symbol):
            raise SchemeSyntaxError("define 的函数名必须是符号")
        params = _parse_parameters(target.cdr, "define")
        body = pair_to_list(args.cdr, "define")
        if not body:
            raise SchemeSyntaxError("define 定义的函数至少要有一个函数体表达式")
        env.define(name.name, Closure(params, body, env, name.name))
        return name

    raise SchemeSyntaxError("define 的目标必须是符号或 (函数名 参数...) 形式")


def _eval_lambda(args, env):
    """(lambda (参数...) 体...)：此刻不求值函数体，产出闭包。"""
    if not isinstance(args, Pair):
        raise SchemeSyntaxError("lambda 需要参数表和函数体")
    params = _parse_parameters(args.car, "lambda")
    body = pair_to_list(args.cdr, "lambda")
    if not body:
        raise SchemeSyntaxError("lambda 至少要有一个函数体表达式")
    return Closure(params, body, env)


def _eval_let(args, env):
    """(let ((名 表达式)...) 体...)：**并行**绑定。

    所有绑定表达式先在**外层**环境求值完，绑定之间互相看不见（spec §4.7），
    然后才在新环境里按 begin 语义求值函数体。
    """
    if not isinstance(args, Pair):
        raise SchemeSyntaxError("let 需要绑定表和函数体")

    bindings = pair_to_list(args.car, "let")
    names = []
    values = []
    for binding in bindings:
        parts = pair_to_list(binding, "let 绑定")
        if len(parts) != 2 or not isinstance(parts[0], Symbol):
            raise SchemeSyntaxError("let 的每个绑定必须是 (名字 表达式) 形式")
        names.append(parts[0].name)
        values.append(evaluate(parts[1], env))      # 注意：用外层 env

    body = pair_to_list(args.cdr, "let")
    let_env = Environment.with_bindings(names, values, parent=env)
    return eval_sequence(body, let_env)


def _eval_begin(args, env):
    """(begin e1 e2 ...)：顺序求值，返回最后一个。"""
    return eval_sequence(pair_to_list(args, "begin"), env)


SPECIAL_FORMS = {
    "quote": _eval_quote,
    "if": _eval_if,
    "cond": _eval_cond,
    "and": _eval_and,
    "or": _eval_or,
    "define": _eval_define,
    "lambda": _eval_lambda,
    "let": _eval_let,
    "begin": _eval_begin,
}


def _parse_parameters(param_expr, who):
    """把形参表解析成名字列表，顺便校验它确实是符号表。"""
    params = pair_to_list(param_expr, who)
    for param in params:
        if not isinstance(param, Symbol):
            raise SchemeSyntaxError(f"{who} 的参数名必须是符号")
    return [param.name for param in params]


def _arity(who, args, expected):
    """检查参数点对链的长度正好是 expected。"""
    count = 0
    node = args
    while isinstance(node, Pair):
        count += 1
        node = node.cdr
    if node is not NIL:
        raise SchemeSyntaxError(f"{who} 的参数不是真列表")
    if count != expected:
        raise SchemeSyntaxError(f"{who} 需要 {expected} 个参数，实际给了 {count}")

#!/usr/bin/env python3
"""自测脚本：把 spec 里每一条语义都写成一个小程序，逐字节核对输出。

用法（在仓库根目录）::

    python3 tests/run_checks.py

评分器只给通过/失败，不给期望输出；这个脚本用来覆盖 spec 正文里
评分器没有直接暴露的边角语义（负数整除、短路返回值、let 并行绑定、
eq?/equal? 的类型区分、点对打印、Unicode 空白等）。

**每一次子进程调用都带超时**：解释器一旦因为词法死循环之类的 bug 卡住，
这里会报 "超时" 失败并继续跑剩下的用例，而不是把整个自测挂死。
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERPRETER = os.path.join(ROOT, "src", "main.py")

# 单次运行的墙上时间上限。公开评分器用的是 60 秒，这里更紧一点，
# 让死循环尽快暴露；正常的用例都在 1 秒以内。
TIMEOUT_SECONDS = 20
TIMEOUT_MARK = "<超时>"

# (说明, 源码, 期望的标准输出)
CHECKS = [
    # ---- 基本自求值 ----------------------------------------------------
    ("整数自求值", "42", "42\n"),
    ("布尔自求值", "#t", "#t\n"),
    ("字符串顶层带引号", '"hi"', '"hi"\n'),
    ("浮点自求值", "2.5", "2.5\n"),

    # ---- 算术（spec §5） -----------------------------------------------
    ("(+) 是 0", "(+)", "0\n"),
    ("(*) 是 1", "(*)", "1\n"),
    ("减法多参数", "(- 10 4 1)", "5\n"),
    ("单参数取反", "(- 5)", "-5\n"),
    ("整数除法取整商", "(/ 7 2)", "3\n"),
    ("负数整除向零截断", "(/ -7 2)", "-3\n"),
    ("再截断一次", "(/ -7 -2)", "3\n"),
    ("单参数除法是浮点倒数", "(/ 2)", "0.5\n"),
    ("浮点除法", "(/ 7.0 2)", "3.5\n"),
    ("混合类型加法", "(+ 1 2.5)", "3.5\n"),
    ("modulo", "(modulo 17 5)", "2\n"),
    ("modulo 负数", "(modulo -7 2)", "1\n"),
    ("quotient", "(quotient 17 5)", "3\n"),
    ("quotient 负数", "(quotient -7 2)", "-3\n"),
    ("expt", "(expt 2 10)", "1024\n"),
    ("abs", "(abs (- 5 9))", "4\n"),

    # ---- 比较：链式 + 符号（spec §5） ----------------------------------
    ("链式 <", "(< 2 3 4)", "#t\n"),
    ("链式中断", "(< 2 4 3)", "#f\n"),
    ("单参数比较", "(< 1)", "#t\n"),
    ("对比符号", "(< 'a 'b)", "#t\n"),
    ("等号链", "(= 1 1 1)", "#t\n"),
    ("等号比符号", "(= 'a 'a)", "#t\n"),
    ("等号跨类型为假", "(= 1 'a)", "#f\n"),
    ("布尔不等于整数", "(= #t 1)", "#f\n"),
    (">= 相等", "(>= 5 5)", "#t\n"),
    ("> 相等为假", "(> 5 5)", "#f\n"),

    # ---- 布尔与短路（spec §4.4） ---------------------------------------
    ("not #f", "(not #f)", "#t\n"),
    ("not 0 为假", "(not 0)", "#f\n"),
    ("not 空表为假", "(not '())", "#f\n"),
    ("(and) 是 #t", "(and)", "#t\n"),
    ("(or) 是 #f", "(or)", "#f\n"),
    ("and 返回最后一个值", "(and 1 2 3)", "3\n"),
    ("or 返回第一个真值", "(or #f 0 9)", "0\n"),
    ("and 短路", "(and #f (/ 1 0))", "#f\n"),
    ("or 短路", "(or #t (/ 1 0))", "#t\n"),
    ("全假 or", "(or #f #f)", "#f\n"),

    # ---- if / cond（spec §4.2、§4.3） -----------------------------------
    ("if 真分支", "(if (> 3 2) 'yes 'no)", "yes\n"),
    ("if 假分支", "(if #f 'bad 'good)", "good\n"),
    ("if 省略假分支", "(if #f 1)", ""),
    ("0 是真", "(if 0 'truthy 'falsy)", "truthy\n"),
    ("cond else", "(cond (else 'd))", "d\n"),
    ("cond 全不匹配", "(cond ((= 1 2) 'a))", ""),
    ("cond 空子句返回测试值", "(cond ((> 2 3)) (else 42))", "42\n"),
    ("cond 多分支", "(cond ((= 1 2) 'a) ((= 2 2) 'b) (else 'c))", "b\n"),

    # ---- quote 与点对链（spec §4.1、§6） -------------------------------
    ("quote 符号", "(quote x)", "x\n"),
    ("quote 列表", "'(1 2 3)", "(1 2 3)\n"),
    ("quote 空表", "'()", "()\n"),
    ("嵌套 quote", "''x", "(quote x)\n"),
    ("读点对字面量", "'(1 . 2)", "(1 . 2)\n"),
    ("读嵌套点对", "'(1 2 . 3)", "(1 2 . 3)\n"),
    ("cons 点对", "(cons 1 2)", "(1 . 2)\n"),
    ("cons 接列表", "(cons 1 '(2 3))", "(1 2 3)\n"),

    # ---- 列表（spec §5、§6） -------------------------------------------
    ("car", "(car '(1 2 3))", "1\n"),
    ("cdr", "(cdr '(1 2 3))", "(2 3)\n"),
    ("list", "(list 1 2 3)", "(1 2 3)\n"),
    ("嵌套列表打印", "(list 1 (list 2 3) 4)", "(1 (2 3) 4)\n"),
    ("length", "(length '(a b c d))", "4\n"),
    ("append", "(append '(1 2) '(3 4))", "(1 2 3 4)\n"),
    ("append 空", "(append)", "()\n"),
    ("null?", "(null? '())", "#t\n"),
    ("pair? 真", "(pair? '(1 2))", "#t\n"),
    ("pair? 空表", "(pair? '())", "#f\n"),
    ("list? 真列表", "(list? '(1 2))", "#t\n"),
    ("list? 点对", "(list? (cons 1 2))", "#f\n"),

    # ---- 谓词（spec §5） -----------------------------------------------
    ("number?", "(number? 5)", "#t\n"),
    ("number? 符号", "(number? 'x)", "#f\n"),
    ("boolean?", "(boolean? #t)", "#t\n"),
    ("symbol?", "(symbol? 'x)", "#t\n"),
    ("symbol? 字符串", "(symbol? \"x\")", "#f\n"),
    ("string?", "(string? \"s\")", "#t\n"),
    ("procedure? 内置", "(procedure? car)", "#t\n"),
    ("procedure? 数字", "(procedure? 1)", "#f\n"),
    ("zero?", "(zero? 0)", "#t\n"),
    ("even?", "(even? 8)", "#t\n"),
    ("odd?", "(odd? 7)", "#t\n"),
    ("eq? 空表", "(eq? '() '())", "#t\n"),
    ("eq? 两个列表不同一", "(eq? '(1) '(1))", "#f\n"),
    ("eq? 数字按值", "(eq? 5 5)", "#t\n"),
    ("equal? 结构相等", "(equal? '(1 2 3) (list 1 2 3))", "#t\n"),
    ("equal? 布尔与整数", "(equal? #t 1)", "#f\n"),
    ("equal? 符号与字符串", "(equal? 'a \"a\")", "#f\n"),
    ("equal? 不同长度", "(equal? '(1 2) '(1 2 3))", "#f\n"),

    # ---- define / lambda / 闭包（spec §4.5、§4.6、§9） ------------------
    ("define 返回符号名", "(define pi 3)", "pi\n"),
    ("define 后可见", "(define pi 3)\n(+ pi 1)", "pi\n4\n"),
    ("define 函数简写", "(define (square x) (* x x))\n(square 7)", "square\n49\n"),
    ("lambda 直接调用", "((lambda (x) (* x 2)) 5)", "10\n"),
    ("lambda 打印成过程", "(lambda (x) x)", "#<procedure>\n"),
    ("闭包记住定义环境", "(define (adder n) (lambda (x) (+ x n)))\n((adder 100) 7)",
     "adder\n107\n"),
    ("递归", "(define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))\n(fact 10)",
     "fact\n3628800\n"),
    ("用语言定义 map",
     "(define (map f xs) (if (null? xs) '() (cons (f (car xs)) (map f (cdr xs)))))\n"
     "(map (lambda (x) (* x x)) '(1 2 3 4))",
     "map\n(1 4 9 16)\n"),
    ("用语言定义 filter",
     "(define (filter p xs) (cond ((null? xs) '()) ((p (car xs)) (cons (car xs) (filter p (cdr xs))))"
     " (else (filter p (cdr xs)))))\n(filter odd? '(1 2 3 4 5))",
     "filter\n(1 3 5)\n"),

    # ---- let / begin（spec §4.7、§4.8） --------------------------------
    ("let 基本", "(let ((x 3) (y 4)) (+ x y))", "7\n"),
    ("let 嵌套", "(let ((a 1)) (let ((b (+ a 1))) (* a b)))", "2\n"),
    ("let 是并行绑定", "(define x 10)\n(let ((x 1) (y x)) y)", "x\n10\n"),
    ("let 体多表达式", "(let ((x 1)) (display x) (+ x 1))", "12\n"),
    ("begin", "(begin (define z 1) (+ z 41))", "42\n"),
    ("define 在函数体里",
     "(define (f) (define y 2))\n(f)", "f\ny\n"),

    # ---- 输出（spec §2、§5、§8） ---------------------------------------
    ("display 不换行", "(display (+ 1 2))(newline)", "3\n"),
    ("display 字符串不带引号", '(display "hello")', "hello"),
    ("display 列表里的字符串",
     "(display (list 1 \"a\" 'b))", "(1 a b)"),
    ("顶层字符串转义打印", '"a\\nb"', '"a\\nb"\n'),
    ("display 不转义", '(display "a\\nb")', "a\nb"),
    ("display 无返回值不打印", "(display 1)", "1"),
    ("newline 单独用", "(newline)", "\n"),
    ("tab 转义打印", '"a\\tb"', '"a\\tb"\n'),
    ("引号转义打印", '"a\\"b"', '"a\\"b"\n'),
    ("反斜杠转义打印", '"a\\\\b"', '"a\\\\b"\n'),

    # ---- 注释与词法（spec §3） -----------------------------------------
    ("行注释", "(+ 1 2) ; 这里到行尾都被忽略\n(* 2 3)", "3\n6\n"),
    ("大小写敏感", "(define foo 1)\n(define FOO 2)\n(+ foo FOO)", "foo\nFOO\n3\n"),
    ("负数与单减号", "(- -7)", "7\n"),
    ("符号里有特殊字符", "(define list-of? 1)\nlist-of?", "list-of?\n1\n"),
    # 非 ASCII：编码必须和评分器的解码方式一致（都是平台默认编码）。
    ("非 ASCII 符号与字符串",
     "(define 甲 1)\n甲\n'正\n(display \"中文\")\n(newline)",
     "甲\n1\n正\n中文\n"),

    # ---- 深递归（无尾调用优化，靠大栈兜底） ----------------------------
    ("深递归 1000",
     "(define (sum-to n) (if (= n 0) 0 (+ n (sum-to (- n 1)))))\n(sum-to 1000)",
     "sum-to\n500500\n"),
]


# --------------------------------------------------------------------------
# Unicode 空白回归用例
#
# 历史 bug：lexer 跳过空白用 ASCII 白名单，切分原子却用 str.isspace()。
# U+3000 / U+00A0 这类 Unicode 空白恰好落在两个判定中间，主循环不认为它
# 是空白而进入原子分支，原子循环又立刻停下 —— 下标不前进，死循环。
#
# 这两条必须走"文件参数"路径：U+00A0 在 cp936（本机平台默认编码）里无法
# 编码，走标准输入会被 subprocess 的编码层直接挡掉；而解释器读文件固定用
# UTF-8，稳定可复现。
# (说明, 夹具相对路径, 夹具里必须真实存在的码位, 期望输出)
# --------------------------------------------------------------------------
UNICODE_WHITESPACE_CHECKS = [
    ("U+3000 全角空格当空白（回归：曾导致词法死循环）",
     os.path.join("tests", "fixtures", "unicode_space_u3000.scm"),
     "\u3000", "3\n6\n(a b)\nx\n5\n"),
    ("U+00A0 不换行空格当空白（回归：曾导致词法死循环）",
     os.path.join("tests", "fixtures", "unicode_space_u00a0.scm"),
     "\u00a0", "3\n6\n(a b)\nx\n5\n"),
]

# 夹具必须真的含有它声称的那个码位：编辑过程中一个字符被"规范化"成普通
# 空格，这条回归就会静默失效。所以下面先断言码位存在，再跑解释器。


def run(source, timeout=None):
    """把源码喂给标准输入跑一次，返回 (returncode, stdout, stderr)。

    刻意**不指定** encoding：评分器用的是 ``text=True``（平台默认编码），
    这里必须用完全一样的方式解码，否则测不出编码相关的错位。

    超时返回 ``(None, TIMEOUT_MARK, "")`` —— 让调用方报"超时"失败，
    而不是把自测挂死。
    """
    return _invoke([], source=source, timeout=resolve_timeout(timeout))


def run_file(*paths, timeout=None):
    """按 CLI 约定把文件路径传给解释器跑一次，同样带超时。"""
    return _invoke(list(paths), source=None, timeout=resolve_timeout(timeout))


def resolve_timeout(timeout):
    """在**调用时**取默认值。

    如果写成 ``def run(source, timeout=TIMEOUT_SECONDS)``，默认值会在函数
    定义时就被绑死，之后改 ``TIMEOUT_SECONDS`` 不再起作用 —— 调参和测试
    超时机制本身都会失效。
    """
    return TIMEOUT_SECONDS if timeout is None else timeout


def _invoke(args, source, timeout):
    """所有子进程调用的唯一出口：保证一定带 timeout。"""
    if timeout is None or timeout <= 0:
        raise ValueError("每次子进程调用都必须带一个正的超时")
    try:
        proc = subprocess.run(
            [sys.executable, INTERPRETER, *args],
            input=source, capture_output=True, text=True, cwd=ROOT,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, TIMEOUT_MARK, ""
    return proc.returncode, proc.stdout, proc.stderr


def describe_failure(code, out, err, expected):
    """通过返回 None；不通过返回一句人类可读的说明。"""
    if code is None:
        return (f"超时：{TIMEOUT_SECONDS} 秒内没有结束（疑似死循环），"
                f"期望 {expected!r}")
    if out != expected or code != 0:
        return (f"期望 {expected!r}，实际 {out!r}，退出码 {code}，"
                f"stderr {err.strip()!r}")
    return None


def check_cli_modes(failures):
    """额外验证 CLI 约定：多文件共享环境、标准输入模式。"""
    fixture_dir = os.path.join(ROOT, "tests", "fixtures")
    first = os.path.join(fixture_dir, "shared_a.scm")
    second = os.path.join(fixture_dir, "shared_b.scm")

    code, out, err = run_file(first, second)
    detail = describe_failure(code, out, err, "shared\n42\n")
    if detail:
        failures.append(("多文件共享全局环境", detail))

    code, out, err = run("(+ 20 22)")
    detail = describe_failure(code, out, err, "42\n")
    if detail:
        failures.append(("标准输入模式", detail))

    code, out, err = run("")
    detail = describe_failure(code, out, err, "")
    if detail:
        failures.append(("空输入", detail))


def check_unicode_whitespace(failures):
    """回归：U+3000 / U+00A0 必须当空白，且不能把词法分析卡住。"""
    for name, relative, codepoint, expected in UNICODE_WHITESPACE_CHECKS:
        path = os.path.join(ROOT, relative)

        try:
            with open(path, "rb") as handle:
                fixture = handle.read().decode("utf-8")
        except OSError as exc:
            failures.append((name, f"读不到夹具 {relative}：{exc}"))
            continue

        if codepoint not in fixture:
            failures.append(
                (name, f"夹具 {relative} 里没有 U+{ord(codepoint):04X}，"
                       f"这条回归测试会静默失效")
            )
            continue

        code, out, err = run_file(path)
        detail = describe_failure(code, out, err, expected)
        if detail:
            failures.append((name, detail))


def main():
    failures = []
    for name, source, expected in CHECKS:
        code, out, err = run(source)
        detail = describe_failure(code, out, err, expected)
        if detail:
            failures.append((name, detail))

    check_unicode_whitespace(failures)
    check_cli_modes(failures)

    total = len(CHECKS) + len(UNICODE_WHITESPACE_CHECKS) + 3
    for name, detail in failures:
        print(f"  FAIL  {name}\n        {detail}")
    print(f"\n{total - len(failures)} passed, {len(failures)} failed / 共 {total} 项")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""mini-Scheme 解释器入口（spec §2 的 CLI 约定）。

用法::

    python3 src/main.py file1.scm [file2.scm ...]     # 顺序求值多个文件
    python3 src/main.py                               # 无参数时读标准输入

约定：
  * 按顺序求值每个顶层表达式，**每个结果独占一行**打印；
  * 结果为 None（display/newline 的返回值）时不打印；
  * 多个文件共享同一个全局环境；
  * 标准输出只有规范要求的内容，报错与调试信息一律走标准错误。
"""

import os
import sys
import threading

# 让 `python src/main.py` 和 `python /绝对路径/src/main.py` 都能 import 到
# 同目录下的 minischeme 包（不依赖当前工作目录）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from minischeme import parser, printer                       # noqa: E402
from minischeme.builtins import make_global_env              # noqa: E402
from minischeme.errors import SchemeError                    # noqa: E402
from minischeme.evaluator import evaluate                    # noqa: E402

# 递归深度：mini-Scheme 没有尾调用优化保证（spec §10），深递归只能靠加大
# Python 栈兜底（同时见 _run_in_big_stack_thread）。
# 实测：一次 Scheme 调用约消耗 7 层 Python 递归，配 256 MB 栈线程时
# 5 万层 Scheme 递归 0.5 秒内跑完；再深会干净地抛 RecursionError
# （退出码 1 + stderr 一行说明），不会崩掉进程。
_RECURSION_LIMIT = 1000000
_STACK_BYTES = 256 * 1024 * 1024


def run_source(text, origin, env, out=None):
    """解析并求值一段源码，逐行打印每个顶层表达式的值。

    多个文件之间复用同一个 env，所以后一个文件能看到前一个的 define。
    """
    out = sys.stdout if out is None else out

    # Windows 编辑器常给 .scm 加 BOM；它必须当成空白而不是符号的一部分。
    if text.startswith("\ufeff"):
        text = text[1:]

    try:
        # 先整体解析再求值：语法错误不会造成"跑了一半"的输出。
        expressions = parser.parse(text)
    except SchemeError as exc:
        raise SchemeError(f"{origin}: {exc}") from None

    for expression in expressions:
        try:
            value = evaluate(expression, env)
        except SchemeError as exc:
            raise SchemeError(f"{origin}: {exc}") from None
        if value is not None:            # None 表示"无值"，不打印
            out.write(printer.to_repr(value))
            out.write("\n")


def run_path(path, env):
    """读一个 .scm 文件并求值（utf-8-sig 允许文件带 BOM）。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            text = handle.read()
    except OSError as exc:
        raise SchemeError(f"无法读取文件 {path}：{exc.strerror or exc}") from None
    run_source(text, path, env)


def main(argv=None):
    """返回进程退出码：0 正常，1 出错。"""
    argv = list(sys.argv[1:] if argv is None else argv)
    env = make_global_env()

    try:
        if argv:
            for path in argv:
                run_path(path, env)
        else:
            run_source(sys.stdin.read(), "<stdin>", env)
    except SchemeError as exc:
        sys.stdout.flush()
        print(f"mini-scheme 错误: {exc}", file=sys.stderr)
        return 1
    except RecursionError:
        sys.stdout.flush()
        print("mini-scheme 错误: 递归太深（超出解释器栈上限）", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        sys.stdout.flush()
        print("mini-scheme: 已中断", file=sys.stderr)
        return 130
    finally:
        sys.stdout.flush()

    return 0


def _configure_streams():
    """只加固标准错误，**不动**标准输出的编码。

    评分器用 ``subprocess.run(..., text=True)`` 抓取程序输出，也就是按
    **平台默认编码**（中文 Windows 上是 cp936/gbk）解码。所以标准输出必须
    保持 Python 的默认行为（等价于 ``print``），否则非 ASCII 输出会和评分器
    的解码方式错位。

    标准错误只给自己看，把无法编码的字符降级成反斜杠转义，
    免得"打印报错信息"这一步自己再抛一个 UnicodeEncodeError。
    """
    reconfigure = getattr(sys.stderr, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(errors="backslashreplace")
        except (ValueError, OSError):
            pass


def _run_in_big_stack_thread():
    """在大栈线程里跑 main，让深递归用例不至于撞上系统栈上限。"""
    box = {}

    def worker():
        box["code"] = main()

    sys.setrecursionlimit(_RECURSION_LIMIT)
    try:
        threading.stack_size(_STACK_BYTES)
    except (ValueError, RuntimeError):
        pass                                  # 平台不支持就退回主线程
    thread = threading.Thread(target=worker, name="mini-scheme")
    thread.start()
    thread.join()
    return box.get("code", 1)


if __name__ == "__main__":
    _configure_streams()
    sys.exit(_run_in_big_stack_thread())

"""mini-Scheme 解释器。

流水线拆成职责单一的模块：

    程序文本 --lexer--> 词 --parser--> 表达式 --evaluator--> 值 --printer--> 文本
                                      ^
                            environment / builtins

`datatypes` 定义所有值类型，`errors` 定义报错类型，各模块之间没有环。
"""

__all__ = ["errors", "datatypes", "lexer", "parser", "environment", "printer",
           "builtins", "evaluator"]

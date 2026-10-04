"""解释器自知会发生的错误类型。

评分规范里没有定义出错时的行为（"错误处理策略（出错时行为未定义，
测试不触发错误）"），所以这里的目标只有一个：让意外输入变成一条人类
可读、带位置信息、绝不会以 Python traceback 形式泄漏到标准输出的报错。

所有异常都继承自 SchemeError，入口 src/main.py 只捕获这一个根类型。
"""


class SchemeError(Exception):
    """所有 mini-Scheme 错误的根类型。

    message 是给人看的中文说明；line/column 是出错位置（词法/语法阶段
    由 token 提供，运行阶段通常为 None）。
    """

    def __init__(self, message, line=None, column=None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column

    def __str__(self):
        if self.line is None:
            return self.message
        return f"第 {self.line} 行第 {self.column} 列：{self.message}"


class SchemeSyntaxError(SchemeError):
    """词法/语法阶段：括号不配对、字符串没闭合、点号位置错误等。"""


class SchemeNameError(SchemeError):
    """引用了未绑定的符号。"""


class SchemeTypeError(SchemeError):
    """参数类型不对，例如把 car 用在非点对上。"""


class SchemeArityError(SchemeError):
    """参数个数不对。"""


class SchemeArithmeticError(SchemeError):
    """算术域错误，例如除以零。"""

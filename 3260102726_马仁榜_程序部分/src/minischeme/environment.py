"""环境：变量绑定表 + 指向外层环境的指针。

链式环境就是词法作用域的载体：查找沿父链向上走，``define`` 永远写在
当前（最内层）环境里，``lambda`` 保存的则是它被创建时的那一层。
"""

from .errors import SchemeNameError

__all__ = ["Environment"]


class Environment:
    """一层作用域。``parent`` 为 None 表示全局环境。"""

    __slots__ = ("_bindings", "parent")

    def __init__(self, parent=None):
        self._bindings = {}
        self.parent = parent

    def define(self, name, value):
        """在当前层建立/覆盖绑定，返回被绑定的名字。"""
        self._bindings[name] = value
        return name

    def lookup(self, name):
        """沿父链查找；找不到是明确的错误，而不是悄悄返回 None。"""
        env = self
        while env is not None:
            if name in env._bindings:
                return env._bindings[name]
            env = env.parent
        raise SchemeNameError(f"未绑定的符号：{name}")

    def contains(self, name):
        """当前层是否直接绑定了这个名字（调试/测试用）。"""
        return name in self._bindings

    @classmethod
    def with_bindings(cls, names, values, parent=None):
        """批量绑定，返回新环境。让 let/函数调用共用同一段建层逻辑。"""
        env = cls(parent)
        for name, value in zip(names, values):
            env.define(name, value)
        return env

"""
异常定义
从readscope提取的核心异常类
"""


class ErnieAgentException(Exception):
    """ERNIE Agent基础异常"""
    pass


class LLMClientError(Exception):
    """LLM客户端错误"""
    pass


class ModelLoadError(Exception):
    """模型加载错误"""
    pass


class ConfigurationError(Exception):
    """配置错误"""
    pass


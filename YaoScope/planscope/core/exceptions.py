"""
PlanScope异常定义
定义工作流引擎中使用的所有自定义异常类
"""


class PlanScopeError(Exception):
    """PlanScope基础异常类"""
    pass


class PlanGenerationError(PlanScopeError):
    """流程生成失败异常"""
    pass


class PlanParsingError(PlanScopeError):
    """流程解析失败异常"""
    pass


class PlanExecutionError(PlanScopeError):
    """流程执行失败异常"""
    
    def __init__(self, message: str, step_id: int = None, executed_steps: list = None):
        """
        初始化执行异常
        
        Args:
            message: 错误信息
            step_id: 失败的步骤ID
            executed_steps: 已执行的步骤列表
        """
        super().__init__(message)
        self.step_id = step_id
        self.executed_steps = executed_steps or []


class ToolNotFoundError(PlanScopeError):
    """工具未注册异常"""
    pass


class DependencyError(PlanScopeError):
    """依赖关系错误异常"""
    pass


class VariableResolutionError(PlanScopeError):
    """变量解析失败异常"""
    pass


class PlanValidationError(PlanScopeError):
    """流程验证失败异常"""
    pass


class ACEContextError(PlanScopeError):
    """ACE上下文操作失败异常"""
    pass


class ACEReflectionError(PlanScopeError):
    """ACE反思过程失败异常"""
    pass


class ACECurationError(PlanScopeError):
    """ACE整编过程失败异常"""
    pass


class TaskMatchingError(PlanScopeError):
    """任务匹配失败异常"""
    pass

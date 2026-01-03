"""
PlanScope - 基于AgentScope的工作流引擎

提供简洁的API接口用于工作流生成和执行
"""

from planscope.planscope import PlanScope
from planscope.core.exceptions import (
    PlanScopeError,
    PlanGenerationError,
    PlanParsingError,
    PlanExecutionError,
    ToolNotFoundError,
    DependencyError,
    VariableResolutionError,
    PlanValidationError
)

__version__ = "0.1.0"

__all__ = [
    "PlanScope",
    "PlanScopeError",
    "PlanGenerationError",
    "PlanParsingError",
    "PlanExecutionError",
    "ToolNotFoundError",
    "DependencyError",
    "VariableResolutionError",
    "PlanValidationError"
]


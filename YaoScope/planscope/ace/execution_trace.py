"""
ACE执行轨迹数据结构
记录工作流执行的完整轨迹
"""
import uuid
import traceback as tb
from typing import Dict, Any, List, Optional
from datetime import datetime


class ExecutionTrace:
    """
    执行轨迹
    
    记录工作流执行的完整信息，包括成功和失败的详情
    """
    
    def __init__(self,
                 trace_id: Optional[str] = None,
                 flow_id: Optional[str] = None,
                 task_description: str = "",
                 plan_json: Optional[Dict[str, Any]] = None,
                 tools_used: Optional[List[str]] = None,
                 execution_result: Optional[Dict[str, Any]] = None,
                 timestamp: Optional[str] = None):
        """
        初始化执行轨迹
        
        Args:
            trace_id: 轨迹唯一标识符
            flow_id: 工作流ID
            task_description: 任务描述
            plan_json: 工作流JSON
            tools_used: 使用的工具列表
            execution_result: 执行结果
            timestamp: 时间戳
        """
        self.trace_id = trace_id or str(uuid.uuid4())
        self.flow_id = flow_id
        self.task_description = task_description
        self.plan_json = plan_json or {}
        self.tools_used = tools_used or []
        self.execution_result = execution_result or {
            "success": False,
            "executed_steps": [],
            "step_results": {},
            "execution_time": 0.0,
            "failure_info": None
        }
        self.timestamp = timestamp or datetime.now().isoformat()
        
        # 步骤详情（用于记录每个步骤的执行信息）
        self.step_details = []
    
    def to_dict(self) -> Dict[str, Any]:
        """
        序列化为字典
        
        Returns:
            字典表示
        """
        return {
            "trace_id": self.trace_id,
            "flow_id": self.flow_id,
            "task_description": self.task_description,
            "plan_json": self.plan_json,
            "tools_used": self.tools_used,
            "execution_result": self.execution_result,
            "timestamp": self.timestamp,
            "step_details": self.step_details
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionTrace':
        """
        从字典反序列化
        
        Args:
            data: 字典数据
            
        Returns:
            ExecutionTrace实例
        """
        trace = cls(
            trace_id=data.get("trace_id"),
            flow_id=data.get("flow_id"),
            task_description=data.get("task_description", ""),
            plan_json=data.get("plan_json", {}),
            tools_used=data.get("tools_used", []),
            execution_result=data.get("execution_result", {}),
            timestamp=data.get("timestamp")
        )
        trace.step_details = data.get("step_details", [])
        return trace
    
    def is_success(self) -> bool:
        """
        判断是否执行成功
        
        Returns:
            是否成功
        """
        return self.execution_result.get("success", False)
    
    def get_failure_info(self) -> Optional[Dict[str, Any]]:
        """
        获取失败信息
        
        Returns:
            失败信息（如果失败）
        """
        return self.execution_result.get("failure_info")
    
    def get_tools_used(self) -> List[str]:
        """
        获取使用的工具列表
        
        Returns:
            工具名称列表
        """
        return self.tools_used
    
    def add_step_detail(self,
                       step_id: int,
                       tool_name: str,
                       tool_input: Dict[str, Any],
                       tool_output: Optional[Any] = None,
                       duration: float = 0.0,
                       error: Optional[str] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        添加步骤详情
        
        Args:
            step_id: 步骤ID
            tool_name: 工具名称
            tool_input: 工具输入
            tool_output: 工具输出
            duration: 执行耗时
            error: 错误信息（如果有）
            metadata: 工具元数据（包含output_json_schema等）
        """
        detail = {
            "step_id": step_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_output": tool_output,
            "duration": duration,
            "error": error,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        }
        self.step_details.append(detail)
        
        # 更新工具列表
        if tool_name not in self.tools_used:
            self.tools_used.append(tool_name)
    
    def set_failure(self,
                   step_id: int,
                   error: Exception,
                   executed_steps: List[int]) -> None:
        """
        设置失败信息
        
        Args:
            step_id: 失败的步骤ID
            error: 异常对象
            executed_steps: 已执行的步骤列表
        """
        self.execution_result["success"] = False
        self.execution_result["executed_steps"] = executed_steps
        self.execution_result["failure_info"] = {
            "step_id": step_id,
            "error": str(error),
            "error_type": type(error).__name__,
            "traceback": tb.format_exc()
        }
    
    def set_success(self,
                   executed_steps: List[int],
                   step_results: Dict[int, Any],
                   execution_time: float) -> None:
        """
        设置成功信息
        
        Args:
            executed_steps: 已执行的步骤列表
            step_results: 步骤结果
            execution_time: 总执行时间
        """
        self.execution_result["success"] = True
        self.execution_result["executed_steps"] = executed_steps
        self.execution_result["step_results"] = step_results
        self.execution_result["execution_time"] = execution_time
    
    def get_failed_step_id(self) -> Optional[int]:
        """
        获取失败的步骤ID
        
        Returns:
            失败的步骤ID（如果失败）
        """
        failure_info = self.get_failure_info()
        if failure_info:
            return failure_info.get("step_id")
        return None
    
    def get_error_message(self) -> Optional[str]:
        """
        获取错误信息
        
        Returns:
            错误信息（如果失败）
        """
        failure_info = self.get_failure_info()
        if failure_info:
            return failure_info.get("error")
        return None
    
    def get_error_traceback(self) -> Optional[str]:
        """
        获取错误堆栈
        
        Returns:
            错误堆栈（如果失败）
        """
        failure_info = self.get_failure_info()
        if failure_info:
            return failure_info.get("traceback")
        return None
    
    def __repr__(self) -> str:
        """字符串表示"""
        status = "SUCCESS" if self.is_success() else "FAILURE"
        return f"ExecutionTrace(id={self.trace_id[:8]}, status={status}, steps={len(self.step_details)})"


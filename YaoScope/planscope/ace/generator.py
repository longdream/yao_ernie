"""
ACE Generator（生成器）
记录工作流执行轨迹

职责说明：
- ExecutionTrace：记录执行结果和工具调用，用于ACEReflector分析失败原因和成功模式（完整版）
- ReflectionChain：记录LLM输入输出和思考过程，用于调试和可视化（完整版）

两者职责不同，都需要保持完整，互不冗余：
- ExecutionTrace服务于ACE自动分析和学习
- ReflectionChain服务于开发者调试和可视化展示
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from planscope.ace.execution_trace import ExecutionTrace


class ACEGenerator:
    """
    ACE生成器
    
    负责记录工作流执行的完整轨迹
    """
    
    def __init__(self, logger_manager, work_dir: Optional[str] = None, storage_manager=None):
        """
        初始化生成器
        
        Args:
            logger_manager: 日志管理器
            work_dir: 工作目录（用于保存轨迹文件）
            storage_manager: 存储管理器（可选，优先使用）
        """
        self.logger_manager = logger_manager
        self.logger = logger_manager.get_logger("ace_generator")
        
        # 当前轨迹
        self.current_trace: Optional[ExecutionTrace] = None
        
        # 轨迹保存目录
        if storage_manager:
            self.traces_dir = storage_manager.get_path("traces")
        elif work_dir:
            self.traces_dir = Path(work_dir) / "ace_traces"
            self.traces_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.traces_dir = None
    
    def start_trace(self, task_description: str, plan_json: Dict[str, Any]) -> ExecutionTrace:
        """
        开始记录轨迹
        
        Args:
            task_description: 任务描述
            plan_json: 工作流JSON
            
        Returns:
            新创建的轨迹对象
        """
        self.logger.info("开始记录执行轨迹")
        self.logger.debug(f"任务: {task_description}")
        
        # 创建新轨迹
        self.current_trace = ExecutionTrace(
            flow_id=plan_json.get("flow_id"),
            task_description=task_description,
            plan_json=plan_json
        )
        
        return self.current_trace
    
    def record_step_execution(self,
                             step_id: int,
                             tool_name: str,
                             tool_input: Dict[str, Any],
                             tool_output: Optional[Any] = None,
                             duration: float = 0.0,
                             error: Optional[str] = None,
                             metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        记录步骤执行
        
        Args:
            step_id: 步骤ID
            tool_name: 工具名称
            tool_input: 工具输入
            tool_output: 工具输出
            duration: 执行耗时
            error: 错误信息（如果有）
            metadata: 工具元数据（包含output_json_schema等）
        """
        if self.current_trace is None:
            self.logger.warning("未开始轨迹记录，无法记录步骤执行")
            return
        
        self.logger.debug(f"记录步骤 {step_id} 执行: {tool_name}")
        
        # 添加步骤详情
        self.current_trace.add_step_detail(
            step_id=step_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            duration=duration,
            error=error,
            metadata=metadata
        )
    
    def record_success(self,
                      executed_steps: List[int],
                      step_results: Dict[int, Any],
                      execution_time: float) -> None:
        """
        记录成功
        
        Args:
            executed_steps: 已执行的步骤列表
            step_results: 步骤结果
            execution_time: 总执行时间
        """
        if self.current_trace is None:
            self.logger.warning("未开始轨迹记录，无法记录成功")
            return
        
        self.logger.info("记录执行成功")
        
        # 设置成功信息
        self.current_trace.set_success(
            executed_steps=executed_steps,
            step_results=step_results,
            execution_time=execution_time
        )
    
    def record_failure(self,
                      step_id: int,
                      error: Exception,
                      executed_steps: List[int]) -> None:
        """
        记录失败
        
        Args:
            step_id: 失败的步骤ID
            error: 异常对象
            executed_steps: 已执行的步骤列表
        """
        if self.current_trace is None:
            self.logger.warning("未开始轨迹记录，无法记录失败")
            return
        
        self.logger.info(f"记录执行失败: 步骤 {step_id}")
        self.logger.error(f"错误: {str(error)}")
        
        # 设置失败信息
        self.current_trace.set_failure(
            step_id=step_id,
            error=error,
            executed_steps=executed_steps
        )
    
    def finalize_trace(self) -> Optional[ExecutionTrace]:
        """
        完成轨迹记录
        
        Returns:
            完成的轨迹对象
        """
        if self.current_trace is None:
            return None
        
        self.logger.info("完成轨迹记录")
        
        # 保存轨迹
        if self.traces_dir:
            self.save_trace(self.current_trace)
        
        trace = self.current_trace
        self.current_trace = None
        
        return trace
    
    def get_current_trace(self) -> Optional[ExecutionTrace]:
        """
        获取当前轨迹
        
        Returns:
            当前轨迹对象
        """
        return self.current_trace
    
    def save_trace(self, trace: ExecutionTrace) -> None:
        """
        保存轨迹到文件
        
        Args:
            trace: 轨迹对象
        """
        if not self.traces_dir:
            return
        
        try:
            # 生成文件名
            filename = f"trace_{trace.trace_id}.json"
            filepath = self.traces_dir / filename
            
            # 确保目录存在
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # 序列化并保存
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(trace.to_dict(), f, ensure_ascii=False, indent=2)
            
            self.logger.debug(f"轨迹已保存到: {filepath}")
            
        except Exception as e:
            self.logger.error(f"保存轨迹失败: {str(e)}")
    
    def load_trace(self, trace_id: str) -> Optional[ExecutionTrace]:
        """
        加载轨迹
        
        Args:
            trace_id: 轨迹ID
            
        Returns:
            轨迹对象（如果找到）
        """
        if not self.traces_dir:
            return None
        
        try:
            filename = f"trace_{trace_id}.json"
            filepath = self.traces_dir / filename
            
            if not filepath.exists():
                return None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return ExecutionTrace.from_dict(data)
            
        except Exception as e:
            self.logger.error(f"加载轨迹失败: {str(e)}")
            return None
    
    def get_recent_traces(self, limit: int = 10) -> List[ExecutionTrace]:
        """
        获取最近的轨迹
        
        Args:
            limit: 返回数量限制
            
        Returns:
            轨迹列表
        """
        if not self.traces_dir:
            return []
        
        try:
            # 获取所有轨迹文件
            trace_files = sorted(
                self.traces_dir.glob("trace_*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            # 加载轨迹
            traces = []
            for trace_file in trace_files[:limit]:
                try:
                    with open(trace_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    traces.append(ExecutionTrace.from_dict(data))
                except Exception as e:
                    self.logger.warning(f"加载轨迹文件失败 {trace_file}: {str(e)}")
            
            return traces
            
        except Exception as e:
            self.logger.error(f"获取最近轨迹失败: {str(e)}")
            return []


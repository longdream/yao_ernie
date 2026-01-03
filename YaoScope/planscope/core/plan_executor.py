"""
流程执行器
按照拓扑排序的顺序执行工作流步骤
"""
import time
from typing import Dict, Any, List, Callable, Optional

from planscope.core.exceptions import (
    PlanExecutionError,
    ToolNotFoundError,
    VariableResolutionError
)
from planscope.core.plan_parser import PlanParser
from planscope.tools.tool_registry import ToolRegistry
from planscope.tools.variable_resolver import VariableResolver


class PlanExecutor:
    """
    流程执行器
    按依赖顺序执行步骤，处理变量替换和错误
    """
    
    def __init__(self, logger_manager, ace_generator=None, storage_manager=None):
        """
        初始化流程执行器
        
        Args:
            logger_manager: 日志管理器
            ace_generator: ACE生成器（可选，用于记录执行轨迹）
            storage_manager: 存储管理器（可选，用于工具输出路径）
        """
        self.logger_manager = logger_manager
        self.logger = logger_manager.get_logger("plan_executor")
        self.parser = PlanParser(logger_manager)
        self.ace_generator = ace_generator
        self.storage_manager = storage_manager
    
    def execute(self,
               plan_json: Dict[str, Any],
               tools: Dict[str, Callable],
               reflection_chain=None) -> Dict[str, Any]:
        """
        执行工作流
        
        Args:
            plan_json: 工作流JSON对象
            tools: 工具函数字典 {tool_name: function}
            reflection_chain: 反思链对象（可选）
            
        Returns:
            执行结果，包含所有步骤的返回值
            
        Raises:
            PlanExecutionError: 执行失败
        """
        self.logger.info("=" * 80)
        self.logger.info("开始执行工作流")
        self.logger.info(f"工作流ID: {plan_json.get('flow_id', 'unknown')}")
        self.logger.info("=" * 80)
        
        start_time = time.time()
        
        # ACE: 开始记录轨迹
        if self.ace_generator:
            task_description = plan_json.get("original_query", "")
            self.ace_generator.start_trace(task_description, plan_json)
        
        try:
            # 解析工作流
            parse_result = self.parser.parse(plan_json)
            step_map = parse_result["step_map"]
            execution_order = parse_result["execution_order"]
            
            # 创建临时工具注册表
            # 设计说明：使用临时registry而非全局registry的原因：
            # 1. 在plan生成时可能通过ToolGenerator动态生成新工具
            # 2. 这些动态生成的工具需要在执行阶段临时注册
            # 3. 临时registry用于隔离执行环境，不影响全局registry
            # 4. 执行完成后，临时工具不会污染全局注册表
            tool_registry = ToolRegistry()
            for tool_name, tool_func in tools.items():
                tool_registry.add(tool_name, tool_func)
            
            # 执行上下文，存储每个步骤的返回值
            context = {"steps": {}}
            executed_steps = []
            
            # 获取 session_id（如果存在）用于发布进度
            session_id = plan_json.get("session_id")
            pm = None
            if session_id:
                try:
                    from service.core.progress_manager import ProgressManager
                    pm = ProgressManager.get_instance()
                except Exception as e:
                    self.logger.debug(f"无法获取进度管理器: {e}")
            
            # 按拓扑顺序执行步骤
            for step_id in execution_order:
                step = step_map[step_id]
                tool_name = step.get("tool", "unknown")
                description = step.get("description", "")
                
                # 发布 step_start 事件
                if pm and session_id:
                    pm.publish_step_start(session_id, step_id, tool_name, description)
                
                try:
                    flow_id = plan_json.get("flow_id", "unknown")
                    result = self._execute_step(step, tool_registry, context, reflection_chain, flow_id)
                    context["steps"][step_id] = result
                    executed_steps.append(step_id)
                    
                    self.logger.info(f"步骤 {step_id} 执行成功")
                    
                    # 发布 step_done 事件
                    if pm and session_id:
                        pm.publish_step_done(session_id, step_id, tool_name, description)
                    
                except Exception as e:
                    error_msg = f"步骤 {step_id} 执行失败: {str(e)}"
                    self.logger.error(error_msg)
                    
                    # 发布 step_error 事件
                    if pm and session_id:
                        pm.publish_step_error(session_id, step_id, tool_name, str(e))
                    
                    # ACE: 记录失败
                    if self.ace_generator:
                        self.ace_generator.record_failure(step_id, e, executed_steps)
                    
                    raise PlanExecutionError(
                        error_msg,
                        step_id=step_id,
                        executed_steps=executed_steps
                    ) from e
            
            execution_time = time.time() - start_time
            
            # ACE: 记录成功
            if self.ace_generator:
                self.ace_generator.record_success(executed_steps, context["steps"], execution_time)
            
            self.logger.info("=" * 80)
            self.logger.info(f"工作流执行成功，共执行 {len(executed_steps)} 个步骤")
            self.logger.info(f"总耗时: {execution_time:.2f}秒")
            self.logger.info("=" * 80)
            
            # 记录性能指标
            self.logger_manager.log_performance_metrics(
                operation="plan_execution",
                duration=execution_time,
                additional_metrics={
                    "step_count": len(executed_steps),
                    "flow_id": plan_json.get("flow_id", "unknown")
                }
            )
            
            # 获取最后一步的结果
            final_step_id = execution_order[-1] if execution_order else None
            final_step_result = context["steps"].get(final_step_id, {})
            
            return {
                "success": True,
                "executed_steps": executed_steps,
                "step_results": context["steps"],
                "final_step": final_step_result,  # 新增：直接提供最后一步
                "execution_order": execution_order,
                "execution_time": execution_time,
                "flow_id": plan_json.get("flow_id"),
                "reflection_chain": reflection_chain
            }
            
        except PlanExecutionError:
            raise
        except Exception as e:
            error_msg = f"工作流执行失败: {str(e)}"
            self.logger.error(error_msg)
            raise PlanExecutionError(error_msg) from e
    
    def _execute_step(self,
                     step: Dict[str, Any],
                     tool_registry: ToolRegistry,
                     context: Dict[str, Any],
                     reflection_chain=None,
                     flow_id=None) -> Any:
        """
        执行单个步骤
        
        Args:
            step: 步骤对象
            tool_registry: 工具注册表
            context: 执行上下文
            reflection_chain: 反思链对象（可选）
            flow_id: 工作流ID（可选）
            
        Returns:
            步骤执行结果
            
        Raises:
            ToolNotFoundError: 工具未注册
            VariableResolutionError: 变量解析失败
        """
        step_id = step["step_id"]
        tool_name = step["tool"]
        tool_input = step["tool_input"]
        description = step.get("description", "")
        
        self.logger.info(f"执行步骤 {step_id}: {description}")
        self.logger.info(f"  工具: {tool_name}")
        
        # 检查工具是否已注册
        if not tool_registry.has(tool_name):
            raise ToolNotFoundError(f"工具 '{tool_name}' 未注册")
        
        # 获取工具的schema（用于占位符替换）
        tool_metadata = tool_registry.get_metadata(tool_name) if hasattr(tool_registry, 'get_metadata') else {}
        tool_schema = tool_metadata.get('output_json_schema', '')
        
        # 准备解析上下文（添加当前工具的schema）
        resolve_context = {
            **context,
            "current_tool_schema": tool_schema
        }
        
        # 解析变量引用
        resolver = VariableResolver(resolve_context, logger=self.logger)
        try:
            resolved_input = resolver.resolve(tool_input)
            
            # 显示替换摘要
            if resolver.replacements:
                self.logger.info(f"  占位符替换: {len(resolver.replacements)}个")
                for repl in resolver.replacements:
                    self.logger.debug(f"    {repl['placeholder']} → {resolver._format_value(repl['value'])}")
            self.logger.debug(f"  解析后的输入: {resolved_input}")
        except Exception as e:
            raise VariableResolutionError(f"变量解析失败: {str(e)}") from e
        
        # 为VL工具注入output_file参数
        if tool_name == "vl_extract_chat_content" and self.storage_manager and flow_id:
            output_file = str(self.storage_manager.get_tool_output_file("vl_extract", flow_id))
            resolved_input["output_file"] = output_file
            self.logger.debug(f"  VL工具输出路径: {output_file}")
        
        # 记录工具执行前到反思链
        if reflection_chain:
            # 提取prompt参数（如果有）
            prompt_value = resolved_input.get("prompt", "")
            reflection_chain.add_entry(
                stage="tool_execution",
                input_data={
                    "step_id": step_id,
                    "tool_name": tool_name,
                    "description": description,
                    "tool_input": resolved_input,
                    "prompt": prompt_value[:500] + "..." if len(prompt_value) > 500 else prompt_value,
                    "prompt_length": len(prompt_value) if prompt_value else 0
                }
            )
        
        # 获取工具函数和metadata
        tool_func = tool_registry.get(tool_name)
        tool_metadata_raw = tool_registry.get_metadata(tool_name) if hasattr(tool_registry, 'get_metadata') else {}
        
        # 过滤metadata，只保留可序列化的字段
        tool_metadata = {}
        if tool_metadata_raw:
            # 只保留output_json_schema和input_parameters的描述信息
            if "output_json_schema" in tool_metadata_raw:
                tool_metadata["output_json_schema"] = tool_metadata_raw["output_json_schema"]
            if "input_parameters" in tool_metadata_raw:
                # 简化input_parameters，移除default值等不可序列化的内容
                simplified_params = {}
                for param_name, param_info in tool_metadata_raw["input_parameters"].items():
                    simplified_params[param_name] = {
                        "type": param_info.get("type", ""),
                        "description": param_info.get("description", ""),
                        "required": param_info.get("required", False)
                    }
                tool_metadata["input_parameters"] = simplified_params
        
        # 执行工具
        step_start_time = time.time()
        try:
            result = tool_func(**resolved_input)
            step_duration = time.time() - step_start_time
            
            self.logger.info(f"  步骤耗时: {step_duration:.2f}秒")
            
            # 输出步骤结果（特别是LLM工具的content字段）
            if isinstance(result, dict):
                if "content" in result:
                    content = result["content"]
                    content_preview = content[:200] + "..." if len(content) > 200 else content
                    self.logger.info(f"  步骤输出内容: {content_preview}")
                    self.logger.info(f"  内容长度: {len(content)} 字符")
            
            self.logger.debug(f"  返回结果: {result}")
            
            # 记录工具执行后到反思链
            if reflection_chain:
                # 截断result以避免过大
                result_str = str(result)
                reflection_chain.add_entry(
                    stage="tool_execution_result",
                    output_data={
                        "step_id": step_id,
                        "tool_name": tool_name,
                        "result": result_str[:1000] + "..." if len(result_str) > 1000 else result_str,
                        "result_length": len(result_str),
                        "execution_time": step_duration,
                        "success": True
                    }
                )
            
            # ACE: 记录步骤执行
            if self.ace_generator:
                self.ace_generator.record_step_execution(
                    step_id=step_id,
                    tool_name=tool_name,
                    tool_input=resolved_input,
                    tool_output=result,
                    duration=step_duration,
                    error=None,
                    metadata=tool_metadata
                )
            
            return result
            
        except Exception as e:
            import traceback
            error_msg = f"工具 '{tool_name}' 执行失败: {str(e)}"
            self.logger.error(error_msg)
            self.logger.error(f"完整异常追踪:\n{traceback.format_exc()}")
            
            # ACE: 记录步骤执行（失败）
            if self.ace_generator:
                self.ace_generator.record_step_execution(
                    step_id=step_id,
                    tool_name=tool_name,
                    tool_input=resolved_input,
                    tool_output=None,
                    duration=time.time() - step_start_time,
                    error=str(e),
                    metadata=tool_metadata
                )
            
            raise PlanExecutionError(error_msg, step_id=step_id) from e
    
    def validate_tools(self,
                      plan_json: Dict[str, Any],
                      tools: Dict[str, Callable]) -> Dict[str, Any]:
        """
        验证所需的工具是否都已提供
        
        Args:
            plan_json: 工作流JSON对象
            tools: 工具函数字典
            
        Returns:
            验证结果 {
                "valid": bool,
                "missing_tools": List[str],
                "available_tools": List[str]
            }
        """
        steps = plan_json["steps"]
        required_tools = set()
        
        for step in steps:
            required_tools.add(step["tool"])
        
        provided_tools = set(tools.keys())
        missing_tools = required_tools - provided_tools
        
        result = {
            "valid": len(missing_tools) == 0,
            "missing_tools": list(missing_tools),
            "available_tools": list(provided_tools),
            "required_tools": list(required_tools)
        }
        
        if missing_tools:
            self.logger.warning(f"缺少工具: {missing_tools}")
        else:
            self.logger.info("所有必需的工具都已提供")
        
        return result


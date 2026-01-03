"""
工具注册中心
提供装饰器模式的工具注册机制
"""
import inspect
import asyncio
from typing import Dict, Any, Callable, Optional
from planscope.core.exceptions import ToolNotFoundError


class ToolRegistry:
    """
    工具注册中心
    支持装饰器注册和手动注册两种方式
    集成ToolUnderstandingAgent自动提取metadata
    """
    
    def __init__(self, tool_understanding_agent=None):
        """
        初始化工具注册表
        
        Args:
            tool_understanding_agent: 工具理解Agent（可选）
        """
        self._tools: Dict[str, Callable] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self.tool_understanding_agent = tool_understanding_agent
    
    def register(self, name: str):
        """
        装饰器：注册工具函数
        
        Args:
            name: 工具名称
            
        Returns:
            装饰器函数
            
        Example:
            >>> registry = ToolRegistry()
            >>> @registry.register("my_tool")
            ... def my_function(arg1, arg2):
            ...     return {"result": arg1 + arg2}
        """
        def decorator(func: Callable) -> Callable:
            self.add(name, func)
            return func
        return decorator
    
    def add(self, name: str, func: Callable, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        手动注册工具函数
        
        如果启用了ToolUnderstandingAgent，会自动分析工具并提取完整metadata
        
        Args:
            name: 工具名称
            func: 工具函数
            metadata: 工具元数据（可选，用于覆盖自动提取的内容）
        """
        if not callable(func):
            raise ValueError(f"工具 '{name}' 必须是可调用对象")
        
        self._tools[name] = func
        
        # 如果启用了ToolUnderstandingAgent，自动分析工具
        auto_metadata = None
        if self.tool_understanding_agent:
            try:
                # 检测是否已有运行中的事件循环
                try:
                    loop = asyncio.get_running_loop()
                    # 如果有运行中的事件循环，使用nest_asyncio
                    import nest_asyncio
                    nest_asyncio.apply()
                    auto_metadata = asyncio.run(
                        self.tool_understanding_agent.analyze_tool(name, func)
                    )
                except RuntimeError:
                    # 没有运行中的事件循环，直接使用asyncio.run
                    auto_metadata = asyncio.run(
                        self.tool_understanding_agent.analyze_tool(name, func)
                    )
            except Exception as e:
                # 工具分析失败，抛出异常（不允许降级）
                raise RuntimeError(f"工具 '{name}' 分析失败: {str(e)}") from e
        
        # 如果没有自动提取的metadata，使用基础提取
        if not auto_metadata:
            # 检查是否是BaseTool实例，如果是则使用其get_metadata()方法
            if hasattr(func, 'get_metadata') and callable(getattr(func, 'get_metadata')):
                try:
                    tool_metadata = func.get_metadata()
                    auto_metadata = {
                        "parameters": {},  # BaseTool使用input_parameters而不是parameters
                        "doc": tool_metadata.get("description", ""),
                        "capabilities": [],
                        "limitations": [],
                        "best_practices": [],
                        "use_cases": [],
                        "input_parameters": tool_metadata.get("input_parameters", {}),
                        "output_json_schema": tool_metadata.get("output_json_schema", ""),
                        "initial_prompt": "",
                    }
                except Exception as e:
                    self.logger.warning(f"无法获取工具 '{name}' 的metadata: {e}，使用inspect提取")
                    auto_metadata = None
            
            # 如果不是BaseTool或获取失败，使用inspect提取
            if not auto_metadata:
                sig = inspect.signature(func)
                auto_metadata = {
                    "parameters": {
                        param_name: {
                            "annotation": str(param.annotation) if param.annotation != inspect.Parameter.empty else "Any",
                            "default": param.default if param.default != inspect.Parameter.empty else None
                        }
                        for param_name, param in sig.parameters.items()
                    },
                    "doc": inspect.getdoc(func) or "",
                    "capabilities": [],
                    "limitations": [],
                    "best_practices": [],
                    "use_cases": [],
                    "input_parameters": {},
                    "output_json_schema": "",
                    "initial_prompt": "",
                }
        
        # 用户提供的metadata可以覆盖自动提取的
        if metadata:
            auto_metadata.update(metadata)
        
        self._metadata[name] = auto_metadata
    
    def get(self, name: str) -> Callable:
        """
        获取已注册的工具函数
        
        Args:
            name: 工具名称
            
        Returns:
            工具函数
            
        Raises:
            ToolNotFoundError: 工具未注册
        """
        if name not in self._tools:
            raise ToolNotFoundError(f"工具 '{name}' 未注册")
        return self._tools[name]
    
    def has(self, name: str) -> bool:
        """
        检查工具是否已注册
        
        Args:
            name: 工具名称
            
        Returns:
            是否已注册
        """
        return name in self._tools
    
    def get_metadata(self, name: str) -> Dict[str, Any]:
        """
        获取工具元数据
        
        Args:
            name: 工具名称
            
        Returns:
            工具元数据
        """
        return self._metadata.get(name, {})
    
    def list_tools(self) -> list:
        """
        列出所有已注册的工具
        
        Returns:
            工具名称列表
        """
        return list(self._tools.keys())
    
    def clear(self) -> None:
        """清空所有已注册的工具"""
        self._tools.clear()
        self._metadata.clear()
    
    def remove(self, name: str) -> None:
        """
        移除已注册的工具
        
        Args:
            name: 工具名称
        """
        if name in self._tools:
            del self._tools[name]
        if name in self._metadata:
            del self._metadata[name]
    
    def validate_tool_call(self, name: str, kwargs: Dict[str, Any]) -> bool:
        """
        验证工具调用参数
        
        Args:
            name: 工具名称
            kwargs: 调用参数
            
        Returns:
            是否验证通过
        """
        if not self.has(name):
            return False
        
        func = self.get(name)
        sig = inspect.signature(func)
        
        try:
            # 尝试绑定参数
            sig.bind(**kwargs)
            return True
        except TypeError:
            return False
    
    def get_tool_description(self, name: str) -> str:
        """
        生成工具的详细描述，供LLM使用
        
        Args:
            name: 工具名称
            
        Returns:
            格式化的工具描述字符串
        """
        if name not in self._metadata:
            return f"工具 '{name}' 无描述信息"
        
        meta = self._metadata[name]
        desc_parts = [f"工具名称: {name}"]
        
        # 功能描述
        if meta.get("doc"):
            desc_parts.append(f"功能描述: {meta['doc']}")
        
        # 参数信息（优先使用input_parameters，它排除了预配置的参数）
        if meta.get("input_parameters"):
            # 使用预定义的input_parameters（用于partial包装的工具）
            params = meta["input_parameters"]
            required_params = []
            optional_params = []
            
            for param_name, param_info in params.items():
                param_type = param_info.get("type", "Any")
                required = param_info.get("required", False)
                param_default = param_info.get("default")
                param_desc = param_info.get("description", "")
                
                if param_default is not None:
                    optional_params.append(f"  - {param_name}: {param_type} = {param_default}  # {param_desc}")
                elif required:
                    required_params.append(f"  - {param_name}: {param_type}  # {param_desc}")
                else:
                    optional_params.append(f"  - {param_name}: {param_type} (可选)  # {param_desc}")
            
            if required_params:
                desc_parts.append(f"⚠️ 必需参数（tool_input中必须包含）:")
                desc_parts.extend(required_params)
            if optional_params:
                desc_parts.append(f"可选参数:")
                desc_parts.extend(optional_params)
        elif meta.get("parameters"):
            # 使用自动提取的parameters
            params = meta["parameters"]
            param_strs = []
            for param_name, param_info in params.items():
                param_type = param_info.get("annotation", "Any")
                param_default = param_info.get("default")
                if param_default is not None:
                    param_strs.append(f"{param_name}: {param_type} = {param_default}")
                else:
                    param_strs.append(f"{param_name}: {param_type}")
            if param_strs:
                desc_parts.append(f"参数: {', '.join(param_strs)}")
        
        # 能力范围
        if meta.get("capabilities"):
            capabilities_str = "; ".join(meta["capabilities"])
            desc_parts.append(f"能力范围: {capabilities_str}")
        
        # 局限性
        if meta.get("limitations"):
            limitations_str = "; ".join(meta["limitations"])
            desc_parts.append(f"局限性: {limitations_str}")
        
        # 最佳实践
        if meta.get("best_practices"):
            practices_str = "; ".join(meta["best_practices"])
            desc_parts.append(f"最佳实践: {practices_str}")
        
        # 适用场景
        if meta.get("use_cases"):
            use_cases_str = "; ".join(meta["use_cases"])
            desc_parts.append(f"适用场景: {use_cases_str}")
        
        # 输出格式
        if meta.get("output_format"):
            desc_parts.append(f"输出格式: {meta['output_format']}")
        
        # 输出JSON Schema（重要：用于步骤间数据传递）
        if meta.get("output_json_schema"):
            schema = meta["output_json_schema"]
            desc_parts.append(f"输出JSON Schema: {schema}")
            # 解析schema提取字段名，帮助LLM理解如何引用
            try:
                import json
                schema_obj = json.loads(schema)
                if isinstance(schema_obj, dict) and "properties" in schema_obj:
                    fields = list(schema_obj["properties"].keys())
                    desc_parts.append(f"⚠️ 引用此工具输出时使用: {{{{steps.X.{fields[0]}}}}} (主要字段: {', '.join(fields)})")
            except (json.JSONDecodeError, KeyError, AttributeError):
                # Schema格式不标准或不是JSON，跳过字段提取
                pass
        
        # 错误处理
        if meta.get("error_handling"):
            desc_parts.append(f"错误处理: {meta['error_handling']}")
        
        # 初始prompt（ACE管理）
        if meta.get("initial_prompt"):
            desc_parts.append(f"初始Prompt: {meta['initial_prompt'][:100]}...")  # 只显示前100字符
        
        return "\n".join(desc_parts)
    
    def get_all_tools_description(self) -> str:
        """
        获取所有工具的描述
        
        Returns:
            所有工具的格式化描述字符串
        """
        if not self._tools:
            return "暂无可用工具"
        
        descriptions = []
        for name in sorted(self._tools.keys()):
            descriptions.append(self.get_tool_description(name))
            descriptions.append("-" * 60)
        
        # 移除最后一个分隔线
        if descriptions:
            descriptions.pop()
        
        return "\n".join(descriptions)


# 全局工具注册表实例
_global_registry = ToolRegistry()


def get_global_registry() -> ToolRegistry:
    """
    获取全局工具注册表
    
    Returns:
        全局ToolRegistry实例
    """
    return _global_registry


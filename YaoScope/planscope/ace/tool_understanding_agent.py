"""
工具理解Agent
自动分析工具代码并提取metadata，集成ACE机制学习和改进
支持工具metadata缓存和任务级配置持久化
"""
import inspect
import re
import ast
import json
import hashlib
from typing import Dict, Any, Callable, Optional, List
from pathlib import Path

from planscope.ace.context_manager import ContextManager
from planscope.ace.context_entry import ContextEntry, ContextEntryType


class ToolUnderstandingAgent:
    """
    工具理解Agent
    
    职责：
    1. 自动分析工具函数的代码、docstring、类型注解
    2. 提取完整的metadata（capabilities, limitations, best_practices, input_parameters, output_json_schema）
    3. 使用LLM理解工具的用途和限制
    4. 集成ACE机制，从执行反馈中学习和改进
    """
    
    # LLM分析工具的Prompt模板
    TOOL_ANALYSIS_PROMPT = """你是一个专业的代码分析专家。请分析以下Python工具函数，提取其功能、能力、限制和最佳实践。

工具名称: {tool_name}

函数签名:
{signature}

文档字符串:
{docstring}

源代码:
{source_code}

请严格按照以下JSON格式返回分析结果：
{{
  "capabilities": [
    "能力1的详细描述",
    "能力2的详细描述"
  ],
  "limitations": [
    "限制1的详细描述",
    "限制2的详细描述"
  ],
  "best_practices": [
    "最佳实践1",
    "最佳实践2"
  ],
  "tool_purpose": "工具的核心用途（一句话总结）",
  "use_cases": [
    "适用场景1",
    "适用场景2"
  ]
}}

分析要求：
1. **capabilities**: 列出工具能做什么，具体功能点
2. **limitations**: 列出工具的局限性、不擅长的事情、注意事项
3. **best_practices**: 如何正确使用这个工具，什么场景下使用
4. **tool_purpose**: 用一句话概括工具的核心目的
5. **use_cases**: 列出2-3个典型的使用场景

只返回JSON，不要有其他说明文字。"""
    
    def __init__(self, 
                 model_client,
                 context_manager: Optional[ContextManager],
                 logger,
                 task_name: str = "default",
                 tools_config_dir: str = "./config/tools",
                 storage_manager=None):
        """
        初始化工具理解Agent
        
        Args:
            model_client: AgentScope模型客户端
            context_manager: ACE上下文管理器（用于学习和复用）
            logger: 日志记录器
            task_name: 任务名称（用于隔离不同任务的工具配置）
            tools_config_dir: 工具配置根目录
            storage_manager: 存储管理器（可选，优先使用）
        """
        self.model_client = model_client
        self.context_manager = context_manager
        self.logger = logger
        self.task_name = task_name
        self.storage_manager = storage_manager
        
        # 任务级工具配置目录
        self.tools_config_dir = Path(tools_config_dir) / task_name
        self.tools_config_dir.mkdir(parents=True, exist_ok=True)
        
        # 工具metadata缓存文件
        self.metadata_cache_file = self.tools_config_dir / "tool_metadata_cache.json"
        
        # 加载已缓存的metadata
        self._metadata_cache = self._load_metadata_cache()
    
    def _load_metadata_cache(self) -> Dict[str, Any]:
        """加载工具metadata缓存"""
        if self.metadata_cache_file.exists():
            try:
                with open(self.metadata_cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                self.logger.info(f"[ToolUnderstandingAgent] 加载metadata缓存: {len(cache)}个工具")
                return cache
            except Exception as e:
                self.logger.warning(f"[ToolUnderstandingAgent] 加载metadata缓存失败: {e}")
        return {}
    
    def _save_metadata_cache(self):
        """保存工具metadata缓存（过滤不可序列化对象）"""
        import copy
        try:
            # 创建可序列化的缓存副本（深拷贝）
            serializable_cache = {}
            for tool_name, cache_data in self._metadata_cache.items():
                try:
                    serializable_data = copy.deepcopy(cache_data)
                    
                    # 过滤metadata中的不可序列化对象
                    if "metadata" in serializable_data and isinstance(serializable_data["metadata"], dict):
                        metadata = serializable_data["metadata"]
                        
                        # 过滤input_parameters中的不可序列化对象（如model_client）
                        if "input_parameters" in metadata and isinstance(metadata["input_parameters"], dict):
                            filtered_params = {}
                            for param_name, param_info in metadata["input_parameters"].items():
                                # 尝试序列化每个参数，如果失败则跳过
                                try:
                                    json.dumps(param_info)
                                    filtered_params[param_name] = param_info
                                except (TypeError, ValueError):
                                    # 跳过不可序列化的参数（如包含model_client的参数）
                                    self.logger.debug(f"跳过不可序列化参数: {param_name}")
                            metadata["input_parameters"] = filtered_params
                    
                    serializable_cache[tool_name] = serializable_data
                except Exception as e:
                    # 如果某个工具的metadata无法处理，跳过它但继续处理其他工具
                    self.logger.debug(f"跳过无法序列化的工具metadata: {tool_name}, {e}")
                    continue
            
            with open(self.metadata_cache_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_cache, f, indent=2, ensure_ascii=False)
            self.logger.debug(f"[ToolUnderstandingAgent] metadata缓存已保存（{len(serializable_cache)}个工具）")
        except Exception as e:
            # 缓存保存失败不影响功能，只记录debug日志
            self.logger.debug(f"[ToolUnderstandingAgent] metadata缓存保存失败（不影响功能）: {e}")
    
    def _get_tool_hash(self, source_code: str) -> str:
        """计算工具代码的hash值，用于判断代码是否变化"""
        return hashlib.md5(source_code.encode('utf-8')).hexdigest()
    
    async def analyze_tool(self, tool_name: str, tool_func: Callable, force_reanalyze: bool = False) -> Dict[str, Any]:
        """
        分析工具并提取完整metadata
        
        如果工具已经成功分析过且代码未变化，直接使用缓存
        
        Args:
            tool_name: 工具名称
            tool_func: 工具函数
            force_reanalyze: 是否强制重新分析（默认False）
            
        Returns:
            完整的metadata字典
        """
        # 1. 首先检查storage_manager缓存（最优先）
        if not force_reanalyze and self.storage_manager:
            cached = self.storage_manager.load_tool_metadata(tool_name)
            if cached:
                self.logger.info(f"[ToolUnderstandingAgent] 使用缓存的metadata: {tool_name}")
                # 更新内存缓存
                self._metadata_cache[tool_name] = {
                    "metadata": cached,
                    "analysis_success": True,
                    "code_hash": cached.get("code_hash", "")
                }
                return cached
        
        self.logger.info(f"[ToolUnderstandingAgent] 开始分析工具: {tool_name}")
        
        try:
            # 2. 提取代码信息
            source_code = self._get_source_code(tool_func)
            docstring = inspect.getdoc(tool_func) or ""
            signature = str(inspect.signature(tool_func))
            
            # 3. 计算代码hash
            code_hash = self._get_tool_hash(source_code)
            
            # 4. 检查本地缓存（如果不是强制重新分析）
            if not force_reanalyze and tool_name in self._metadata_cache:
                cached_data = self._metadata_cache[tool_name]
                cached_hash = cached_data.get("code_hash")
                
                # 如果代码未变化且分析成功过，使用缓存
                if cached_hash == code_hash and cached_data.get("analysis_success"):
                    self.logger.info(f"[ToolUnderstandingAgent] 使用本地缓存的metadata: {tool_name}")
                    return cached_data.get("metadata", {})
            
            # 4. 提取input_parameters（从类型注解和docstring）
            input_parameters = self._extract_input_parameters(tool_func, source_code, docstring)
            
            # 5. 提取output_json_schema（从源代码中的常量定义）
            output_json_schema = self._extract_output_schema(tool_func, source_code)
            
            # 6. 查找是否有历史成功案例（ACE复用）
            similar_analysis = None
            if self.context_manager:
                similar_analysis = self._find_similar_tool_analysis(tool_name, source_code)
            
            # 7. 使用LLM分析工具（提取capabilities, limitations, best_practices）
            llm_metadata = await self._llm_analyze_tool(
                tool_name, source_code, docstring, signature, similar_analysis
            )
            
            # 8. 组合完整的metadata
            metadata = {
                "capabilities": llm_metadata.get("capabilities", []),
                "limitations": llm_metadata.get("limitations", []),
                "best_practices": llm_metadata.get("best_practices", []),
                "use_cases": llm_metadata.get("use_cases", []),
                "tool_purpose": llm_metadata.get("tool_purpose", ""),
                "input_parameters": input_parameters,
                "output_json_schema": output_json_schema,
                "doc": docstring,
                "signature": signature
            }
            
            # 9. 验证提取的metadata
            validated_metadata = self._validate_metadata(metadata, tool_func)
            
            self.logger.info(f"[ToolUnderstandingAgent] 工具分析完成: {tool_name}")
            self.logger.debug(f"  - capabilities: {len(validated_metadata.get('capabilities', []))}项")
            self.logger.debug(f"  - limitations: {len(validated_metadata.get('limitations', []))}项")
            self.logger.debug(f"  - input_parameters: {len(validated_metadata.get('input_parameters', {}))}个")
            self.logger.debug(f"  - output_json_schema: {'已提取' if validated_metadata.get('output_json_schema') else '未找到'}")
            
            # 10. 保存到缓存
            self._metadata_cache[tool_name] = {
                "metadata": validated_metadata,
                "code_hash": code_hash,
                "analysis_success": True,
                "task_name": self.task_name
            }
            self._save_metadata_cache()
            self.logger.info(f"[ToolUnderstandingAgent] metadata已缓存: {tool_name}")
            
            # 11. 记录成功的分析（供ACE学习）
            if self.context_manager:
                self._record_successful_analysis(tool_name, validated_metadata, source_code)
            
            return validated_metadata
            
        except Exception as e:
            self.logger.error(f"[ToolUnderstandingAgent] 工具分析失败: {tool_name}, 错误: {str(e)}")
            # 返回基础metadata
            return self._get_fallback_metadata(tool_func)
    
    def _get_source_code(self, tool_func: Callable) -> str:
        """获取工具函数的源代码（智能处理partial函数）"""
        try:
            # 如果是partial函数，尝试获取原始函数的源代码
            from functools import partial
            if isinstance(tool_func, partial):
                self.logger.info(f"检测到partial函数，尝试获取原始函数源代码")
                return inspect.getsource(tool_func.func)
            else:
                return inspect.getsource(tool_func)
        except Exception as e:
            self.logger.warning(f"无法获取源代码: {str(e)}")
            return ""
    
    def _extract_input_parameters(self, 
                                  tool_func: Callable,
                                  source_code: str,
                                  docstring: str) -> Dict[str, Any]:
        """
        从BaseTool子类提取INPUT_PARAMETERS
        
        要求：所有工具必须继承BaseTool并定义INPUT_PARAMETERS类属性
        通过调用 get_metadata() 统一获取元数据，避免属性访问歧义
        """
        try:
            # 策略1: 如果是绑定方法（实例的execute方法）
            if hasattr(tool_func, '__self__'):
                tool_instance = tool_func.__self__
                tool_class = tool_instance.__class__
                if hasattr(tool_class, 'get_metadata'):
                    metadata = tool_class.get_metadata()
                    params = metadata.get('input_parameters', {})
                    if params:
                        self.logger.debug(f"从{tool_class.__name__}.get_metadata()提取到input_parameters")
                        return params
            
            # 策略2: 从模块中查找BaseTool子类
            tool_module = inspect.getmodule(tool_func)
            if tool_module:
                for name in dir(tool_module):
                    obj = getattr(tool_module, name)
                    if (inspect.isclass(obj) and 
                        hasattr(obj, 'get_metadata') and
                        obj.__name__.endswith('Tool')):
                        try:
                            metadata = obj.get_metadata()
                            params = metadata.get('input_parameters', {})
                            if params:
                                self.logger.debug(f"从{obj.__name__}.get_metadata()提取到input_parameters")
                                return params
                        except Exception:
                            continue
        except Exception as e:
            self.logger.error(f"提取input_parameters失败: {str(e)}")
            # 遵循No Fallback原则
            raise ValueError(f"工具必须继承BaseTool并定义INPUT_PARAMETERS: {str(e)}")
        
        # 如果到这里还没找到，说明工具不符合规范
        raise ValueError(
            f"工具 {tool_func.__name__} 不符合规范：\n"
            f"1. 必须继承BaseTool\n"
            f"2. 必须定义INPUT_PARAMETERS类属性\n"
            f"3. 必须实现get_metadata()类方法"
        )
    
    
    def _extract_output_schema(self, tool_func: Callable, source_code: str) -> str:
        """
        从BaseTool子类提取OUTPUT_JSON_SCHEMA
        
        要求：所有工具必须继承BaseTool并定义OUTPUT_JSON_SCHEMA类属性
        通过调用 get_metadata() 统一获取元数据，避免属性访问歧义
        """
        try:
            # 策略1: 如果是绑定方法（实例的execute方法）
            if hasattr(tool_func, '__self__'):
                tool_instance = tool_func.__self__
                tool_class = tool_instance.__class__
                if hasattr(tool_class, 'get_metadata'):
                    metadata = tool_class.get_metadata()
                    schema = metadata.get('output_json_schema', '')
                    if schema:
                        self.logger.debug(f"从{tool_class.__name__}.get_metadata()提取到output_json_schema")
                        return schema
            
            # 策略2: 从模块中查找BaseTool子类
            tool_module = inspect.getmodule(tool_func)
            if tool_module:
                for name in dir(tool_module):
                    obj = getattr(tool_module, name)
                    if (inspect.isclass(obj) and 
                        hasattr(obj, 'get_metadata') and
                        obj.__name__.endswith('Tool')):
                        try:
                            metadata = obj.get_metadata()
                            schema = metadata.get('output_json_schema', '')
                            if schema:
                                self.logger.debug(f"从{obj.__name__}.get_metadata()提取到output_json_schema")
                                return schema
                        except Exception:
                            continue
        except Exception as e:
            self.logger.error(f"提取output_json_schema失败: {str(e)}")
            # 遵循No Fallback原则，不返回默认值
            raise ValueError(f"工具必须继承BaseTool并定义OUTPUT_JSON_SCHEMA: {str(e)}")
        
        # 如果到这里还没找到，说明工具不符合规范
        raise ValueError(
            f"工具 {tool_func.__name__} 不符合规范：\n"
            f"1. 必须继承BaseTool\n"
            f"2. 必须定义OUTPUT_JSON_SCHEMA类属性\n"
            f"3. 必须实现get_metadata()类方法"
        )
    
    def _find_similar_tool_analysis(self, tool_name: str, source_code: str) -> Optional[Dict[str, Any]]:
        """
        查找类似工具的历史分析结果（ACE复用）
        
        Args:
            tool_name: 工具名称
            source_code: 源代码
            
        Returns:
            历史分析结果或None
        """
        if not self.context_manager:
            return None
        
        try:
            # 查找TOOL_UNDERSTANDING类型的成功案例
            entries = self.context_manager.get_entries_by_type(ContextEntryType.TOOL_UNDERSTANDING)
            
            for entry in entries:
                if entry.metadata.get("success") and entry.metadata.get("tool_name") == tool_name:
                    self.logger.info(f"找到工具 {tool_name} 的历史分析结果，复用")
                    return entry.metadata.get("extracted_metadata")
            
        except Exception as e:
            self.logger.debug(f"查找历史分析失败: {str(e)}")
        
        return None
    
    async def _llm_analyze_tool(self,
                                tool_name: str,
                                source_code: str,
                                docstring: str,
                                signature: str,
                                similar_analysis: Optional[Dict]) -> Dict[str, Any]:
        """
        使用LLM分析工具代码，提取结构化metadata
        
        Args:
            tool_name: 工具名称
            source_code: 源代码
            docstring: 文档字符串
            signature: 函数签名
            similar_analysis: 历史分析结果（可选）
            
        Returns:
            LLM分析的metadata
        """
        # 如果有历史分析结果，直接复用
        if similar_analysis:
            return similar_analysis
        
        # 构建分析prompt
        prompt = self.TOOL_ANALYSIS_PROMPT.format(
            tool_name=tool_name,
            signature=signature,
            docstring=docstring if docstring else "无文档字符串",
            source_code=source_code[:2000]  # 限制长度
        )
        
        try:
            # 调用LLM
            result = await self.model_client.call_model_with_json_response(prompt=prompt)
            
            self.logger.debug(f"LLM分析完成: {tool_name}")
            return result
            
        except Exception as e:
            self.logger.error(f"LLM分析失败: {str(e)}")
            # 返回空结果
            return {
                "capabilities": [],
                "limitations": [],
                "best_practices": [],
                "use_cases": [],
                "tool_purpose": ""
            }
    
    def _validate_metadata(self, metadata: Dict[str, Any], tool_func: Callable) -> Dict[str, Any]:
        """
        验证提取的metadata
        
        确保必需字段存在，格式正确
        """
        validated = {}
        
        # 确保列表字段存在
        for field in ["capabilities", "limitations", "best_practices", "use_cases"]:
            validated[field] = metadata.get(field, [])
            if not isinstance(validated[field], list):
                validated[field] = []
        
        # 确保字符串字段存在
        for field in ["tool_purpose", "output_json_schema", "doc", "signature"]:
            validated[field] = metadata.get(field, "")
            if not isinstance(validated[field], str):
                validated[field] = str(validated[field])
        
        # 确保input_parameters是字典
        validated["input_parameters"] = metadata.get("input_parameters", {})
        if not isinstance(validated["input_parameters"], dict):
            validated["input_parameters"] = {}
        
        return validated
    
    def _get_fallback_metadata(self, tool_func: Callable) -> Dict[str, Any]:
        """
        获取降级的基础metadata（当分析失败时）
        """
        sig = inspect.signature(tool_func)
        docstring = inspect.getdoc(tool_func) or ""
        
        return {
            "capabilities": [],
            "limitations": [],
            "best_practices": [],
            "use_cases": [],
            "tool_purpose": "",
            "input_parameters": {},
            "output_json_schema": "",
            "doc": docstring,
            "signature": str(sig)
        }
    
    def _record_successful_analysis(self, 
                                   tool_name: str,
                                   metadata: Dict[str, Any],
                                   source_code: str):
        """
        记录成功的分析结果（供ACE学习）
        """
        if not self.context_manager:
            return
        
        try:
            entry = ContextEntry(
                entry_type=ContextEntryType.TOOL_UNDERSTANDING,
                task_description=f"分析工具: {tool_name}",
                metadata={
                    "tool_name": tool_name,
                    "extracted_metadata": metadata,
                    "success": True,
                    "source_code_hash": hash(source_code)
                }
            )
            
            self.context_manager.add_entry(entry)
            self.logger.debug(f"记录工具分析成功案例: {tool_name}")
            
        except Exception as e:
            self.logger.debug(f"记录分析结果失败: {str(e)}")
    
    def record_extraction_feedback(self,
                                   tool_name: str,
                                   extracted_metadata: Dict[str, Any],
                                   execution_result: Dict[str, Any],
                                   success: bool):
        """
        记录提取反馈，供ACE学习
        
        Args:
            tool_name: 工具名称
            extracted_metadata: 提取的metadata
            execution_result: 执行结果
            success: 是否成功
        """
        if not self.context_manager:
            return
        
        try:
            entry = ContextEntry(
                entry_type=ContextEntryType.TOOL_UNDERSTANDING,
                task_description=f"工具执行反馈: {tool_name}",
                metadata={
                    "tool_name": tool_name,
                    "extracted_metadata": extracted_metadata,
                    "execution_success": success,
                    "execution_error": execution_result.get("error") if not success else None,
                    "feedback_type": "execution_result"
                }
            )
            
            # 如果失败，分析原因
            if not success:
                improvement = self._analyze_extraction_failure(
                    tool_name, extracted_metadata, execution_result
                )
                entry.metadata["improvement_suggestion"] = improvement
            
            self.context_manager.add_entry(entry)
            self.logger.info(f"记录工具执行反馈: {tool_name}, 成功={success}")
            
        except Exception as e:
            self.logger.error(f"记录执行反馈失败: {str(e)}")
    
    def _analyze_extraction_failure(self,
                                   tool_name: str,
                                   extracted_metadata: Dict[str, Any],
                                   execution_result: Dict[str, Any]) -> str:
        """
        分析提取失败的原因，生成改进建议
        
        Returns:
            改进建议字符串
        """
        error = execution_result.get("error", "")
        
        suggestions = []
        
        # 分析错误类型
        if "missing" in error.lower() or "required" in error.lower():
            suggestions.append("input_parameters可能缺少必需参数定义")
        
        if "type" in error.lower() or "expected" in error.lower():
            suggestions.append("input_parameters的类型定义可能不准确")
        
        if "json" in error.lower() or "format" in error.lower():
            suggestions.append("output_json_schema可能与实际输出不匹配")
        
        if not suggestions:
            suggestions.append("需要检查工具的metadata定义是否完整")
        
        return "; ".join(suggestions)


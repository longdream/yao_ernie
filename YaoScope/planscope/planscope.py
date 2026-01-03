"""
PlanScope主类
提供简洁的API接口用于工作流生成和执行
"""
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from planscope.adapters import ConfigManager, LoggerManager
from planscope.adapters.langchain_client import LangChainModelClient
from planscope.adapters.exceptions import ErnieAgentException

from planscope.core.exceptions import PlanScopeError
from planscope.core.plan_generator import PlanGenerator
from planscope.core.plan_parser import PlanParser
from planscope.core.plan_executor import PlanExecutor
from planscope.core.storage_manager import StorageManager
from planscope.tools.tool_registry import ToolRegistry, get_global_registry


class PlanScope:
    """
    PlanScope - 基于LangChain的工作流引擎
    
    特点:
    - 自动生成: 通过LLM根据需求生成工作流JSON
    - 依赖解析: 自动分析依赖关系，拓扑排序执行
    - 变量替换: 支持步骤间的数据传递 {steps.X.field}
    - 工具注册: 装饰器模式注册工具函数
    - 流程持久化: 保存和加载工作流JSON
    """
    
    def __init__(self, config: Dict[str, Any], work_dir: str = "./planscope_data", use_ace: bool = True, task_name: str = "default"):
        """
        初始化PlanScope
        
        Args:
            config: 配置字典，与ReadScope相同的格式
            work_dir: 工作目录，用于存储流程文件和日志
            use_ace: 是否启用ACE框架（默认True）
            task_name: 任务名称，用于隔离不同任务的工具配置（默认"default"）
            
        Example:
            >>> ps = PlanScope(
            ...     config={
            ...         "llm": {...},
            ...         "embedding": {...},
            ...         "reranker": {...}
            ...     },
            ...     work_dir="./planscope_data",
            ...     use_ace=True,
            ...     task_name="chat_analysis"
            ... )
        """
        self.work_dir = Path(work_dir).absolute()  # 确保使用绝对路径
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.use_ace = use_ace
        self.task_name = task_name
        
        # 初始化存储管理器（统一管理文件夹结构）
        self.storage_manager = StorageManager(str(self.work_dir))
        
        # 初始化配置管理器
        self.config_manager = ConfigManager.from_dict(config, str(self.work_dir))
        
        # 初始化日志管理器
        logging_config = self.config_manager.get_logging_config()
        self.logger_manager = LoggerManager(logging_config)
        self.logger = self.logger_manager.get_logger("planscope")
        
        self.logger.info("=" * 80)
        self.logger.info(f"PlanScope初始化开始 (ACE: {'启用' if use_ace else '禁用'})")
        self.logger.info(f"工作目录: {self.work_dir}")
        
        # 初始化LangChain模型客户端（传入embedding配置）
        try:
            # 提取embedding配置
            embedding_config = config.get("embedding")
            
            self.model_client = LangChainModelClient(
                self.config_manager,
                self.logger_manager,
                embedding_config=embedding_config
            )
            self.logger.info("LangChain模型客户端初始化成功")
        except Exception as e:
            self.logger.error(f"LangChain模型客户端初始化失败: {e}")
            raise ErnieAgentException(f"LangChain模型客户端初始化失败: {e}")
        
        # 初始化Plan专用的model client（如果配置了plan_llm）
        self.plan_model_client = None
        if use_ace:
            plan_llm_config = config.get("plan_llm")
            if plan_llm_config:
                try:
                    # 创建临时ConfigManager来包装plan_llm配置
                    # plan_llm配置应该包含所有必要的字段
                    plan_config = {
                        "llm": plan_llm_config,  # 将plan_llm配置作为主LLM配置
                        "embedding": config.get("embedding", {}),  # 可选的embedding配置
                        "reranker": config.get("reranker", {})  # 可选的reranker配置
                    }
                    
                    # 创建临时ConfigManager（已在文件开头导入）
                    temp_config_manager = ConfigManager.from_dict(plan_config, work_dir)
                    
                    self.plan_model_client = LangChainModelClient(
                        temp_config_manager,
                        self.logger_manager,
                        embedding_config=embedding_config  # 传入embedding配置
                    )
                    self.logger.info(f"Plan专用模型初始化成功: {plan_llm_config.get('model_name')}")
                except Exception as e:
                    # Plan专用模型初始化失败，抛出异常（不允许fallback）
                    error_msg = f"Plan专用模型(plan_llm)初始化失败: {e}\n配置: {plan_llm_config}"
                    self.logger.error(error_msg)
                    raise PlanScopeError(error_msg) from e
        
        # 初始化工具注册表（必须在核心组件之前）
        self.tool_registry = get_global_registry()
        
        # 初始化工具池（用于存储可用但未注册的工具）
        self.tool_pool: Dict[str, Dict[str, Any]] = {}
        
        # 初始化核心组件
        try:
            if use_ace:
                # 导入ACE组件
                from planscope.ace.context_manager import ContextManager
                from planscope.ace.task_matcher import TaskMatcher
                from planscope.ace.generator import ACEGenerator
                from planscope.ace.reflector import ACEReflector
                from planscope.ace.curator import ACECurator
                from planscope.ace.llm_analyzer import LLMAnalyzer
                from planscope.core.ace_plan_generator import ACEPlanGenerator
                from planscope.ace.tool_understanding_agent import ToolUnderstandingAgent
                
                # 初始化LLM分析器（核心组件）
                # 注意：embedding_client使用model_client的embedding功能
                self.llm_analyzer = LLMAnalyzer(
                    model_client=self.model_client,
                    embedding_client=self.model_client,  # 使用同一个client
                    logger_manager=self.logger_manager,
                    cache_dir=str(self.storage_manager.get_path("llm_cache")),
                    storage_manager=self.storage_manager
                )
                
                # 初始化向量数据库管理器
                from planscope.ace.vector_db_manager import VectorDBManager
                vector_db_path = str(self.work_dir / "vector_db")
                
                try:
                    self.logger.info("正在初始化向量数据库管理器...")
                    self.vector_db_manager = VectorDBManager(
                        persist_directory=vector_db_path,
                        embedding_client=self.model_client,  # 用于计算embedding
                        logger_manager=self.logger_manager
                    )
                    self.logger.info(f"向量数据库管理器初始化完成: {vector_db_path}")
                except Exception as e:
                    error_msg = f"向量数据库初始化失败，PlanScope无法启动: {str(e)}"
                    self.logger.error(error_msg)
                    raise PlanScopeError(error_msg) from e
                
                # 初始化ACE组件（使用StorageManager的路径）
                self.context_manager = ContextManager(
                    str(self.storage_manager.get_path("contexts")),
                    llm_analyzer=self.llm_analyzer,
                    storage_manager=self.storage_manager
                )
                self.task_matcher = TaskMatcher(
                    str(self.storage_manager.get_path("persistent")),
                    self.logger_manager,
                    llm_analyzer=self.llm_analyzer,
                    storage_manager=self.storage_manager,
                    vector_db_manager=self.vector_db_manager  # 传入向量数据库管理器
                )
                self.ace_generator = ACEGenerator(
                    self.logger_manager, 
                    str(self.storage_manager.get_path("persistent")),
                    storage_manager=self.storage_manager
                )
                self.ace_reflector = ACEReflector(
                    self.model_client,
                    self.logger_manager
                )
                self.ace_curator = ACECurator(self.context_manager, self.logger_manager)
                
                # 初始化ToolUnderstandingAgent（传递task_name用于任务级配置隔离）
                self.tool_understanding_agent = ToolUnderstandingAgent(
                    model_client=self.model_client,
                    context_manager=self.context_manager,
                    logger=self.logger_manager.get_logger("ace.tool_understanding"),
                    task_name=self.task_name,
                    tools_config_dir=str(self.storage_manager.get_path("tools")),
                    storage_manager=self.storage_manager
                )
                
                # 将ToolUnderstandingAgent传递给ToolRegistry
                self.tool_registry.tool_understanding_agent = self.tool_understanding_agent
                
                self.logger.info(f"ToolUnderstandingAgent初始化成功 (任务: {self.task_name})")
                
                # 初始化ToolGenerator（传递task_name用于任务级工具隔离）
                from planscope.ace.tool_generator import ToolGenerator
                self.tool_generator = ToolGenerator(
                    model_client=self.model_client,
                    tool_registry=self.tool_registry,
                    logger=self.logger_manager.get_logger("ace.tool_generator"),
                    work_dir=str(self.storage_manager.get_path("tools")),
                    task_name=self.task_name
                )
                
                # 使用ACEPlanGenerator（使用plan_model_client或默认LLM）
                plan_client = self.plan_model_client if self.plan_model_client else self.model_client
                self.plan_generator = ACEPlanGenerator(
                    plan_client,
                    self.logger_manager,
                    str(self.storage_manager.get_path("persistent")),
                    self.context_manager,
                    self.task_matcher,
                    self.tool_registry,
                    storage_manager=self.storage_manager
                )
                
                # 将tool_generator传递给plan_generator
                self.plan_generator.tool_generator = self.tool_generator
                
                # 使用带ACE的PlanExecutor
                self.plan_executor = PlanExecutor(
                    self.logger_manager, 
                    self.ace_generator, 
                    storage_manager=self.storage_manager
                )
                
                self.logger.info("ACE组件初始化成功")
            else:
                # 使用原有的PlanGenerator
                self.plan_generator = PlanGenerator(
                    self.model_client,
                    self.logger_manager,
                    str(self.work_dir),
                    storage_manager=self.storage_manager
                )
                self.plan_executor = PlanExecutor(self.logger_manager)
                
                self.logger.info("使用标准PlanGenerator")
            
            self.plan_parser = PlanParser(self.logger_manager)
            
            self.logger.info("核心组件初始化成功")
        except Exception as e:
            self.logger.error(f"核心组件初始化失败: {e}")
            raise PlanScopeError(f"核心组件初始化失败: {e}")
        
        self.logger.info("PlanScope初始化完成")
        self.logger.info("=" * 80)
    
    def generate_plan(self,
                     prompt: str,
                     prompt_template: Optional[str] = None,
                     save_to_file: bool = True,
                     session_id: Optional[str] = None,
                     **kwargs) -> Dict[str, Any]:
        """
        生成工作流计划
        
        工作流程：
        1. 检查工具库是否为空
        2. LLM从工具库筛选2-5个最相关的工具
        3. 动态注册筛选出的工具
        4. 使用筛选后的工具生成plan
        
        Args:
            prompt: 用户需求描述
            prompt_template: 自定义prompt模板（可选）
            save_to_file: 是否保存到文件
            **kwargs: 传递给LLM的额外参数（如temperature, max_tokens）
            
        Returns:
            工作流JSON对象
            
        Raises:
            PlanScopeError: 生成失败
            
        Example:
            >>> # 先添加工具到工具库
            >>> ps.add_tool_to_pool("tool1", func1, "描述1")
            >>> ps.add_tool_to_pool("tool2", func2, "描述2")
            >>> 
            >>> # 生成plan（LLM自动筛选工具）
            >>> plan = ps.generate_plan("请查看聊天记录并生成回复")
        """
        self.logger.info(f"生成工作流计划: {prompt}")
        
        try:
            # 步骤0: 尝试精确匹配历史plan（最快路径）
            if self.task_matcher:
                cached_plan = self.task_matcher.find_exact_match_plan(prompt)
                if cached_plan:
                    self.logger.info("找到完全匹配的历史plan，直接复用")
                    # 保持原有的flow_id，不生成新的
                    # 这样用户在Settings页面编辑的plan会被直接使用
                    original_flow_id = cached_plan.get("flow_id", "unknown")
                    self.logger.info(f"复用原有flow_id: {original_flow_id}")
                    
                    # 重要：注册plan中使用的工具（从tool_pool获取）
                    plan_tool_names = set()
                    for step in cached_plan.get("steps", []):
                        tool_name = step.get("tool")
                        if tool_name:
                            plan_tool_names.add(tool_name)
                    
                    if plan_tool_names:
                        self.logger.info(f"注册复用plan所需的工具: {plan_tool_names}")
                        for tool_name in plan_tool_names:
                            if tool_name in self.tool_pool:
                                tool_data = self.tool_pool[tool_name]
                                self.tool_registry.add(
                                    tool_name,
                                    tool_data["func"],
                                    metadata={
                                        "description": tool_data.get("description", ""),
                                        "tool_type": tool_data.get("tool_type", "function"),
                                        "input_parameters": tool_data.get("input_parameters", {}),
                                        "output_json_schema": tool_data.get("output_json_schema", "")
                                    }
                                )
                                self.logger.info(f"✓ 工具 '{tool_name}' 已从tool_pool注册到tool_registry")
                            else:
                                self.logger.warning(f"工具 '{tool_name}' 不在tool_pool中")
                    
                    # ACE优化注入：即使复用缓存plan，也要应用最新的优化prompt
                    if self.use_ace and self.context_manager:
                        self.logger.info("检查是否有ACE优化的prompt需要注入...")
                        relevant_entries = self.context_manager.retrieve_relevant_entries(
                            prompt, 
                            task_type="document_analysis",
                            top_k=5
                        )
                        if relevant_entries:
                            self.logger.info(f"检索到 {len(relevant_entries)} 个相关context条目")
                            # 调用ACEPlanGenerator的注入方法
                            cached_plan = self.plan_generator._inject_optimized_prompts(
                                cached_plan, 
                                relevant_entries
                            )
                            self.logger.info("✓ 已将最新优化prompt注入到缓存plan")
                        else:
                            self.logger.info("未找到相关优化prompt，使用原始plan")
                    
                    return cached_plan
            
            # 检查：如果工具库为空且没有已注册工具，抛出异常
            if not self.tool_pool and not self.tool_registry.list_tools():
                error_msg = "工具库为空，请先使用 add_tool_to_pool() 添加工具"
                self.logger.error(error_msg)
                raise PlanScopeError(error_msg)
            
            # 如果工具库不为空，强制使用工具推荐流程
            if self.tool_pool:
                self.logger.info("=" * 80)
                self.logger.info("步骤1: LLM分析用户需求并筛选工具")
                self.logger.info("=" * 80)
                
                # 发布进度状态
                if session_id:
                    try:
                        from service.core.progress_manager import ProgressManager
                        pm = ProgressManager.get_instance()
                        pm.publish(session_id, "tool_selection", "正在筛选工具...")
                    except Exception as e:
                        self.logger.debug(f"发布进度失败: {e}")
                
                # 创建工具推荐器
                from planscope.core.tool_recommender import ToolRecommender
                recommender = ToolRecommender(
                    self.model_client,
                    self.logger,
                    self.tool_pool
                )
                
                # 推荐工具
                recommended_tools = asyncio.run(recommender.recommend_tools(prompt))
                
                if not recommended_tools:
                    error_msg = "LLM未推荐任何工具，无法生成plan"
                    self.logger.error(error_msg)
                    raise PlanScopeError(error_msg)
                
                self.logger.info(f"LLM推荐了 {len(recommended_tools)} 个工具: {recommended_tools}")
                
                # 动态注册推荐的工具
                self.logger.info("=" * 80)
                self.logger.info("步骤2: 动态注册推荐的工具并提取metadata")
                self.logger.info("=" * 80)
                
                # 发布进度状态
                if session_id:
                    try:
                        from service.core.progress_manager import ProgressManager
                        pm = ProgressManager.get_instance()
                        pm.publish(session_id, "metadata_analysis", "正在分析工具...")
                    except Exception as e:
                        self.logger.debug(f"发布进度失败: {e}")
                
                for tool_name in recommended_tools:
                    if tool_name in self.tool_pool:
                        if not self.tool_registry.has(tool_name):
                            tool_info = self.tool_pool[tool_name]
                            
                            self.logger.info(f"正在注册工具: {tool_name}")
                            
                            # 直接传递完整metadata，避免事后修改
                            self.tool_registry.add(
                                tool_name,
                                tool_info["func"],
                                metadata={
                                    "output_json_schema": tool_info.get("output_json_schema", ""),
                                    "input_parameters": tool_info.get("input_parameters", {}),
                                    "tool_type": tool_info.get("tool_type", "function"),
                                    "description": tool_info.get("description", "")
                                }
                            )
                            self.logger.info(f"✓ 工具 '{tool_name}' 已注册")
                        else:
                            self.logger.debug(f"工具 '{tool_name}' 已存在，跳过注册")
                    else:
                        self.logger.warning(f"工具 '{tool_name}' 不在工具池中，跳过")
            
            # 生成工作流
            self.logger.info("=" * 80)
            self.logger.info("步骤3: 生成工作流计划（使用已注册的工具）")
            self.logger.info("=" * 80)
            
            # 发布进度状态
            if session_id:
                try:
                    from service.core.progress_manager import ProgressManager
                    pm = ProgressManager.get_instance()
                    pm.publish(session_id, "plan_generation", "正在生成工作流...")
                except Exception as e:
                    self.logger.debug(f"发布进度失败: {e}")
            
            # 使用asyncio运行异步方法
            plan_json = asyncio.run(
                self.plan_generator.generate(
                    user_prompt=prompt,
                    prompt_template=prompt_template,
                    save_to_file=save_to_file,
                    **kwargs
                )
            )
            
            # 重要：检查plan中所需的工具是否都已注册（特别是复用历史plan的情况）
            plan_tool_names = set()
            for step in plan_json.get("steps", []):
                tool_name = step.get("tool")
                if tool_name:
                    plan_tool_names.add(tool_name)
            
            # 注册缺失的工具
            missing_tools = plan_tool_names - set(self.tool_registry.list_tools())
            if missing_tools:
                self.logger.info(f"发现plan需要但未注册的工具: {missing_tools}，正在注册...")
                for tool_name in missing_tools:
                    if tool_name in self.tool_pool:
                        tool_info = self.tool_pool[tool_name]
                        self.tool_registry.add(
                            tool_name,
                            tool_info["func"],
                            metadata={
                                "output_json_schema": tool_info.get("output_json_schema", ""),
                                "input_parameters": tool_info.get("input_parameters", {}),
                                "tool_type": tool_info.get("tool_type", "function"),
                                "description": tool_info.get("description", "")
                            }
                        )
                        self.logger.info(f"✓ 工具 '{tool_name}' 已补充注册")
                    else:
                        self.logger.error(f"工具 '{tool_name}' 不在tool_pool中，无法注册")
                        raise PlanScopeError(f"Plan需要的工具 '{tool_name}' 不存在于tool_pool")
            
            return plan_json
        except Exception as e:
            error_msg = f"工作流生成失败: {str(e)}"
            self.logger.error(error_msg)
            raise PlanScopeError(error_msg) from e
    
    def execute_plan(self,
                    plan_json: Dict[str, Any],
                    tools: Dict[str, Callable]) -> Dict[str, Any]:
        """
        执行工作流计划
        
        Args:
            plan_json: 工作流JSON对象
            tools: 工具函数字典 {tool_name: function}
            
        Returns:
            执行结果，包含所有步骤的返回值
            
        Raises:
            PlanScopeError: 执行失败
            
        Example:
            >>> result = ps.execute_plan(
            ...     plan_json=plan,
            ...     tools={
            ...         "screenshot_and_analyze": screenshot_func,
            ...         "paddle_ocr_analyze": ocr_func
            ...     }
            ... )
        """
        self.logger.info("执行工作流计划")
        
        try:
            # 验证工具
            validation = self.plan_executor.validate_tools(plan_json, tools)
            if not validation["valid"]:
                raise PlanScopeError(
                    f"缺少必需的工具: {validation['missing_tools']}"
                )
            
            # 获取reflection_chain（如果有）
            reflection_chain = None
            if "reflection_chain_id" in plan_json:
                try:
                    from planscope.ace.reflection_chain import ReflectionChain
                    # 使用StorageManager加载
                    chain_data = self.storage_manager.load_reflection_chain(plan_json["reflection_chain_id"])
                    if chain_data:
                        reflection_chain = ReflectionChain.from_dict(chain_data)
                except Exception as e:
                    self.logger.warning(f"无法加载反思链: {e}")
            
            # 执行工作流
            result = self.plan_executor.execute(plan_json, tools, reflection_chain)
            
            # 保存更新后的反思链
            if reflection_chain:
                try:
                    chain_path = self.storage_manager.save_reflection_chain(reflection_chain)
                    self.logger.info(f"反思链已更新: {reflection_chain.chain_id} -> {chain_path.name}")
                except Exception as e:
                    self.logger.warning(f"保存反思链失败: {e}")
            
            # ACE: 执行成功，更新任务成功状态
            if self.use_ace and hasattr(self, 'plan_generator'):
                flow_id = plan_json.get("flow_id")
                if flow_id and hasattr(self.plan_generator, 'update_task_success'):
                    self.plan_generator.update_task_success(flow_id, success=True)
            
            return result
            
        except Exception as e:
            error_msg = f"工作流执行失败: {str(e)}"
            self.logger.error(error_msg)
            
            # ACE: 执行失败，触发反思流程（阈值为1，失败1次就触发）
            if self.use_ace:
                self._trigger_ace_reflection(plan_json, e)
            
            raise PlanScopeError(error_msg) from e
    
    def _trigger_ace_reflection(self, plan_json: Dict[str, Any], error: Exception) -> None:
        """
        触发ACE反思流程
        
        Args:
            plan_json: 工作流JSON
            error: 异常对象
        """
        try:
            self.logger.info("=" * 80)
            self.logger.info("触发ACE反思流程")
            self.logger.info("=" * 80)
            
            # 获取当前轨迹
            trace = self.ace_generator.get_current_trace()
            if not trace:
                self.logger.warning("未找到执行轨迹，跳过ACE反思")
                return
            
            # 完成轨迹记录
            trace = self.ace_generator.finalize_trace()
            
            # 反思：分析失败原因
            self.logger.info("步骤1: 分析失败原因...")
            insights = self.ace_reflector.analyze_trace(trace)
            self.logger.info(f"分析完成，失败类型: {insights.get('failure_type', 'unknown')}")
            
            # 整编：生成上下文条目
            self.logger.info("步骤2: 生成上下文条目...")
            new_entries = self.ace_curator.curate_insights(insights, trace)
            self.logger.info(f"生成了 {len(new_entries)} 个新条目")
            
            # 更新上下文
            self.logger.info("步骤3: 更新上下文...")
            task_type = self.context_manager.identify_task_type(trace.task_description)
            self.ace_curator.update_context(task_type, new_entries)
            self.logger.info("上下文更新完成")
            
            # 更新任务失败状态
            flow_id = plan_json.get("flow_id")
            if flow_id and hasattr(self.plan_generator, 'update_task_success'):
                self.plan_generator.update_task_success(flow_id, success=False)
            
            self.logger.info("=" * 80)
            self.logger.info("ACE反思流程完成")
            self.logger.info("=" * 80)
            
        except Exception as e:
            self.logger.error(f"ACE反思流程失败: {str(e)}")
            # 不抛出异常，避免影响主流程
    
    def execute_plan_from_file(self,
                              file_path: str,
                              tools: Dict[str, Callable]) -> Dict[str, Any]:
        """
        从文件加载并执行工作流
        
        Args:
            file_path: 工作流JSON文件路径
            tools: 工具函数字典
            
        Returns:
            执行结果
            
        Raises:
            PlanScopeError: 加载或执行失败
            
        Example:
            >>> result = ps.execute_plan_from_file(
            ...     "plan_123.json",
            ...     tools={...}
            ... )
        """
        self.logger.info(f"从文件加载工作流: {file_path}")
        
        try:
            # 加载工作流
            plan_json = self.plan_generator.load_plan_from_file(file_path)
            
            # 执行工作流
            return self.execute_plan(plan_json, tools)
        except Exception as e:
            error_msg = f"工作流加载或执行失败: {str(e)}"
            self.logger.error(error_msg)
            raise PlanScopeError(error_msg) from e
    
    def load_plan(self, flow_id: str) -> Dict[str, Any]:
        """
        根据flow_id加载工作流
        
        Args:
            flow_id: 工作流ID
            
        Returns:
            工作流JSON对象
            
        Raises:
            PlanScopeError: 加载失败
        """
        try:
            return self.plan_generator.load_plan(flow_id)
        except Exception as e:
            error_msg = f"工作流加载失败: {str(e)}"
            self.logger.error(error_msg)
            raise PlanScopeError(error_msg) from e
    
    def add_tool_to_pool(self, tool_class, **init_kwargs) -> None:
        """
        将工具添加到工具池（只支持BaseTool类，统一格式）
        
        工具池中的工具只有在LLM分析用户需求后推荐使用时，才会被动态注册和分析
        
        Args:
            tool_class: BaseTool子类
            **init_kwargs: 初始化参数（如vl_model_client, llm_model_client）
            
        Example:
            >>> from examples.tools.vl_extract_image_content import VLExtractTool
            >>> ps.add_tool_to_pool(VLExtractTool, vl_model_client=vl_client)
            
            >>> from examples.tools.scroll_and_analyze import ScrollAndAnalyzeTool
            >>> ps.add_tool_to_pool(ScrollAndAnalyzeTool, vl_model_client=vl_client)
            
            >>> from examples.tools.general_llm_processor import GeneralLLMProcessorTool
            >>> ps.add_tool_to_pool(GeneralLLMProcessorTool, llm_model_client=llm_client)
            
        Raises:
            TypeError: 如果tool_class不是BaseTool子类
        """
        from planscope.tools.base_tool import BaseTool
        
        # 检查是否继承BaseTool
        if not (isinstance(tool_class, type) and issubclass(tool_class, BaseTool)):
            raise TypeError(
                f"工具必须是BaseTool的子类。收到: {tool_class}\n"
                f"请确保工具继承自planscope.tools.base_tool.BaseTool\n"
                f"示例：ps.add_tool_to_pool(VLExtractTool, vl_model_client=vl_client)"
            )
        
        # 验证元数据完整性（No Fallback原则）
        is_valid, missing_fields = tool_class.validate_metadata()
        if not is_valid:
            raise ValueError(
                f"工具 {tool_class.__name__} 元数据不完整，缺少以下字段：\n"
                f"{chr(10).join('  - ' + field for field in missing_fields)}"
            )
        
        # 实例化工具
        tool_instance = tool_class(**init_kwargs)
        
        # 获取元数据（统一入口）
        metadata = tool_class.get_metadata()
        
        # 添加到工具池
        self.tool_pool[metadata['name']] = {
            "name": metadata['name'],
            "func": tool_instance.execute,
            "description": metadata['description'],
            "tool_type": metadata.get('tool_type', 'function'),
            "input_parameters": metadata.get('input_parameters', {}),
            "output_json_schema": metadata.get('output_json_schema', '')
        }
        
        self.logger.info(
            f"✓ 工具 '{metadata['name']}' (类型: {metadata.get('tool_type')}) 已添加到工具池"
        )
    
    def register_tool(self, name: str, metadata: Optional[Dict[str, Any]] = None):
        """
        [已废弃] 装饰器：注册工具函数
        
        ⚠️ 此方法已废弃，请使用 add_tool_to_pool() 替代。
        
        新的工作流程：
        1. 使用 add_tool_to_pool() 将工具添加到工具库
        2. 调用 generate_plan() 时，LLM会自动筛选并注册需要的工具
        
        Raises:
            DeprecationWarning: 此方法已废弃
        """
        import warnings
        warnings.warn(
            "register_tool() 已废弃，请使用 add_tool_to_pool() 替代。"
            "新流程：add_tool_to_pool() → generate_plan() → LLM自动筛选并注册工具",
            DeprecationWarning,
            stacklevel=2
        )
        self.logger.warning(f"register_tool() 已废弃，请使用 add_tool_to_pool() 替代")
        
        def decorator(func: Callable) -> Callable:
            # 不再执行注册，只返回原函数
            return func
        return decorator
    
    def add_tool(self, name: str, func: Callable, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        [已废弃] 手动注册工具函数
        
        ⚠️ 此方法已废弃，请使用 add_tool_to_pool() 替代。
        
        Raises:
            DeprecationWarning: 此方法已废弃
        """
        import warnings
        warnings.warn(
            "add_tool() 已废弃，请使用 add_tool_to_pool() 替代。",
            DeprecationWarning,
            stacklevel=2
        )
        self.logger.warning(f"add_tool() 已废弃，请使用 add_tool_to_pool() 替代")
    
    def list_tools(self) -> list:
        """
        列出所有已注册的工具
        
        Returns:
            工具名称列表
        """
        return self.tool_registry.list_tools()
    
    def parse_plan(self, plan_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析工作流（不执行）
        
        Args:
            plan_json: 工作流JSON对象
            
        Returns:
            解析结果，包含执行顺序和依赖图
        """
        try:
            return self.plan_parser.parse(plan_json)
        except Exception as e:
            error_msg = f"工作流解析失败: {str(e)}"
            self.logger.error(error_msg)
            raise PlanScopeError(error_msg) from e
    
    def get_logger(self) -> LoggerManager:
        """
        获取日志管理器
        
        Returns:
            LoggerManager实例
        """
        return self.logger_manager
    
    def trigger_quality_reflection(self,
                                   plan: Dict[str, Any],
                                   result: Dict[str, Any],
                                   feedback: str) -> None:
        """
        手动触发质量反思（用于成功但质量不佳的情况）
        
        Args:
            plan: 执行的计划
            result: 执行结果
            feedback: 用户反馈
        """
        if not self.use_ace:
            self.logger.warning("ACE未启用，无法触发质量反思")
            return
        
        self.logger.info("=" * 80)
        self.logger.info("触发ACE质量反思")
        self.logger.info("=" * 80)
        
        try:
            # 获取当前轨迹
            trace = self.ace_generator.current_trace
            if not trace:
                self.logger.warning("未找到执行轨迹，无法触发质量反思")
                return
            
            # 添加质量问题标记
            trace.quality_issue = feedback
            
            # 获取或加载reflection_chain
            reflection_chain = None
            if "reflection_chain_id" in plan:
                try:
                    from planscope.ace.reflection_chain import ReflectionChain
                    # 使用StorageManager加载
                    chain_data = self.storage_manager.load_reflection_chain(plan["reflection_chain_id"])
                    if chain_data:
                        reflection_chain = ReflectionChain.from_dict(chain_data)
                        self.logger.info(f"加载反思链: {reflection_chain.chain_id}")
                except Exception as e:
                    self.logger.warning(f"无法加载反思链: {e}")
            
            # 调用反思器分析质量问题
            self.logger.info("步骤1: 分析质量问题...")
            insights = self.ace_reflector.analyze_quality_issue(trace, feedback, reflection_chain)
            self.logger.info(f"分析完成，问题步骤: {insights.get('problem_step', 'unknown')}")
            
            # 整编：生成上下文条目
            self.logger.info("步骤2: 生成上下文条目...")
            new_entries = self.ace_curator.curate_insights(insights, trace, reflection_chain)
            self.logger.info(f"生成了 {len(new_entries)} 个新条目")
            
            # 更新上下文
            self.logger.info("步骤3: 更新上下文...")
            task_type = self.context_manager.identify_task_type(trace.task_description)
            self.ace_curator.update_context(task_type, new_entries)
            self.logger.info("上下文更新完成")
            
            # 保存更新后的反思链
            if reflection_chain:
                try:
                    chain_path = self.storage_manager.save_reflection_chain(reflection_chain)
                    self.logger.info(f"反思链已保存: {chain_path.name}")
                except Exception as e:
                    self.logger.warning(f"保存反思链失败: {e}")
            
            self.logger.info("=" * 80)
            self.logger.info("ACE质量反思完成")
            self.logger.info("=" * 80)
            
        except Exception as e:
            self.logger.error(f"ACE质量反思失败: {str(e)}")
            import traceback
            self.logger.debug(traceback.format_exc())
            # 不抛出异常，避免影响主流程
    
    def cleanup(self) -> None:
        """
        清理资源
        """
        self.logger.info("PlanScope清理资源")
        self.tool_registry.clear()
    
    # ========== ACE用户反馈API ==========
    
    def mark_entry_useful(self, entry_id: str, task_type: Optional[str] = None) -> bool:
        """
        标记上下文条目为有用
        
        Args:
            entry_id: 条目ID
            task_type: 任务类型（可选）
            
        Returns:
            是否标记成功
        """
        if not self.use_ace:
            self.logger.warning("ACE未启用，无法标记条目")
            return False
        
        try:
            # 获取条目
            entry = self.context_manager.get_entry_by_id(entry_id)
            if not entry:
                self.logger.warning(f"未找到条目: {entry_id}")
                return False
            
            # 更新评分
            entry.update_score(is_useful=True)
            
            # 保存
            if task_type is None:
                task_type = entry.metadata.get("related_tasks", ["general"])[0]
            
            self.context_manager.update_entry(entry_id, {"metadata": entry.metadata}, task_type)
            
            self.logger.info(f"条目已标记为有用: {entry_id}, 新评分: {entry.metadata['score']}")
            return True
            
        except Exception as e:
            self.logger.error(f"标记条目失败: {str(e)}")
            return False
    
    def mark_entry_harmful(self, entry_id: str, task_type: Optional[str] = None) -> bool:
        """
        标记上下文条目为有害
        
        Args:
            entry_id: 条目ID
            task_type: 任务类型（可选）
            
        Returns:
            是否标记成功
        """
        if not self.use_ace:
            self.logger.warning("ACE未启用，无法标记条目")
            return False
        
        try:
            # 获取条目
            entry = self.context_manager.get_entry_by_id(entry_id)
            if not entry:
                self.logger.warning(f"未找到条目: {entry_id}")
                return False
            
            # 更新评分
            entry.update_score(is_useful=False)
            
            # 保存
            if task_type is None:
                task_type = entry.metadata.get("related_tasks", ["general"])[0]
            
            self.context_manager.update_entry(entry_id, {"metadata": entry.metadata}, task_type)
            
            self.logger.info(f"条目已标记为有害: {entry_id}, 新评分: {entry.metadata['score']}")
            return True
            
        except Exception as e:
            self.logger.error(f"标记条目失败: {str(e)}")
            return False
    
    def get_context_entries(self, task_type: Optional[str] = None) -> list:
        """
        获取上下文条目
        
        Args:
            task_type: 任务类型（如果为None则返回所有类型）
            
        Returns:
            条目列表（字典格式）
        """
        if not self.use_ace:
            self.logger.warning("ACE未启用，返回空列表")
            return []
        
        try:
            entries = self.context_manager.get_all_entries(task_type)
            return [entry.to_dict() for entry in entries]
        except Exception as e:
            self.logger.error(f"获取上下文条目失败: {str(e)}")
            return []
    
    def clear_context(self, task_type: Optional[str] = None) -> int:
        """
        清理上下文
        
        Args:
            task_type: 任务类型（如果为None则清理所有类型）
            
        Returns:
            删除的条目数量
        """
        if not self.use_ace:
            self.logger.warning("ACE未启用，无法清理上下文")
            return 0
        
        try:
            if task_type:
                # 清理指定类型
                entries = self.context_manager.load_context(task_type)
                count = len(entries)
                self.context_manager.save_context(task_type, [])
                self.logger.info(f"已清理任务类型 {task_type} 的 {count} 个条目")
                return count
            else:
                # 清理所有类型
                from pathlib import Path
                count = 0
                for context_file in Path(self.context_manager.context_dir).glob("*.json"):
                    tt = context_file.stem
                    entries = self.context_manager.load_context(tt)
                    count += len(entries)
                    self.context_manager.save_context(tt, [])
                
                self.logger.info(f"已清理所有上下文，共 {count} 个条目")
                return count
                
        except Exception as e:
            self.logger.error(f"清理上下文失败: {str(e)}")
            return 0
    
    def get_task_history(self, limit: int = 20) -> list:
        """
        获取任务历史
        
        Args:
            limit: 返回数量限制
            
        Returns:
            任务历史列表
        """
        if not self.use_ace:
            self.logger.warning("ACE未启用，返回空列表")
            return []
        
        try:
            return self.task_matcher.get_task_history(limit)
        except Exception as e:
            self.logger.error(f"获取任务历史失败: {str(e)}")
            return []
    
    def export_context(self, output_path: str) -> bool:
        """
        导出上下文到文件
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            是否导出成功
        """
        if not self.use_ace:
            self.logger.warning("ACE未启用，无法导出上下文")
            return False
        
        try:
            import json
            from pathlib import Path
            
            # 收集所有上下文
            all_contexts = {}
            for context_file in Path(self.context_manager.context_dir).glob("*.json"):
                task_type = context_file.stem
                entries = self.context_manager.load_context(task_type)
                all_contexts[task_type] = [entry.to_dict() for entry in entries]
            
            # 保存到文件
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(all_contexts, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"上下文已导出到: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"导出上下文失败: {str(e)}")
            return False


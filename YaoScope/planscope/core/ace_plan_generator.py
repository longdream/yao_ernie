"""
ACE增强的流程生成器
继承PlanGenerator并增加ACE功能
"""
from typing import Dict, Any, Optional, List
from pathlib import Path

from planscope.core.plan_generator import PlanGenerator
from planscope.core.prompt_cache_manager import PromptCacheManager
from planscope.ace.context_manager import ContextManager
from planscope.ace.context_entry import ContextEntry
from planscope.ace.task_matcher import TaskMatcher
from planscope.ace.reflection_chain import ReflectionChain
from planscope.core.exceptions import PlanGenerationError


class ACEPlanGenerator(PlanGenerator):
    """
    ACE增强的流程生成器
    
    在原有PlanGenerator基础上增加：
    1. 任务相似度匹配和复用
    2. 经验注入到Prompt
    3. 任务-JSON映射保存
    """
    
    def __init__(self,
                 model_client,
                 logger_manager,
                 work_dir: str,
                 context_manager: ContextManager,
                 task_matcher: TaskMatcher,
                 tool_registry,
                 storage_manager=None):
        """
        初始化ACE流程生成器
        
        Args:
            model_client: AgentScope模型客户端
            logger_manager: 日志管理器
            work_dir: 工作目录
            context_manager: 上下文管理器
            task_matcher: 任务匹配器
            tool_registry: 工具注册表
            storage_manager: 存储管理器（可选）
        """
        # 调用父类初始化（传递storage_manager）
        super().__init__(model_client, logger_manager, work_dir, storage_manager=storage_manager)
        
        # ACE组件
        self.context_manager = context_manager
        self.task_matcher = task_matcher
        self.tool_registry = tool_registry
        self.tool_generator = None  # 将由PlanScope设置
        # storage_manager已在父类中设置
        
        # Prompt缓存管理器（在generate时设置flow_id）
        self.prompt_cache_manager = PromptCacheManager(
            work_dir, 
            flow_id=None, 
            storage_manager=storage_manager
        )
        
        # 工具推荐器（初始化时不设置，在generate时创建）
        self.tool_recommender = None
        
        # 更新logger名称
        self.logger = logger_manager.get_logger("ace_plan_generator")
    
    async def generate_with_auto_tool_creation(self,
                                               user_prompt: str,
                                               prompt_template: Optional[str] = None,
                                               save_to_file: bool = True,
                                               **kwargs) -> Dict[str, Any]:
        """
        生成工作流计划，支持自动创建缺失的工具
        
        如果发现plan中需要的工具不存在，会自动生成并注册该工具，然后重新生成plan
        
        Args:
            user_prompt: 用户需求描述
            prompt_template: 自定义prompt模板（可选）
            save_to_file: 是否保存到文件
            **kwargs: 传递给LLM的额外参数
            
        Returns:
            工作流JSON对象
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # 尝试生成plan
                plan_json = await self.generate(user_prompt, prompt_template, save_to_file, **kwargs)
                
                # 检查所需工具是否都存在
                if not self.tool_generator:
                    # 如果没有tool_generator，直接返回（不支持自动生成）
                    return plan_json
                
                missing_tools = self._check_missing_tools(plan_json)
                
                if not missing_tools:
                    return plan_json  # 成功，所有工具都存在
                
                # 发现缺失工具
                self.logger.warning(f"发现缺失工具: {list(missing_tools.keys())}")
                self.logger.info("尝试自动生成缺失的工具...")
                
                # 使用ACE生成工具
                for tool_name, tool_desc in missing_tools.items():
                    self.logger.info(f"正在生成工具: {tool_name}")
                    
                    success = await self.tool_generator.generate_tool(
                        tool_name=tool_name,
                        tool_description=tool_desc,
                        required_capabilities=self._extract_capabilities(tool_desc)
                    )
                    
                    if not success:
                        raise RuntimeError(f"无法生成工具: {tool_name}")
                    
                    self.logger.info(f"工具生成成功: {tool_name}")
                
                # 重新生成plan（现在工具已存在）
                self.logger.info("工具已生成，重新生成plan...")
                
            except Exception as e:
                if attempt == max_retries - 1:
                    self.logger.error(f"Plan生成失败，已达到最大重试次数")
                    raise
                self.logger.warning(f"Plan生成失败，尝试 {attempt + 1}/{max_retries}: {e}")
        
        raise RuntimeError("Plan生成失败，已达到最大重试次数")
    
    async def generate(self,
                      user_prompt: str,
                      prompt_template: Optional[str] = None,
                      save_to_file: bool = True,
                      **kwargs) -> Dict[str, Any]:
        """
        生成工作流计划（ACE增强版）
        
        Args:
            user_prompt: 用户需求描述
            prompt_template: 自定义prompt模板（可选）
            save_to_file: 是否保存到文件
            **kwargs: 传递给LLM的额外参数
            
        Returns:
            工作流JSON对象
            
        Raises:
            PlanGenerationError: 生成失败
        """
        self.logger.info("=" * 80)
        self.logger.info("ACE增强的工作流生成")
        self.logger.info(f"用户需求: {user_prompt}")
        
        # 创建反思链
        reflection_chain = ReflectionChain(
            task_description=user_prompt,
            task_name="plan_generation"
        )
        
        # 步骤1：尝试复用相似任务的plan
        reused_plan = await self._try_reuse_plan(user_prompt)
        if reused_plan:
            self.logger.info("成功复用历史任务的plan")
            
            # 注意：工具注册由PlanScope.generate_plan在返回后统一处理
            # 这里只负责返回plan，不负责工具注册
            
            # ⚠️ 重要：生成新的flow_id，避免覆盖旧的task记录
            # 原因：每次执行都应该创建新的task记录，即使复用了plan
            import time
            import hashlib
            old_flow_id = reused_plan.get("flow_id", "unknown")
            timestamp = int(time.time())
            query_hash = hashlib.md5(user_prompt.encode('utf-8')).hexdigest()[:8]
            new_flow_id = f"flow_{timestamp}_{query_hash}"
            
            # 更新plan中的flow_id
            reused_plan["flow_id"] = new_flow_id
            reused_plan["reused_from"] = old_flow_id  # 记录复用来源
            
            self.logger.info(f"生成新的flow_id: {new_flow_id} (复用自: {old_flow_id})")
            
            # 设置Prompt缓存管理器的flow_id
            self.prompt_cache_manager.set_flow_id(new_flow_id)
            self.logger.info(f"Prompt缓存管理器已设置flow_id: {new_flow_id}")
            
            # ⚠️ 优化：复用plan时跳过经验检索和prompt注入
            # 原因：
            # 1. 复用的plan已经包含完整的prompt（从缓存获取）
            # 2. _retrieve_relevant_context会调用LLM做任务分类（~5秒）
            # 3. _inject_initial_prompts会从缓存获取prompt（已优化，无LLM调用）
            # 结论：直接使用复用的plan，不需要额外处理
            self.logger.info("✓ 复用plan，跳过经验检索和prompt注入（使用缓存的完整plan）")
            
            # 创建/更新task记录（使用新的flow_id）
            # 这样每次执行都会创建新的task记录
            self._save_task_mapping(user_prompt, reused_plan, success=None)
            
            # 更新元数据
            reused_plan = self._add_metadata(reused_plan, user_prompt, 0.0)
            if save_to_file:
                file_path = self._save_plan(reused_plan)
                reused_plan["file_path"] = str(file_path)
            return reused_plan
        
        # 步骤2：检索相关经验（异步调用）
        relevant_entries = await self._retrieve_relevant_context(user_prompt)
        
        # 步骤3：构建增强的prompt
        if relevant_entries:
            self.logger.info(f"找到 {len(relevant_entries)} 个相关经验，注入到prompt")
            enhanced_prompt = self._build_enhanced_prompt(user_prompt, relevant_entries, prompt_template)
        else:
            self.logger.info("未找到相关经验，使用默认prompt")
            # 获取工具描述
            tools_desc = ""
            if self.tool_registry:
                tools_desc = self.tool_registry.get_all_tools_description()
            else:
                tools_desc = "暂无可用工具"
            
            template = prompt_template or self.DEFAULT_PROMPT_TEMPLATE
            enhanced_prompt = template.format(
                user_prompt=user_prompt,
                available_tools_description=tools_desc
            )
        
        # 步骤4：调用父类的generate方法（但使用增强的prompt）
        try:
            # 记录Plan生成输入到反思链
            reflection_chain.add_entry(
                stage="plan_generation",
                input_data={
                    "user_prompt": user_prompt,
                    "full_prompt": enhanced_prompt[:1000] + "..." if len(enhanced_prompt) > 1000 else enhanced_prompt,
                    "prompt_length": len(enhanced_prompt),
                    "has_context": len(relevant_entries) > 0,
                    "context_count": len(relevant_entries)
                },
                model_info={
                    "model_name": getattr(self.model_client, 'model_name', 'unknown'),
                    "temperature": kwargs.get("temperature", "default")
                }
            )
            
            # 直接调用LLM（复制父类逻辑）
            import time
            start_time = time.time()
            
            self.logger.info("=" * 80)
            self.logger.info("准备调用LLM生成工作流")
            self.logger.info(f"Prompt长度: {len(enhanced_prompt)}")
            self.logger.info(f"Prompt前500字符: {enhanced_prompt[:500]}")
            self.logger.info("=" * 80)
            
            plan_json = await self.model_client.call_model_with_json_response(
                prompt=enhanced_prompt,
                **kwargs
            )
            generation_time = time.time() - start_time
            
            self.logger.info("=" * 80)
            self.logger.info("LLM返回工作流")
            self.logger.info(f"生成耗时: {generation_time:.2f}秒")
            self.logger.info("=" * 80)
            
            # 记录Plan生成输出到反思链
            reflection_chain.add_entry(
                stage="plan_generation_result",
                output_data={
                    "plan_json": plan_json,
                    "steps_count": len(plan_json.get("steps", [])),
                    "complexity_level": plan_json.get("complexity_level", "unknown"),
                    "generation_time": generation_time
                }
            )
            
            # 验证JSON格式
            from planscope.utils.json_validator import PlanJSONValidator
            PlanJSONValidator.validate(plan_json)
            PlanJSONValidator.validate_dependencies(plan_json)
            
            # 添加元数据
            plan_json = self._add_metadata(plan_json, user_prompt, generation_time)
            
            # 设置Prompt缓存管理器的flow_id（从plan的flow_id中获取）
            flow_id = plan_json.get("flow_id", "unknown")
            self.prompt_cache_manager.set_flow_id(flow_id)
            self.logger.info(f"Prompt缓存管理器已设置flow_id: {flow_id}")
            
            # 步骤4.5：注入ACE优化的prompt（如果有）
            plan_json = self._inject_optimized_prompts(plan_json, relevant_entries)
            
            # 步骤4.6：注入initial_prompt（如果工具有initial_prompt且没有被优化prompt覆盖）
            plan_json = await self._inject_initial_prompts(plan_json)
            
            # 步骤4.7：优化聊天判断prompt（如果是聊天分析任务）
            # self._optimize_chat_judge_prompt(plan_json)  # 已禁用硬编码优化
            
            # 步骤4.8：优化文档续写prompt（如果是文档续写任务）
            # self._optimize_document_continue_prompt(plan_json)  # 已禁用硬编码优化
            
            # 保存到文件
            if save_to_file:
                file_path = self._save_plan(plan_json)
                plan_json["file_path"] = str(file_path)
                self.logger.info(f"工作流已保存到: {file_path}")
            
            # 步骤5：保存任务映射（注意：此时还不知道是否成功，先保存为未知状态）
            self._save_task_mapping(user_prompt, plan_json, success=None)
            
            self.logger.info(f"工作流生成成功，包含 {len(plan_json['steps'])} 个步骤")
            self.logger.info(f"生成耗时: {generation_time:.2f}秒")
            self.logger.info("=" * 80)
            
            # 保存反思链（通过StorageManager）
            if self.storage_manager:
                chain_path = self.storage_manager.save_reflection_chain(reflection_chain)
                self.logger.info(f"反思链已保存: {chain_path.name}")
                plan_json["reflection_chain_id"] = reflection_chain.chain_id
                plan_json["reflection_chain_file"] = str(chain_path)
            else:
                self.logger.warning("StorageManager未初始化，反思链未保存")
            
            # 记录性能指标
            self.logger_manager.log_performance_metrics(
                operation="ace_plan_generation",
                duration=generation_time,
                additional_metrics={
                    "step_count": len(plan_json["steps"]),
                    "prompt_length": len(user_prompt),
                    "complexity": plan_json.get("complexity_level", "unknown"),
                    "used_context": len(relevant_entries) > 0
                }
            )
            
            return plan_json
            
        except Exception as e:
            error_msg = f"工作流生成失败: {str(e)}"
            self.logger.error(error_msg)
            self.logger.error(f"异常类型: {type(e).__name__}")
            self.logger.error(f"异常详情: {repr(e)}")
            
            # 如果是JSON解析错误，记录更多上下文
            if "JSON" in str(e) or "json" in str(e) or "steps" in str(e):
                self.logger.error("=" * 80)
                self.logger.error("JSON解析错误详情:")
                self.logger.error(f"用户prompt: {user_prompt[:500]}")
                self.logger.error(f"增强prompt长度: {len(enhanced_prompt) if 'enhanced_prompt' in locals() else 'N/A'}")
                self.logger.error("=" * 80)
            
            raise PlanGenerationError(error_msg) from e
    
    async def _try_reuse_plan(self, task_description: str) -> Optional[Dict[str, Any]]:
        """
        尝试复用相似任务的plan（只复用成功的任务）
        
        Args:
            task_description: 任务描述
            
        Returns:
            可复用的plan JSON（如果找到）
        """
        self.logger.info("检查是否有可复用的历史任务...")
        
        try:
            # 查找相似任务（提高阈值以减少误匹配）
            similar_tasks = await self.task_matcher.find_similar_tasks(
                task_description, 
                threshold=0.85  # 提高到0.85，只匹配高度相似的任务
            )
            
            if similar_tasks:
                self.logger.info(f"找到 {len(similar_tasks)} 个相似任务")
                
                # 按相似度排序，优先尝试最相似的
                sorted_tasks = sorted(similar_tasks, key=lambda x: x[1], reverse=True)
                
                # 优先复用成功的任务，如果没有成功的，也可以复用失败任务的prompt
                successful_task = None
                failed_task_with_plan = None
                
                for task_id, similarity, task_data in sorted_tasks:
                    self.logger.info(f"检查任务 {task_id}, 相似度: {similarity:.2f}, 成功: {task_data.get('success')}")
                    
                    if task_data:
                        flow_id = task_data.get("flow_id")
                        if flow_id:
                            plan_file = self.plans_dir / f"{flow_id}.json"
                            if plan_file.exists():
                                # 检查任务是否成功
                                if task_data.get("success") == True:
                                    # 找到成功的任务，直接使用
                                    successful_task = (task_id, similarity, flow_id, plan_file)
                                    break
                                elif failed_task_with_plan is None:
                                    # 记录第一个有plan的失败任务，作为备选
                                    failed_task_with_plan = (task_id, similarity, flow_id, plan_file)
                
                # 优先使用成功的任务
                if successful_task:
                    task_id, similarity, flow_id, plan_file = successful_task
                    self.logger.info(f"✓ 找到成功的相似任务: {task_id}, 相似度: {similarity:.2f}")
                    with open(plan_file, 'r', encoding='utf-8') as f:
                        import json
                        plan = json.load(f)
                    self.logger.info(f"✓ 成功复用plan: {flow_id}")
                    return plan
                
                # 如果没有成功的任务，但有失败任务的plan（包含优化过的prompt），也可以复用
                elif failed_task_with_plan:
                    task_id, similarity, flow_id, plan_file = failed_task_with_plan
                    self.logger.info(f"⚠ 未找到成功的任务，但找到相似的失败任务: {task_id}, 相似度: {similarity:.2f}")
                    self.logger.info(f"⚠ 将复用其优化过的prompt（虽然之前执行失败，但prompt可能是有效的）")
                    with open(plan_file, 'r', encoding='utf-8') as f:
                        import json
                        plan = json.load(f)
                    self.logger.info(f"✓ 复用失败任务的plan（含优化prompt）: {flow_id}")
                    return plan
                
                else:
                    self.logger.info("找到相似任务但都没有有效的plan文件，不复用")
            else:
                self.logger.info("未找到可复用的任务")
            
            return None
            
        except Exception as e:
            self.logger.warning(f"任务复用检查失败: {str(e)}")
            return None
    
    async def _retrieve_relevant_context(self, task_description: str) -> List[ContextEntry]:
        """
        检索相关上下文（异步版本）
        
        Args:
            task_description: 任务描述
            
        Returns:
            相关的上下文条目列表
        """
        try:
            # 识别任务类型（使用异步版本）
            task_type = await self.context_manager.identify_task_type_async(task_description)
            self.logger.debug(f"任务类型: {task_type}")
            
            # 从自动Context加载
            auto_entries = await self.context_manager.retrieve_relevant_entries_async(
                task_description=task_description,
                task_type=task_type,
                top_k=5
            )
            
            # 从Memory加载（用户标记的正确记录）
            memory_entries = self.context_manager.load_memory_as_context(task_type)
            
            # 合并（Memory优先）
            all_entries = memory_entries + auto_entries
            
            # 去重（保留第一个，即Memory的）
            unique_entries = []
            seen = set()
            for entry in all_entries:
                key = (entry.tool_name, entry.task_type)
                if key not in seen:
                    unique_entries.append(entry)
                    seen.add(key)
            
            # 限制数量
            entries = unique_entries[:5]
            
            # 更新最后使用时间
            for entry in entries:
                entry.update_last_used()
            
            self.logger.info(f"检索到上下文: {len(auto_entries)}个自动 + {len(memory_entries)}个Memory = {len(entries)}个（去重后）")
            
            return entries
            
        except Exception as e:
            self.logger.warning(f"检索上下文失败: {str(e)}")
            return []
    
    def _build_enhanced_prompt(self,
                              user_prompt: str,
                              context_entries: List[ContextEntry],
                              prompt_template: Optional[str] = None) -> str:
        """
        构建增强的prompt
        
        Args:
            user_prompt: 用户需求
            context_entries: 上下文条目
            prompt_template: 自定义模板
            
        Returns:
            增强的prompt
        """
        # 构建经验库文本
        context_text = self._format_context_entries(context_entries)
        
        # 获取工具描述
        tools_desc = ""
        if self.tool_registry:
            tools_desc = self.tool_registry.get_all_tools_description()
        else:
            tools_desc = "暂无可用工具"
        
        # 使用增强模板
        template = prompt_template or self._get_enhanced_template()
        
        # 格式化
        enhanced_prompt = template.format(
            context_entries=context_text,
            user_prompt=user_prompt,
            available_tools_description=tools_desc
        )
        
        return enhanced_prompt
    
    def _format_context_entries(self, entries: List[ContextEntry]) -> str:
        """
        格式化上下文条目
        
        Args:
            entries: 上下文条目列表
            
        Returns:
            格式化的文本
        """
        if not entries:
            return "（暂无相关经验）"
        
        lines = []
        for i, entry in enumerate(entries, 1):
            entry_type = entry.entry_type.value
            score = entry.metadata.get("score", 0)
            lines.append(f"{i}. [{entry_type}] (评分: {score})")
            lines.append(f"   {entry.content}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _get_enhanced_template(self) -> str:
        """
        获取增强的prompt模板
        
        Returns:
            增强的模板
        """
        return """你是一个工作流规划专家。以下是过往的成功经验和策略，以及可用工具信息，请参考这些信息生成高质量的工作流计划。

【经验库】
{context_entries}

【可用工具】
{available_tools_description}

【用户需求】
{user_prompt}

请生成一个JSON格式的工作流计划，包含以下结构：
{{
  "steps": [
    {{
      "step_id": 1,
      "description": "步骤描述",
      "tool": "工具名称",
      "tool_input": {{
        "参数名": "参数值"
      }},
      "dependencies": [],
      "reasoning": "选择该步骤的原因"
    }}
  ],
  "overall_strategy": "整体策略描述",
  "complexity_level": "simple/medium/complex",
  "estimated_steps": 步骤数量
}}

要求：
1. step_id必须从1开始连续递增
2. dependencies数组包含该步骤依赖的其他步骤的step_id
3. ⚠️ tool_input必须包含工具的**所有必需参数**
   - 查看工具描述中的"⚠️ 必需参数（tool_input中必须包含）"部分
   - 每个必需参数都必须在tool_input中显式指定为独立字段
   - 参数值可以是常量、变量引用{{{{steps.X.field}}}}、或者空字符串，但字段本身必须存在
   
   🔥 **特别重要 - general_llm_processor 工具的正确用法**：
   ❌ 错误（content 参数缺失）：
   "tool_input": {{
     "prompt": "请分析：{{{{steps.1.content}}}}"
   }}
   
   ✅ 正确（content 和 prompt 都存在）：
   "tool_input": {{
     "content": "{{{{steps.1.content}}}}",
     "prompt": "请分析以上内容并判断..."
   }}
   
   🔥 **特别重要 - 微信聊天记录处理规则**（如果任务涉及聊天记录分析）：
   VL工具会分析聊天截图，识别消息内容和发送者。
   在生成 general_llm_processor 的 prompt 时：
   - 直接基于聊天上下文生成回复
   - 输出内容应该干净、可直接使用
   - 不要在输出中添加任何位置标记或前缀
   
   示例prompt：
   "prompt": "分析聊天记录上下文，生成一条自然、符合对话风格的回复。只返回回复文本内容，不要添加任何前缀或标记。"
   
   🔥 **特别重要 - 文档编辑器必须使用OCR三步流程**：
   
   **⚠️ 强制判断规则**：
   如果 app_name 包含以下任一关键词（不区分大小写）：
   - "记事本" / "notepad"
   - "Word" / "word" / "winword"
   - "写字板" / "wordpad" 
   - "VSCode" / "vscode" / "code"
   - "Notepad++"
   - "Sublime"
   - "PDF"
   - 或任何其他文档/代码编辑器
   
   **必须生成3步工作流（强制要求）**：
   ```json
   {{
     "steps": [
       {{
         "step_id": 1,
         "tool": "screenshot_and_analyze",
         "tool_input": {{
           "app_name": "记事本",
           "prompt": "截取文档编辑区域"
         }},
         "description": "截取文档窗口"
       }},
       {{
         "step_id": 2,
         "tool": "ocr_extract_text",
         "tool_input": {{
           "image_path": "{{{{steps.1.screenshot_path}}}}"
         }},
         "dependencies": [1],
         "description": "使用OCR提取文字（纯文字识别，不做过滤）"
       }},
       {{
         "step_id": 3,
         "tool": "general_llm_processor",
            "tool_input": {{
            "content": "{{{{steps.2.content}}}}",
            "prompt": "**第一步**：识别并删除所有非正文内容（工具栏文字等）。**第二步**：理解原文内容和风格。**第三步**：从原文最后一个字开始续写新内容（100-200字）。**重要**：只返回新续写的部分，不要重复原文。"
          }},
         "dependencies": [2],
         "description": "LLM过滤并处理文字内容"
       }}
     ]
   }}
   ```
   
   **❌ 绝对禁止以下错误模式**：
   ```json
   {{
     "steps": [
       {{"step_id": 1, "tool": "screenshot_and_analyze", ...}},
       {{"step_id": 2, "tool": "general_llm_processor", ...}}  ← 错误！缺少OCR步骤
     ]
   }}
   ```
   
   **关键检查清单**：
   ✅ 步骤数 = 3 （不是2！）
   ✅ 步骤2必须是 ocr_extract_text
   ✅ 步骤2必须引用 {{{{steps.1.screenshot_path}}}}
   ✅ 步骤3必须引用 {{{{steps.2.content}}}}
   ✅ 步骤3的prompt必须包含过滤指令
   
4. tool_input中可以使用变量引用，格式为 {{{{steps.X.field}}}}（双层花括号），表示引用步骤X的返回值中的field字段
   示例：{{{{steps.1.content}}}}、{{{{steps.1.participants}}}}、{{{{steps.2.result.data}}}}
5. ⚠️ 重要：不能引用不存在的步骤！只能引用step_id小于当前步骤的已执行步骤
   - 错误示例：步骤1引用{{{{steps.0.xxx}}}}（步骤0不存在）
   - 错误示例：步骤1引用{{{{steps.1.xxx}}}}（不能自引用）
   - 正确示例：步骤2引用{{{{steps.1.xxx}}}}（引用前一步的结果）
6. 如果第一步需要用户输入的数据（如聊天记录、文档内容等），这些数据应该：
   - 通过工具的输入参数直接获取（如screenshot_and_analyze工具会自动截图）
   - 或者在tool_input中使用空字符串/占位文本，不要使用steps引用
7. ⚠️ 应用名称推理规则（针对screenshot_and_analyze等需要app_name的工具）：
   - 必须保持用户输入的原始应用名称，不要翻译或转换
   - 用户说"微信" → app_name: "微信"（保持中文）
   - 用户说"WeChat" → app_name: "WeChat"（保持英文）
   - 错误示例：用户说"微信" → app_name: "wechat"（错误：不要翻译成英文）
   - 错误示例：用户说"微信" → app_name: "WeChat"（错误：不要转换）
   - 正确示例：用户说"微信" → app_name: "微信"（正确：保持原样）
8. 确保依赖关系正确，不能有循环依赖
9. 根据工具的能力范围和局限性选择合适的工具，不要超出工具的能力边界
10. 参考工具的最佳实践和适用场景进行规划
11. 参考经验库中的成功策略和工具最佳实践
12. 避免经验库中记录的错误模式
13. 只返回JSON，不要有其他说明文字

请生成工作流计划："""
    
    def _inject_optimized_prompts(self, 
                                  plan_json: Dict[str, Any],
                                  relevant_entries: List) -> Dict[str, Any]:
        """
        从ACE context中提取优化后的prompt并注入到tool_input中
        
        Args:
            plan_json: 工作流JSON
            relevant_entries: 相关的上下文条目
            
        Returns:
            注入prompt后的plan_json
        """
        if not relevant_entries:
            return plan_json
        
        # 统计
        total_entries = len(relevant_entries)
        tool_usage_entries = 0
        prompts_found = 0
        
        # 构建工具名 -> 优化prompt的映射
        tool_prompts = {}
        for entry in relevant_entries:
            if entry.entry_type.value == "tool_usage":
                tool_usage_entries += 1
                optimized_prompt = entry.metadata.get("optimized_prompt")
                
                # Fallback: 从content解析
                if not optimized_prompt:
                    self.logger.debug(f"从metadata中未找到optimized_prompt，尝试从content解析")
                    optimized_prompt = self._extract_prompt_from_content(entry.content)
                
                related_tools = entry.metadata.get("related_tools", [])
                if optimized_prompt and related_tools:
                    prompts_found += 1
                    for tool_name in related_tools:
                        # 使用最新的prompt（按创建时间排序，时间最新的优先）
                        entry_created_at = entry.metadata.get("created_at", "")
                        existing_created_at = tool_prompts.get(tool_name, {}).get("created_at", "")
                        
                        if tool_name not in tool_prompts or entry_created_at > existing_created_at:
                            tool_prompts[tool_name] = {
                                "prompt": optimized_prompt,
                                "score": entry.metadata.get("score", 0),
                                "created_at": entry_created_at
                            }
                            self.logger.debug(f"找到工具'{tool_name}'的优化prompt，created_at={entry_created_at}, score={entry.metadata.get('score', 0)}")
        
        self.logger.info(f"Context检索结果: 总条目={total_entries}, tool_usage={tool_usage_entries}, 有效prompt={prompts_found}")
        
        if not tool_prompts:
            self.logger.warning("未找到任何可注入的优化prompt")
            return plan_json
        
        # ⚠️ OCR工具白名单：这些工具不应该接受自定义prompt（纯功能性工具）
        NO_PROMPT_TOOLS = {"ocr_extract_text", "scroll", "click_element", "type_text"}
        
        # 注入prompt到对应的步骤，并记录变化
        injected_count = 0
        for step in plan_json.get("steps", []):
            tool_name = step.get("tool")
            
            # 跳过不需要prompt的工具
            if tool_name in NO_PROMPT_TOOLS:
                self.logger.debug(f"跳过工具'{tool_name}'的prompt注入（该工具不使用自定义prompt）")
                continue
            
            if tool_name in tool_prompts:
                if "tool_input" not in step:
                    step["tool_input"] = {}
                
                # 记录旧prompt（用于对比）
                old_prompt = step.get("tool_input", {}).get("prompt", "")
                optimized_prompt_raw = tool_prompts[tool_name]["prompt"]
                
                # 提取旧prompt的核心内容（去掉JSON schema部分）以便对比
                old_prompt_core = old_prompt.split("\n\n**必须严格按以下JSON格式返回：**")[0] if old_prompt else ""
                
                # 检查核心prompt是否变化了
                if old_prompt_core != optimized_prompt_raw:
                    # ⚠️ 注意：不在这里拼接JSON schema！
                    # schema应该在工具内部拼接，这样每个工具可以控制自己的输出格式
                    # 这里只存储ACE优化的纯任务描述prompt
                    step["tool_input"]["prompt"] = optimized_prompt_raw
                    injected_count += 1
                    
                    # 保存优化后的prompt到Plan缓存
                    if hasattr(self, 'prompt_cache_manager') and self.prompt_cache_manager:
                        self.prompt_cache_manager.save_prompt(
                            tool_name=tool_name,
                            prompt=optimized_prompt_raw,  # 保存核心prompt（不含JSON schema）
                            generator="ace",
                            quality_score=max(0.0, (tool_prompts[tool_name]['score'] + 5) / 10),  # 归一化score到0-1
                            optimized_by_ace=True
                        )
                        self.logger.debug(f"✓ 已保存优化prompt到Plan缓存: {tool_name}")
                    
                    self.logger.info("=" * 80)
                    self.logger.info(f"✓ 步骤{step['step_id']}的工具'{tool_name}'已更新prompt（schema将由工具内部拼接）")
                    self.logger.info(f"创建时间: {tool_prompts[tool_name].get('created_at', 'unknown')}")
                    self.logger.info(f"Score: {tool_prompts[tool_name]['score']}")
                    
                    # 显示变化对比
                    if old_prompt_core:
                        self.logger.info(f"\n旧Prompt（前100字符）:\n{old_prompt_core[:100]}...")
                    self.logger.info(f"\n新Prompt（前100字符）:\n{optimized_prompt_raw[:100]}...")
                    self.logger.info("=" * 80)
                else:
                    self.logger.info(f"步骤{step['step_id']}的工具'{tool_name}'的prompt未变化（核心内容相同），跳过更新")
        
        self.logger.info(f"Prompt注入完成: {injected_count}/{len(tool_prompts)}个工具的prompt已更新")
        
        if injected_count == 0 and len(tool_prompts) > 0:
            self.logger.warning(f"警告：找到了{len(tool_prompts)}个优化prompt，但没有任何prompt被注入（可能已经是最新的）")
        
        return plan_json
    
    def _extract_prompt_from_content(self, content: str) -> Optional[str]:
        """
        从content字段解析优化后的prompt
        
        用于当metadata中没有optimized_prompt时的fallback机制
        
        Args:
            content: 上下文条目的content字段
            
        Returns:
            提取出的prompt，如果提取失败则返回None
        """
        if not content:
            return None
        
        import re
        
        # 尝试多种解析模式
        patterns = [
            # 模式1: 【Prompt优化】- 建议: ...
            r'【Prompt优化】.*?- 建议:\s*(.+?)(?:\n【|$)',
            # 模式2: 优化后的Prompt: ...
            r'优化后的Prompt[：:]\s*(.+?)(?:\n【|$)',
            # 模式3: suggested_prompt: ...
            r'suggested_prompt[：:]\s*(.+?)(?:\n【|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                extracted = match.group(1).strip()
                if extracted and len(extracted) > 10:  # 确保不是空的或太短的
                    self.logger.debug(f"成功从content解析出prompt，长度: {len(extracted)}字符")
                    return extracted
        
        self.logger.debug("无法从content解析出有效的prompt")
        return None
    
    def _ensure_content_in_schema(self, schema_str: str) -> str:
        """
        确保JSON schema包含content字段
        
        Args:
            schema_str: JSON schema字符串
            
        Returns:
            包含content字段的schema字符串
        """
        try:
            # 尝试解析JSON
            import json
            schema = json.loads(schema_str)
            
            # 检查是否是对象类型的schema
            if isinstance(schema, dict) and schema.get("type") == "object":
                # 检查properties是否存在
                if "properties" not in schema:
                    schema["properties"] = {}
                
                # 如果没有content字段，添加它
                if "content" not in schema.get("properties", {}):
                    schema["properties"]["content"] = {
                        "type": "string",
                        "description": "本工具最重要的输出结果，必须填写"
                    }
                    
                    # 更新required字段
                    if "required" not in schema:
                        schema["required"] = []
                    if "content" not in schema["required"]:
                        schema["required"].append("content")
                    
                    self.logger.debug(f"已添加content字段到schema")
                
                # 返回格式化的JSON字符串
                return json.dumps(schema, ensure_ascii=False, indent=2)
            
            # 如果不是对象类型，返回原schema
            return schema_str
            
        except Exception as e:
            # 解析失败，返回原schema
            self.logger.warning(f"解析schema失败，保持原样: {e}")
            return schema_str
    
    async def _inject_initial_prompts(self, plan_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        为工具注入initial_prompt（异步版本）
        
        如果工具注册时提供了initial_prompt，且没有被优化prompt覆盖，则注入。
        如果没有initial_prompt，则调用LLM智能生成（支持Plan缓存）。
        
        Args:
            plan_json: 工作流JSON
            
        Returns:
            注入initial_prompt后的plan_json
        """
        self.logger.debug(f"[_inject_initial_prompts] 开始注入prompt，tool_registry={self.tool_registry is not None}")
        
        if not self.tool_registry:
            return plan_json
        
        # ⚠️ OCR工具白名单：这些工具不应该接受自定义prompt（纯功能性工具）
        NO_PROMPT_TOOLS = {"ocr_extract_text", "scroll", "click_element", "type_text"}
        
        # 遍历所有步骤
        for step in plan_json.get("steps", []):
            tool_name = step.get("tool")
            self.logger.debug(f"[_inject_initial_prompts] 处理步骤: {tool_name}")
            
            if not tool_name:
                continue
            
            # 跳过不需要prompt的工具
            if tool_name in NO_PROMPT_TOOLS:
                self.logger.debug(f"[_inject_initial_prompts] 跳过工具'{tool_name}'（该工具不使用自定义prompt）")
                continue
            
            # 获取工具的output_json_schema
            tool_metadata = self.tool_registry.get_metadata(tool_name)
            output_json_schema = tool_metadata.get("output_json_schema", "")
            
            # 强制添加content字段到schema
            if output_json_schema:
                output_json_schema = self._ensure_content_in_schema(output_json_schema)
                # 更新metadata中的schema
                tool_metadata["output_json_schema"] = output_json_schema
            
            # 获取当前LLM生成的prompt（如果有）
            llm_generated_prompt = ""
            if "tool_input" in step and "prompt" in step["tool_input"]:
                llm_generated_prompt = step["tool_input"]["prompt"]
            
            # 获取工具的initial_prompt（如果有）
            initial_prompt = tool_metadata.get("initial_prompt", "")
            
            # 决定是否需要生成/优化prompt
            should_generate_prompt = False
            
            # 决定是否生成prompt
            # 情况1：工具有预定义的initial_prompt -> 使用它，不生成
            if initial_prompt:
                should_generate_prompt = False
                self.logger.debug(f"[_inject_initial_prompts] 工具'{tool_name}'有预定义的initial_prompt，直接使用")
            
            # 情况2：LLM生成了prompt（参考它来增强）
            # -> 基于LLM的prompt进行增强
            elif llm_generated_prompt:
                should_generate_prompt = True
                self.logger.info(f"[_inject_initial_prompts] LLM为工具'{tool_name}'生成了prompt，ACE将基于它进行增强")
            
            # 情况3：LLM没有生成prompt
            # -> 由ACE从零生成
            else:
                should_generate_prompt = True
                self.logger.info(f"[_inject_initial_prompts] 为工具'{tool_name}'生成prompt（由ACE统一生成）")
            
            # 执行prompt生成（如果需要）
            if should_generate_prompt:
                initial_prompt = await self._generate_prompt_for_tool(
                    tool_name=tool_name,
                    tool_metadata=tool_metadata,
                    step_description=step.get("description", ""),
                    step_reasoning=step.get("reasoning", ""),
                    llm_generated_prompt=llm_generated_prompt  # ← 传递LLM生成的prompt
                )
                self.logger.info(f"[OK] 为工具'{tool_name}'生成了新prompt")
            
            if initial_prompt:
                if "tool_input" not in step:
                    step["tool_input"] = {}
                
                # ⚠️ 注意：不在这里拼接JSON schema！
                # schema应该在工具内部拼接，这样每个工具可以控制自己的输出格式
                # 这里只存储纯任务描述prompt
                step["tool_input"]["prompt"] = initial_prompt
                
                self.logger.info("=" * 80)
                self.logger.info(f"为步骤{step['step_id']}的工具'{tool_name}'注入prompt（schema将由工具内部拼接）")
                self.logger.info(f"\nPrompt内容:\n{initial_prompt[:300]}...")
                self.logger.info("=" * 80)
        
        # 自动修复：检查并修复 general_llm_processor 缺失的 content 参数
        self._fix_general_llm_processor_params(plan_json)
        
        return plan_json
    
    def _fix_general_llm_processor_params(self, plan_json: Dict[str, Any]) -> None:
        """
        自动修复 general_llm_processor 工具缺失的 content 参数
        
        如果 prompt 中包含 {{steps.X.content}}，自动提取为独立的 content 参数
        """
        import re
        
        for step in plan_json.get("steps", []):
            tool_name = step.get("tool")
            tool_input = step.get("tool_input", {})
            
            # 修改条件：content不存在 或者 content是空字符串
            content_value = tool_input.get("content", "")
            if tool_name == "general_llm_processor" and (not content_value or content_value == ""):
                prompt = tool_input.get("prompt", "")
                
                # 查找 prompt 中的 {{steps.X.content}} 引用
                match = re.search(r'\{\{steps\.(\d+)\.content\}\}', prompt)
                
                if match:
                    # 提取变量引用
                    step_ref = match.group(0)  # 如 {{steps.1.content}}
                    
                    # 添加 content 参数
                    tool_input["content"] = step_ref
                    
                    # 从 prompt 中移除这个引用，避免重复
                    prompt = re.sub(r'[：:]\s*\{\{steps\.\d+\.content\}\}', '', prompt)
                    prompt = re.sub(r'请.*分析.*\{\{steps\.\d+\.content\}\}[，。,.\s]*', '请分析以上内容，', prompt)
                    tool_input["prompt"] = prompt.strip()
                    
                    self.logger.warning(f"🔧 自动修复：为步骤{step['step_id']}的general_llm_processor添加content参数: {step_ref}")
                    self.logger.info(f"   修复后的prompt: {prompt[:100]}...")
    
    def _optimize_chat_judge_prompt_disabled(self, plan_json: Dict[str, Any]) -> None:
        """
        优化聊天判断步骤的prompt，明确说明如何识别 [左侧-XXX] 和 [右侧-我] 格式
        
        检测条件：
        1. 步骤1使用 screenshot_and_analyze 且任务涉及微信/聊天
        2. 步骤2使用 general_llm_processor 且依赖步骤1
        """
        steps = plan_json.get("steps", [])
        if len(steps) < 2:
            return
        
        # 检查是否是聊天分析任务
        step1 = steps[0]
        step2 = steps[1] if len(steps) > 1 else None
        
        is_chat_task = (
            step1.get("tool") == "screenshot_and_analyze" and
            step2 and step2.get("tool") == "general_llm_processor" and
            1 in step2.get("dependencies", []) and
            any(keyword in step1.get("description", "").lower() for keyword in ["微信", "聊天", "wechat", "qq"])
        )
        
        if not is_chat_task:
            return
        
        # 优化步骤2的prompt
        tool_input = step2.get("tool_input", {})
        old_prompt = tool_input.get("prompt", "")
        
        # 检查prompt中是否已经包含格式识别规则
        if "[左侧-" in old_prompt and "[右侧-我]" in old_prompt:
            self.logger.info("✓ 聊天判断prompt已包含格式识别规则，无需优化")
            return
        
        # 添加明确的格式识别规则
        format_rule = """

【重要】识别VL工具返回的格式：
- `[左侧-XXX]` 或 `[左侧-XXX]:` = 对方发送的消息 → 必须生成回复
- `[右侧-我]` 或 `[右侧-我]:` = 我发送的消息 → 返回空字符串''

判断方法：检查最后一条消息是否包含"[左侧-"，如果包含则是对方发送，需要生成回复；如果包含"[右侧-我]"则是我发送，返回空字符串。"""
        
        # 在prompt开头添加规则
        optimized_prompt = format_rule + "\n\n" + old_prompt
        tool_input["prompt"] = optimized_prompt
        
        self.logger.warning(f"🔧 自动优化：为步骤{step2['step_id']}添加聊天格式识别规则")
        self.logger.info(f"   优化后的prompt长度: {len(optimized_prompt)} 字符")
    
    def _optimize_document_continue_prompt(self, plan_json: Dict[str, Any]) -> None:
        """
        [已禁用] 此方法不再使用硬编码优化，改由LLM根据工具描述自主规划
        
        保留此方法是为了向后兼容，但实际不执行任何操作。
        工作流的正确性由LLM在plan生成时保证，而不是事后修正。
        """
        # 不再进行硬编码的优化
        # LLM应该根据工具描述和prompt指导自己生成正确的工作流
        return
    
    async def _generate_prompt_for_tool(self,
                                        tool_name: str,
                                        tool_metadata: Dict[str, Any],
                                        step_description: str,
                                        step_reasoning: str,
                                        llm_generated_prompt: str = "") -> str:
        """
        使用LLM智能生成工具的prompt（异步版本，支持缓存）
        
        优先级：
        1. Plan缓存（PromptCacheManager） - 避免重复生成
        2. LLM动态生成 - 首次生成时调用
        
        根据工具的能力、限制、输入参数等元数据，以及步骤的描述和推理，
        让LLM智能生成一个合适的prompt。
        
        如果提供了llm_generated_prompt，则在其基础上进行增强（保留占位符，添加规则）。
        
        Args:
            tool_name: 工具名称
            tool_metadata: 工具元数据（capabilities, limitations, input_parameters, output_json_schema等）
            step_description: 步骤描述
            step_reasoning: 步骤推理原因
            llm_generated_prompt: LLM在生成plan时已生成的prompt（可选）
            
        Returns:
            LLM生成/增强的prompt字符串
        """
        # 0. 优先检查Plan缓存（避免不必要的LLM调用）
        if hasattr(self, 'prompt_cache_manager') and self.prompt_cache_manager:
            cached_prompt = self.prompt_cache_manager.get_cached_prompt(tool_name)
            if cached_prompt:
                self.logger.info(f"✓ 复用Plan缓存的prompt: {tool_name} (长度: {len(cached_prompt)}字符)")
                return cached_prompt
        
        # 1. 提取LLM prompt中的占位符（如果有）
        import re
        placeholders = []
        if llm_generated_prompt:
            # 匹配 {{steps.X.field}} 格式的占位符
            placeholders = re.findall(r'\{\{steps\.\d+\.[^}]+\}\}', llm_generated_prompt)
            if placeholders:
                self.logger.info(f"✓ 从LLM prompt中提取到 {len(placeholders)} 个占位符: {placeholders}")
        
        # 2. 使用意图分类快速识别任务类型（替代关键词匹配）
        task_classification_str = "general"
        primary_category = "general"
        sub_category = ""
        
        if hasattr(self, 'context_manager') and self.context_manager:
            try:
                task_classification_str = await self.context_manager.identify_task_type_async(step_description)
                # 解析字符串格式: "primary_category-sub_category" 或 "primary_category"
                if "-" in task_classification_str:
                    parts = task_classification_str.split("-", 1)
                    primary_category = parts[0]
                    sub_category = parts[1]
                else:
                    primary_category = task_classification_str
                    sub_category = ""
                
                self.logger.info(f"✓ 任务分类: {primary_category}"
                               f"{f' - {sub_category}' if sub_category else ''} "
                               f"(置信度: 0.95)")
            except Exception as e:
                self.logger.warning(f"意图分类失败，使用默认分类: {e}")
        
        # 3. 根据分类决定是否需要特殊规则（仅微信/QQ聊天）
        needs_chat_rules = (
            tool_name in ["scroll_and_analyze", "screenshot_and_analyze"] and 
            (sub_category in ["wechat_extraction", "qq_extraction"] or
             primary_category == "chat_analysis" or
             "微信" in step_description or "QQ" in step_description or "聊天" in step_description or
             "微信" in step_reasoning or "QQ" in step_reasoning or "聊天" in step_reasoning)
        )
        
        if needs_chat_rules:
            self.logger.info(f"✓ 检测到聊天工具任务，将添加左右识别规则")
        
        # 4. 检查是否是文档编辑任务
        needs_document_rules = (
            tool_name == "screenshot_and_analyze" and
            any(keyword in step_description.lower() for keyword in ["文档", "记事本", "notepad", "word", "续写", "改写", "扩写"]) or
            any(keyword in step_reasoning.lower() for keyword in ["文档", "记事本", "notepad", "word", "续写", "改写", "扩写"])
        )
        
        if needs_document_rules:
            self.logger.info(f"✓ 检测到文档编辑任务，将添加文档识别规则")
        
        # 4. 调用LLM生成/增强prompt（已确认没有缓存）
        # 提取工具元数据
        capabilities = tool_metadata.get("capabilities", [])
        limitations = tool_metadata.get("limitations", [])
        input_parameters = tool_metadata.get("input_parameters", {})
        best_practices = tool_metadata.get("best_practices", [])
        
        # 构建输入参数说明
        params_desc = []
        has_app_names_param = False
        for param_name, param_info in input_parameters.items():
            if isinstance(param_info, dict) and param_name != "prompt":
                param_type = param_info.get("type", "any")
                required = "必需" if param_info.get("required", False) else "可选"
                description = param_info.get("description", "")
                params_desc.append(f"  - {param_name} ({param_type}, {required}): {description}")
                
                # 检测是否有app_names参数（窗口查找相关）
                if param_name == "app_names":
                    has_app_names_param = True
        
        # 构造让LLM生成/增强prompt的提示
        if llm_generated_prompt:
            # 基于已有prompt进行增强
            llm_prompt = f"""你是一个Prompt增强专家。请基于原始prompt进行增强，保留所有占位符并添加必要的规则。

【原始Prompt】（由LLM在生成plan时创建）
{llm_generated_prompt}

【占位符信息】
原prompt中包含以下占位符，增强后的prompt中**必须完整保留**：
{chr(10).join(f"- {p}" for p in placeholders) if placeholders else "（无占位符）"}

【工具信息】
工具名称: {tool_name}
步骤描述: {step_description}
选择原因: {step_reasoning}

【工具能力】
{chr(10).join(f"- {cap}" for cap in capabilities) if capabilities else "（无）"}

【工具限制】
{chr(10).join(f"- {lim}" for lim in limitations) if limitations else "（无）"}

【增强要求】
1. **必须保留原prompt中的所有占位符**（格式：{{{{steps.X.field}}}}），不能修改或删除
2. 优化prompt的表述，使其更清晰、更具体、更有指导性
3. 保持原prompt的核心意图和结构
4. **严禁添加任何输出格式说明**：
   - 只优化任务描述部分
   - 不要写"输出格式"、"返回格式"、"JSON"、"Schema"等任何格式相关词汇
   - 不要写示例格式
   - 系统会自动处理输出格式
5. **深入理解用户意图**：
   - 分析用户真正想达成的目标是什么
   - 判断这个步骤在整个工作流中的作用
   - 理解工具的能力边界和限制
   - 基于理解生成精准、自然的prompt
   - 不要机械套用固定模板，要根据具体情况灵活调整
{f'''6. **聊天界面分析规则**（放在prompt开头或适当位置）：

【微信/QQ聊天界面分析】

**关键说明**：
- 截图已自动裁剪，仅包含聊天消息区域
- 整个画面即为可分析的聊天内容区域

**消息气泡位置规则**：
1. 左对齐气泡（白色/灰色背景）= 对方发送的消息
2. 右对齐气泡（绿色/蓝色背景）= 我发送的消息

**分析步骤**：
1. 从上至下理解聊天上下文
2. 识别最后一条消息的发送者
3. 理解对话的主题和语气

**输出要求**：
- 直接输出消息内容或回复内容
- 不要添加任何位置标记（如[左侧]、[右侧]等）
- 输出应该干净、可直接使用
''' if needs_chat_rules else ''}

{f'''7. **文档OCR识别规则**（如果是文档相关任务）：

【重要说明】：
截图已自动裁剪，只包含文本编辑区域，不含标题栏、菜单栏和工具栏。

【你的任务】：
使用OCR技术精确识别并提取文档中的所有文字内容

【OCR提取要求】：
1. **逐行扫描**：从上到下、从左到右按行提取所有可见文本
2. **保留格式**：保持原始的换行符、段落分隔、缩进
3. **识别段落**：正确识别段落结构和层次
4. **完整提取**：不遗漏任何文字，包括标点符号
5. **精确识别**：确保每个字符都正确识别，避免误读

【输出内容】：
只输出提取的完整文本内容（纯文本，保持原始格式）

⚠️ **注意**：
- 你的任务是OCR识别提取文字，不是理解内容
- 不要分析、总结或修改文本
- 不要添加任何额外的说明或注释
- 只需要原原本本地提取出所有文字
''' if needs_document_rules else ''}

【输出要求】
- 只返回增强后的完整prompt文本
- 确保所有占位符格式正确且完整保留
- prompt长度适中（200-500字）
- 不要有任何解释或额外说明

增强后的Prompt："""
        else:
            # 从零生成新prompt
            llm_prompt = f"""你是一个智能Prompt生成专家。请根据以下信息，为工具'{tool_name}'生成一个高质量的执行prompt。

【工具信息】
工具名称: {tool_name}
步骤描述: {step_description}
选择原因: {step_reasoning}

【工具能力】
{chr(10).join(f"- {cap}" for cap in capabilities) if capabilities else "（无）"}

【工具限制】
{chr(10).join(f"- {lim}" for lim in limitations) if limitations else "（无）"}

【输入参数】
{chr(10).join(params_desc) if params_desc else "（无额外参数）"}

【最佳实践】
{chr(10).join(f"- {bp}" for bp in best_practices) if best_practices else "（无）"}

【生成要求】
1. Prompt应该清晰、简洁、任务导向
2. 如果是VL工具（图像识别），prompt应该专注于描述需要从图像中提取什么信息
3. Prompt长度适中（VL工具100-200字，LLM工具200-400字）
4. **严禁包含任何输出格式说明**：
   - 只描述任务内容和要求
   - 不要写"输出格式"、"返回格式"、"JSON"、"Schema"、"按照...格式"等词汇
   - 不要写任何格式示例
   - 系统会自动处理输出格式
5. **深入理解用户意图并灵活生成**：
   - 理解步骤描述背后的真实目标
   - 考虑这个步骤在整个工作流的位置和作用
   - 结合工具的能力和限制，生成最合适的指令
   - 不要套用固定模板，要自然、灵活地表达
   - 例如："续写"任务应理解为在原文基础上继续创作，保持连贯性
{f'''6. **聊天界面分析规则**：

【微信聊天记录分析】：

**重要说明**：
截图已经自动裁剪，只包含聊天对话区域。

**识别规则**：
1. 左边的消息（白色/灰色气泡）= 对方发的
2. 右边的消息（绿色/蓝色气泡）= 我发的
3. 理解聊天上下文和对话主题
4. 重点关注最后一条消息

**输出要求**：
- 直接输出消息内容或回复内容
- 不要添加任何位置标记或前缀
- 输出应该干净、可直接使用
''' if needs_chat_rules else ''}

{f'''7. **文档编辑识别规则**（如果是文档续写/改写任务）：

【重要说明】：
截图已自动裁剪，只包含文本编辑区域，不含标题栏、菜单栏和工具栏。

【OCR提取规则】：
1. 从上到下按行提取所有可见文本
2. 保留原始格式和换行
3. 识别段落结构
4. 完整提取文档内容，不遗漏

【输出格式】：
提取的完整文本内容（保持原始格式）

【处理要求】：
- **续写任务（极其重要）**：
  * 第一步：过滤掉非正文内容（如工具栏文字）
  * 第二步：理解原文风格和内容
  * 第三步：从原文最后一个字开始续写（100-200字）
  * **关键要求：只返回新续写的部分，绝对不要重复原文！**
- 改写任务：使用更生动的语言，提升表达质量，返回完整改写后的文本
- 扩写任务：增加细节描述和情感表达，返回完整扩写后的文本
''' if needs_document_rules else ''}

【输出格式】
只返回生成的prompt文本，不要有任何解释或其他内容。

生成的Prompt："""
        
        try:
            # 调用LLM生成prompt（异步版本，使用纯文本调用而非JSON）
            
            # 直接调用model_client生成文本（不是JSON）
            if hasattr(self, 'context_manager') and self.context_manager.llm_analyzer:
                # 使用LLM Analyzer的model_client
                # 增加max_tokens以确保prompt不被截断
                generated_prompt = await self.context_manager.llm_analyzer.model_client.call_model(
                    prompt=llm_prompt,
                    max_tokens=2000  # 确保有足够的token生成完整的prompt
                )
                
                generated_prompt = str(generated_prompt).strip()
                
                self.logger.info(f"✓ LLM为工具'{tool_name}'智能生成prompt，长度: {len(generated_prompt)}字符")
                
                # 清理prompt中可能包含的输出格式提示（确保prompt纯粹）
                import re
                # 移除"输出格式："及其后续内容
                generated_prompt = re.sub(r'\n*\*\*输出格式\*\*[：:]\s*.*$', '', generated_prompt, flags=re.DOTALL)
                generated_prompt = re.sub(r'\n*输出格式[：:]\s*.*$', '', generated_prompt, flags=re.DOTALL)
                generated_prompt = generated_prompt.strip()
                
                self.logger.info(f"✓ Prompt已清理，最终长度: {len(generated_prompt)}字符")
                
                # 3. 保存到Plan缓存
                if hasattr(self, 'prompt_cache_manager') and self.prompt_cache_manager:
                    self.prompt_cache_manager.save_prompt(
                        tool_name=tool_name,
                        prompt=generated_prompt,
                        generator="llm"
                    )
                    self.logger.info(f"✓ 已保存prompt到Plan缓存: {tool_name}")
                
                return generated_prompt
            else:
                # 如果没有LLMAnalyzer，抛出异常
                raise RuntimeError("LLMAnalyzer未初始化，无法智能生成prompt")
                
        except Exception as e:
            error_msg = f"LLM生成prompt失败: {e}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def _save_task_mapping(self,
                          task_description: str,
                          plan_json: Dict[str, Any],
                          success: Optional[bool] = None) -> None:
        """
        保存任务映射
        
        Args:
            task_description: 任务描述
            plan_json: 工作流JSON
            success: 是否成功（None表示未知）
        """
        try:
            # 如果success为None，暂时保存为False（后续执行成功后会更新）
            self.task_matcher.save_task_mapping(
                task_description=task_description,
                plan_json=plan_json,
                success=success if success is not None else False
            )
        except Exception as e:
            self.logger.warning(f"保存任务映射失败: {str(e)}")
    
    def update_task_success(self, flow_id: str, success: bool) -> None:
        """
        更新任务执行结果（同时更新时间戳）
        
        Args:
            flow_id: 工作流ID
            success: 是否成功
        """
        try:
            import json
            from datetime import datetime
            
            task_id = f"task_{flow_id}"
            task_file = self.task_matcher.task_history_dir / f"{task_id}.json"
            
            if task_file.exists():
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = json.load(f)
                
                # 更新成功状态和执行时间
                task_data["success"] = success
                task_data["last_executed_at"] = datetime.now().isoformat()
                
                with open(task_file, 'w', encoding='utf-8') as f:
                    json.dump(task_data, f, ensure_ascii=False, indent=2)
                
                self.logger.info(f"任务执行结果已更新: {task_id}, success={success}")
            else:
                self.logger.warning(f"任务文件不存在，无法更新: {task_file}")
        except Exception as e:
            self.logger.error(f"更新任务执行结果失败: {str(e)}")
            import traceback
            self.logger.debug(traceback.format_exc())
    
    def _check_missing_tools(self, plan_json: Dict[str, Any]) -> Dict[str, str]:
        """
        检查plan中需要的工具是否都已注册
        
        Args:
            plan_json: 工作流JSON
            
        Returns:
            缺失的工具字典 {tool_name: tool_description}
        """
        missing_tools = {}
        
        for step in plan_json.get("steps", []):
            tool_name = step.get("tool")
            if not tool_name:
                continue
            
            # 检查工具是否已注册
            if not self.tool_registry.has(tool_name):
                # 工具缺失
                description = step.get("description", "")
                reasoning = step.get("reasoning", "")
                
                # 组合描述
                tool_desc = f"{description}. {reasoning}" if reasoning else description
                missing_tools[tool_name] = tool_desc
                
                self.logger.warning(f"缺失工具: {tool_name} - {tool_desc}")
        
        return missing_tools
    
    def _extract_capabilities(self, tool_description: str) -> list:
        """
        从工具描述中提取所需能力
        
        Args:
            tool_description: 工具描述
            
        Returns:
            能力列表
        """
        # 简单实现：将描述按句号分割作为能力列表
        # 更复杂的实现可以使用LLM来提取
        capabilities = []
        
        # 按句号或逗号分割
        import re
        sentences = re.split(r'[。.；;，,]', tool_description)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and len(sentence) > 5:  # 过滤太短的句子
                capabilities.append(sentence)
        
        # 限制数量
        return capabilities[:5]


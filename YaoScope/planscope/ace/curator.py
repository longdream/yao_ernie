"""
ACE Curator（整编器）
将反思器的洞见转化为上下文条目
"""
from typing import Dict, Any, List
import difflib

from planscope.ace.context_entry import ContextEntry, ContextEntryType
from planscope.ace.execution_trace import ExecutionTrace
from planscope.ace.context_manager import ContextManager
from planscope.core.exceptions import ACECurationError


class ACECurator:
    """
    ACE整编器
    
    负责将反思器的洞见转化为结构化的上下文条目
    """
    
    def __init__(self, context_manager: ContextManager, logger_manager):
        """
        初始化整编器
        
        Args:
            context_manager: 上下文管理器
            logger_manager: 日志管理器
        """
        self.context_manager = context_manager
        self.logger_manager = logger_manager
        self.logger = logger_manager.get_logger("ace_curator")
    
    def curate_insights(self,
                       insights: Dict[str, Any],
                       trace: ExecutionTrace,
                       reflection_chain=None) -> List[ContextEntry]:
        """
        整编洞见
        
        Args:
            insights: 反思器提取的洞见
            trace: 执行轨迹
            reflection_chain: 反思链对象（可选）
            
        Returns:
            新创建的上下文条目列表
        """
        self.logger.info("开始整编洞见")
        
        failure_type = insights.get("failure_type", "unknown")
        
        if failure_type == "workflow":
            return self._curate_workflow_insights(insights, trace)
        elif failure_type == "tool":
            return self._curate_tool_insights(insights, trace)
        elif failure_type == "mixed":
            return self._curate_mixed_insights(insights, trace)
        elif failure_type == "success":
            return self._curate_success_insights(insights, trace)
        elif failure_type == "quality_issue":
            return self._curate_quality_issue_insights(insights, trace, reflection_chain)
        else:
            self.logger.warning(f"未知的失败类型: {failure_type}")
            return []
    
    def _curate_workflow_insights(self,
                                  insights: Dict[str, Any],
                                  trace: ExecutionTrace) -> List[ContextEntry]:
        """
        整编流程失败洞见
        
        Args:
            insights: 洞见
            trace: 轨迹
            
        Returns:
            上下文条目列表
        """
        entries = []
        
        # 创建 ERROR_PATTERN 类型条目
        root_cause = insights.get("root_cause", "")
        workflow_issues = insights.get("workflow_issues", [])
        improved_strategy = insights.get("improved_workflow_strategy", "")
        
        # 构建内容
        content = f"【错误模式】{root_cause}\n"
        content += f"【改进策略】{improved_strategy}\n"
        content += "【具体问题】\n"
        for issue in workflow_issues:
            content += f"- {issue.get('issue', '')}: {issue.get('suggestion', '')}\n"
        
        entry = ContextEntry(
            entry_type=ContextEntryType.ERROR_PATTERN,
            content=content,
            metadata={
                "created_at": trace.timestamp,
                "last_used": trace.timestamp,
                "useful_count": 0,
                "harmful_count": 1,  # 失败案例初始为-1分
                "score": -1,
                "related_tools": trace.tools_used,
                "related_tasks": [self.context_manager.identify_task_type(trace.task_description)],
                "source": "auto"
            }
        )
        
        # 添加示例
        entry.add_example(
            task=trace.task_description,
            result="failure",
            reasoning=root_cause
        )
        
        entries.append(entry)
        
        self.logger.info(f"创建了 {len(entries)} 个流程失败条目")
        return entries
    
    def _curate_tool_insights(self,
                             insights: Dict[str, Any],
                             trace: ExecutionTrace) -> List[ContextEntry]:
        """
        整编工具失败洞见
        
        Args:
            insights: 洞见
            trace: 轨迹
            
        Returns:
            上下文条目列表
        """
        entries = []
        
        # 创建 TOOL_USAGE 类型条目
        tool_name = insights.get("tool_name", "")
        root_cause = insights.get("root_cause", "")
        best_practice = insights.get("tool_usage_best_practice", "")
        parameter_issues = insights.get("parameter_issues", [])
        prompt_optimization = insights.get("tool_prompt_optimization", {})
        
        # 构建内容
        content = f"【工具】{tool_name}\n"
        content += f"【失败原因】{root_cause}\n"
        content += f"【最佳实践】{best_practice}\n"
        
        if parameter_issues:
            content += "【参数建议】\n"
            for param in parameter_issues:
                content += f"- {param.get('parameter', '')}: {param.get('suggestion', '')}\n"
        
        if prompt_optimization.get("needs_optimization"):
            content += "【Prompt优化】\n"
            content += f"- 问题: {', '.join(prompt_optimization.get('current_issues', []))}\n"
            content += f"- 建议: {prompt_optimization.get('suggested_prompt', '')}\n"
        
        entry = ContextEntry(
            entry_type=ContextEntryType.TOOL_USAGE,
            content=content,
            metadata={
                "created_at": trace.timestamp,
                "last_used": trace.timestamp,
                "useful_count": 0,
                "harmful_count": 1,  # 失败案例初始为-1分
                "score": -1,
                "related_tools": [tool_name],
                "related_tasks": [self.context_manager.identify_task_type(trace.task_description)],
                "source": "auto"
            }
        )
        
        # 添加示例
        entry.add_example(
            task=trace.task_description,
            result="failure",
            reasoning=root_cause
        )
        
        entries.append(entry)
        
        self.logger.info(f"创建了 {len(entries)} 个工具失败条目")
        return entries
    
    def _curate_mixed_insights(self,
                              insights: Dict[str, Any],
                              trace: ExecutionTrace) -> List[ContextEntry]:
        """
        整编混合洞见
        
        Args:
            insights: 洞见
            trace: 轨迹
            
        Returns:
            上下文条目列表
        """
        entries = []
        
        workflow_analysis = insights.get("workflow_analysis", {})
        tool_analysis = insights.get("tool_analysis", {})
        
        # 如果有流程问题，创建 ERROR_PATTERN 条目
        if workflow_analysis.get("has_workflow_issues"):
            content = "【流程问题】\n"
            for issue in workflow_analysis.get("issues", []):
                content += f"- {issue}\n"
            content += "【建议】\n"
            for suggestion in workflow_analysis.get("suggestions", []):
                content += f"- {suggestion}\n"
            
            entry = ContextEntry(
                entry_type=ContextEntryType.ERROR_PATTERN,
                content=content,
                metadata={
                    "created_at": trace.timestamp,
                    "last_used": trace.timestamp,
                    "useful_count": 0,
                    "harmful_count": 1,
                    "score": -1,
                    "related_tools": trace.tools_used,
                    "related_tasks": [self.context_manager.identify_task_type(trace.task_description)],
                    "source": "auto"
                }
            )
            entries.append(entry)
        
        # 如果有工具问题，创建 TOOL_USAGE 条目
        if tool_analysis.get("has_tool_issues"):
            content = "【工具问题】\n"
            for issue in tool_analysis.get("issues", []):
                content += f"- {issue}\n"
            content += "【建议】\n"
            for suggestion in tool_analysis.get("suggestions", []):
                content += f"- {suggestion}\n"
            
            entry = ContextEntry(
                entry_type=ContextEntryType.TOOL_USAGE,
                content=content,
                metadata={
                    "created_at": trace.timestamp,
                    "last_used": trace.timestamp,
                    "useful_count": 0,
                    "harmful_count": 1,
                    "score": -1,
                    "related_tools": trace.tools_used,
                    "related_tasks": [self.context_manager.identify_task_type(trace.task_description)],
                    "source": "auto"
                }
            )
            entries.append(entry)
        
        self.logger.info(f"创建了 {len(entries)} 个混合失败条目")
        return entries
    
    def _curate_success_insights(self,
                                insights: Dict[str, Any],
                                trace: ExecutionTrace) -> List[ContextEntry]:
        """
        整编成功洞见
        
        Args:
            insights: 洞见
            trace: 轨迹
            
        Returns:
            上下文条目列表
        """
        entries = []
        
        # 创建 STRATEGY 类型条目
        success_strategies = insights.get("success_strategies", [])
        workflow_patterns = insights.get("workflow_patterns", [])
        
        if success_strategies or workflow_patterns:
            content = "【成功策略】\n"
            for strategy in success_strategies:
                content += f"- {strategy}\n"
            
            if workflow_patterns:
                content += "【流程模式】\n"
                for pattern in workflow_patterns:
                    content += f"- {pattern}\n"
            
            entry = ContextEntry(
                entry_type=ContextEntryType.STRATEGY,
                content=content,
                metadata={
                    "created_at": trace.timestamp,
                    "last_used": trace.timestamp,
                    "useful_count": 1,  # 成功案例初始为+1分
                    "harmful_count": 0,
                    "score": 1,
                    "related_tools": trace.tools_used,
                    "related_tasks": [self.context_manager.identify_task_type(trace.task_description)],
                    "source": "auto"
                }
            )
            
            entry.add_example(
                task=trace.task_description,
                result="success",
                reasoning="工作流执行成功"
            )
            
            entries.append(entry)
        
        # 创建 TOOL_USAGE 类型条目（工具最佳实践）
        tool_best_practices = insights.get("tool_best_practices", {})
        for tool_name, practice in tool_best_practices.items():
            content = f"【工具】{tool_name}\n"
            content += f"【最佳实践】{practice}\n"
            
            entry = ContextEntry(
                entry_type=ContextEntryType.TOOL_USAGE,
                content=content,
                metadata={
                    "created_at": trace.timestamp,
                    "last_used": trace.timestamp,
                    "useful_count": 1,
                    "harmful_count": 0,
                    "score": 1,
                    "related_tools": [tool_name],
                    "related_tasks": [self.context_manager.identify_task_type(trace.task_description)],
                    "source": "auto"
                }
            )
            
            entries.append(entry)
        
        self.logger.info(f"创建了 {len(entries)} 个成功条目")
        return entries
    
    def _curate_quality_issue_insights(self,
                                      insights: Dict[str, Any],
                                      trace: ExecutionTrace,
                                      reflection_chain=None) -> List[ContextEntry]:
        """
        整编质量问题洞见
        
        Args:
            insights: 洞见
            trace: 轨迹
            reflection_chain: 反思链对象（可选）
            
        Returns:
            上下文条目列表
        """
        entries = []
        
        # 提取关键信息
        problem_step = insights.get("problem_step", 0)
        root_cause = insights.get("root_cause", "未知原因")
        improvement_suggestions = insights.get("improvement_suggestions", [])
        prompt_optimization = insights.get("prompt_optimization", {})
        
        # 添加调试日志
        self.logger.debug(f"prompt_optimization原始内容: {prompt_optimization}")
        
        # 创建TOOL_USAGE类型条目（针对prompt优化）
        if prompt_optimization:
            tool_name = prompt_optimization.get("tool", "unknown")
            suggested_prompt = prompt_optimization.get("suggested_prompt", "")
            
            # 添加验证和日志
            if not suggested_prompt:
                self.logger.warning(f"prompt_optimization中没有suggested_prompt: {prompt_optimization}")
                return entries
            
            self.logger.info(f"✓ 提取到优化prompt，长度: {len(suggested_prompt)}字符")
            
            # 记录prompt优化到反思链
            if reflection_chain:
                # 尝试从trace中获取原始prompt（如果有）
                original_prompt = ""
                for step in trace.step_details:
                    if step.get("tool_name") == tool_name:
                        original_prompt = step.get("tool_input", {}).get("prompt", "")
                        break
                
                reflection_chain.add_entry(
                    stage="prompt_optimization",
                    input_data={
                        "tool_name": tool_name,
                        "original_prompt": original_prompt[:300] + "..." if len(original_prompt) > 300 else original_prompt,
                        "problem": root_cause,
                        "improvement_suggestions": improvement_suggestions
                    },
                    output_data={
                        "optimized_prompt": suggested_prompt,
                        "optimization_reasoning": f"根据{root_cause}，优化prompt以改进输出质量"
                    },
                    analysis=f"Prompt优化完成，预期改进: {', '.join(improvement_suggestions[:2])}"
                )
            
            # 输出到日志
            self.logger.info("=" * 80)
            self.logger.info(f"ACE生成的Prompt优化方案 - 工具: {tool_name}")
            self.logger.info("=" * 80)
            self.logger.info(f"问题根因: {root_cause}")
            self.logger.info(f"\n优化后的Prompt:\n{suggested_prompt}")
            self.logger.info("\n改进建议:")
            for i, suggestion in enumerate(improvement_suggestions, 1):
                self.logger.info(f"  {i}. {suggestion}")
            self.logger.info("=" * 80)
            
            content = f"【工具Prompt优化】{tool_name}\n"
            content += f"- 问题: {root_cause}\n"
            content += f"- 优化后的Prompt:\n{suggested_prompt}\n"
            content += "【改进建议】\n"
            for suggestion in improvement_suggestions:
                content += f"- {suggestion}\n"
            
            # 去重机制：检查是否已存在相似的优化建议
            task_type = self.context_manager.identify_task_type(trace.task_description)
            existing_entries = self.context_manager.load_context(task_type)
            
            is_duplicate = False
            for existing_entry in existing_entries:
                # 只检查TOOL_USAGE类型的条目
                if existing_entry.entry_type != ContextEntryType.TOOL_USAGE:
                    continue
                
                # 检查工具名是否相同
                if tool_name not in existing_entry.metadata.get("related_tools", []):
                    continue
                
                # 使用difflib计算相似度
                existing_content = existing_entry.content
                similarity = difflib.SequenceMatcher(None, content, existing_content).ratio()
                
                # 如果相似度超过80%，认为是重复
                if similarity > 0.8:
                    is_duplicate = True
                    self.logger.info(f"发现相似的优化建议（相似度: {similarity:.2%}），跳过创建")
                    self.logger.debug(f"现有条目ID: {existing_entry.entry_id}")
                    
                    # 更新现有条目的使用次数
                    existing_entry.update_last_used()
                    self.context_manager.save_context(task_type, existing_entries)
                    break
            
            # 只有不重复时才创建新条目
            if not is_duplicate:
                entry = ContextEntry(
                    entry_type=ContextEntryType.TOOL_USAGE,
                    content=content,
                    metadata={
                        "created_at": trace.timestamp,
                        "last_used": trace.timestamp,
                        "useful_count": 0,
                        "harmful_count": 1,  # 质量问题初始为-1分
                        "score": -1,
                        "related_tools": [tool_name],
                        "related_tasks": [task_type],
                        "source": "quality_feedback",
                        "optimized_prompt": suggested_prompt  # 存储优化后的prompt
                    }
                )
                
                # 添加示例
                entry.add_example(
                    task=trace.task_description,
                    result="quality_issue",
                    reasoning=root_cause
                )
                
                entries.append(entry)
                self.logger.info(f"创建新的优化建议条目")
            else:
                self.logger.info(f"跳过重复的优化建议")
        
        self.logger.info(f"创建了 {len(entries)} 个质量问题条目")
        return entries
    
    def update_context(self, task_type: str, new_entries: List[ContextEntry]) -> None:
        """
        更新上下文
        
        Args:
            task_type: 任务类型
            new_entries: 新条目列表
        """
        self.logger.info(f"更新上下文: {task_type}, 新增 {len(new_entries)} 个条目")
        
        try:
            # 加载现有条目
            existing_entries = self.context_manager.load_context(task_type)
            
            # 合并条目
            merged_entries = self.merge_entries(new_entries, existing_entries)
            
            # 去重
            deduplicated_entries = self.deduplicate_entries(merged_entries)
            
            # 限制数量（保留评分最高的100个）
            if len(deduplicated_entries) > 100:
                deduplicated_entries.sort(key=lambda e: e.metadata.get("score", 0), reverse=True)
                deduplicated_entries = deduplicated_entries[:100]
                self.logger.info(f"限制条目数量为100个")
            
            # 保存
            self.context_manager.save_context(task_type, deduplicated_entries)
            
            self.logger.info(f"上下文更新完成，当前共 {len(deduplicated_entries)} 个条目")
            
        except Exception as e:
            raise ACECurationError(f"更新上下文失败: {str(e)}")
    
    def merge_entries(self,
                     new_entries: List[ContextEntry],
                     existing_entries: List[ContextEntry]) -> List[ContextEntry]:
        """
        合并条目
        
        Args:
            new_entries: 新条目
            existing_entries: 现有条目
            
        Returns:
            合并后的条目列表
        """
        # 简单合并：直接添加新条目
        merged = existing_entries + new_entries
        return merged
    
    def deduplicate_entries(self, entries: List[ContextEntry]) -> List[ContextEntry]:
        """
        去重条目
        
        Args:
            entries: 条目列表
            
        Returns:
            去重后的条目列表
        """
        if not entries:
            return []
        
        unique_entries = []
        seen_contents = []
        
        for entry in entries:
            # 检查内容相似度
            is_duplicate = False
            for seen_content in seen_contents:
                similarity = self.calculate_similarity(entry.content, seen_content)
                if similarity > 0.85:  # 相似度阈值
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_entries.append(entry)
                seen_contents.append(entry.content)
        
        self.logger.info(f"去重: {len(entries)} -> {len(unique_entries)}")
        return unique_entries
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算文本相似度
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            相似度（0-1）
        """
        return difflib.SequenceMatcher(None, text1, text2).ratio()


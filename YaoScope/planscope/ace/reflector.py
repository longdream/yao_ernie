"""
ACE Reflector（反思器）
分析执行轨迹，区分流程失败和工具失败
"""
import json
import asyncio
from typing import Dict, Any, Optional

from planscope.ace.execution_trace import ExecutionTrace
from planscope.core.exceptions import ACEReflectionError


class ACEReflector:
    """
    ACE反思器
    
    负责分析执行轨迹，提取成功经验和失败教训
    区分流程失败和工具失败两种类型
    """
    
    # 失败类型常量
    WORKFLOW_FAILURE = "workflow"
    TOOL_FAILURE = "tool"
    MIXED_FAILURE = "mixed"
    
    def __init__(self, model_client, logger_manager):
        """
        初始化反思器
        
        Args:
            model_client: AgentScope模型客户端
            logger_manager: 日志管理器
        """
        self.model_client = model_client
        self.logger_manager = logger_manager
        self.logger = logger_manager.get_logger("ace_reflector")
    
    def analyze_trace(self, trace: ExecutionTrace) -> Dict[str, Any]:
        """
        分析轨迹（主入口）
        
        Args:
            trace: 执行轨迹
            
        Returns:
            分析结果
        """
        self.logger.info(f"开始分析轨迹: {trace.trace_id}")
        
        if trace.is_success():
            return self.identify_success_patterns(trace)
        else:
            # 分类失败类型
            failure_type = self.classify_failure_type(trace)
            self.logger.info(f"失败类型: {failure_type}")
            
            # 根据类型分析
            if failure_type == self.WORKFLOW_FAILURE:
                return self.analyze_workflow_failure(trace)
            elif failure_type == self.TOOL_FAILURE:
                return self.analyze_tool_failure(trace)
            else:
                # 混合分析
                return self.analyze_mixed_failure(trace)
    
    def classify_failure_type(self, trace: ExecutionTrace) -> str:
        """
        使用LLM+规则分类失败类型
        
        Args:
            trace: 执行轨迹
            
        Returns:
            失败类型（workflow/tool/mixed）
        """
        failure_info = trace.get_failure_info()
        if not failure_info:
            return self.MIXED_FAILURE
        
        error_message = failure_info.get("error", "")
        error_type = failure_info.get("error_type", "")
        
        # 规则1：明确的流程异常（快速判断）
        workflow_exceptions = ["ToolNotFoundError", "VariableResolutionError", "DependencyError", "PlanParsingError"]
        if any(exc in error_type for exc in workflow_exceptions):
            self.logger.info(f"规则判断：{error_type} -> WORKFLOW_FAILURE")
            return self.WORKFLOW_FAILURE
        
        # 规则2：明确的工具异常
        tool_exceptions = ["ValueError", "TypeError", "KeyError", "AttributeError"]
        if any(exc in error_type for exc in tool_exceptions) and "工具执行失败" in error_message:
            self.logger.info(f"规则判断：{error_type} -> TOOL_FAILURE")
            return self.TOOL_FAILURE
        
        # LLM深度分析（模糊情况）
        self.logger.info("使用LLM深度分析失败类型")
        
        prompt = f'''分析以下工作流执行失败的原因，判断是流程设计问题还是工具调用问题。

任务：{trace.task_description}
失败步骤ID：{failure_info.get("step_id")}
错误类型：{error_type}
错误信息：{error_message}

工作流结构：
{json.dumps(trace.plan_json, ensure_ascii=False, indent=2)[:1000]}

返回JSON格式：
{{
  "failure_type": "workflow 或 tool 或 mixed",
  "confidence": 0.95,
  "reasoning": "详细分析",
  "primary_cause": "主要原因",
  "secondary_causes": ["次要原因1", "次要原因2"]
}}

分类标准：
- workflow: 步骤依赖、顺序、工具选择、变量引用等流程设计问题
- tool: 工具参数、工具内部逻辑、工具Prompt等工具调用问题
- mixed: 同时存在两类问题

只返回JSON。'''
        
        try:
            result = asyncio.run(
                self.model_client.call_model_with_json_response(prompt=prompt)
            )
            
            failure_type = result.get("failure_type", "mixed")
            self.logger.info(f"LLM判断：{failure_type}, 置信度: {result.get('confidence', 0)}")
            
            # 映射到常量
            if "workflow" in failure_type.lower():
                return self.WORKFLOW_FAILURE
            elif "tool" in failure_type.lower():
                return self.TOOL_FAILURE
            else:
                return self.MIXED_FAILURE
                
        except Exception as e:
            self.logger.error(f"LLM分析失败: {str(e)}")
            raise  # 直接抛出异常，不返回降级值
    
    def analyze_workflow_failure(self, trace: ExecutionTrace) -> Dict[str, Any]:
        """
        分析流程失败
        
        Args:
            trace: 执行轨迹
            
        Returns:
            分析结果
        """
        self.logger.info("分析流程失败")
        
        # 构建 Prompt
        prompt = self._build_workflow_failure_prompt(trace)
        
        # 调用 LLM 分析
        try:
            insights = asyncio.run(
                self.model_client.call_model_with_json_response(prompt=prompt)
            )
            
            # 确保包含 failure_type
            insights["failure_type"] = self.WORKFLOW_FAILURE
            
            self.logger.info("流程失败分析完成")
            return insights
            
        except Exception as e:
            self.logger.error(f"流程失败分析失败: {str(e)}")
            raise ACEReflectionError(f"流程失败分析失败: {str(e)}")
    
    def analyze_tool_failure(self, trace: ExecutionTrace) -> Dict[str, Any]:
        """
        分析工具失败
        
        Args:
            trace: 执行轨迹
            
        Returns:
            分析结果
        """
        self.logger.info("分析工具失败")
        
        # 构建 Prompt
        prompt = self._build_tool_failure_prompt(trace)
        
        # 调用 LLM 分析
        try:
            insights = asyncio.run(
                self.model_client.call_model_with_json_response(prompt=prompt)
            )
            
            # 确保包含 failure_type
            insights["failure_type"] = self.TOOL_FAILURE
            
            self.logger.info("工具失败分析完成")
            return insights
            
        except Exception as e:
            self.logger.error(f"工具失败分析失败: {str(e)}")
            raise ACEReflectionError(f"工具失败分析失败: {str(e)}")
    
    def analyze_mixed_failure(self, trace: ExecutionTrace) -> Dict[str, Any]:
        """
        混合分析（同时分析流程和工具问题）
        
        Args:
            trace: 执行轨迹
            
        Returns:
            分析结果
        """
        self.logger.info("进行混合失败分析")
        
        # 构建 Prompt
        prompt = self._build_mixed_failure_prompt(trace)
        
        # 调用 LLM 分析
        try:
            insights = asyncio.run(
                self.model_client.call_model_with_json_response(prompt=prompt)
            )
            
            insights["failure_type"] = self.MIXED_FAILURE
            
            self.logger.info("混合失败分析完成")
            return insights
            
        except Exception as e:
            self.logger.error(f"混合失败分析失败: {str(e)}")
            raise ACEReflectionError(f"混合失败分析失败: {str(e)}")
    
    def analyze_quality_issue(self,
                             trace: ExecutionTrace,
                             feedback: str,
                             reflection_chain=None) -> Dict[str, Any]:
        """
        分析质量问题（执行成功但输出质量不佳）
        
        Args:
            trace: 执行轨迹
            feedback: 用户反馈
            reflection_chain: 反思链对象（可选）
            
        Returns:
            分析结果
        """
        self.logger.info("分析质量问题")
        
        # 从用户反馈中提取实际输出和期望输出
        actual_output = ""
        expected_output = ""
        problem_desc = feedback
        
        # 尝试解析结构化反馈
        if "实际输出:" in feedback and "期望输出:" in feedback:
            lines = feedback.split('\n')
            for line in lines:
                if "实际输出:" in line:
                    actual_output = line.split("实际输出:")[-1].strip()
                elif "期望输出:" in line:
                    expected_output = line.split("期望输出:")[-1].strip()
                elif "问题描述:" in line:
                    problem_desc = line.split("问题描述:")[-1].strip()
        
        # 提取问题步骤的工具信息和schema
        problem_tool_schema = ""
        problem_tool_name = ""
        for step_detail in trace.step_details:
            # 尝试从问题描述中提取工具名
            if problem_desc and any(keyword in problem_desc.lower() for keyword in ['vl', '提取', '图片', '识别']):
                # 找VL工具
                if step_detail.get("tool_name") == "vl_extract_image_content" or "extract" in step_detail.get("tool_name", "").lower():
                    problem_tool_name = step_detail.get("tool_name", "")
                    # 从step_detail的metadata中获取output_json_schema
                    metadata = step_detail.get("metadata", {})
                    if isinstance(metadata, dict) and "output_json_schema" in metadata:
                        problem_tool_schema = metadata["output_json_schema"]
                    break
            elif problem_desc and any(keyword in problem_desc.lower() for keyword in ['llm', '分析', '理解', '回复']):
                # 找LLM工具
                if "analyze" in step_detail.get("tool_name", "").lower() or "reply" in step_detail.get("tool_name", "").lower():
                    problem_tool_name = step_detail.get("tool_name", "")
                    # 从step_detail的metadata中获取output_json_schema
                    metadata = step_detail.get("metadata", {})
                    if isinstance(metadata, dict) and "output_json_schema" in metadata:
                        problem_tool_schema = metadata["output_json_schema"]
                    break
        
        # 构建工具schema约束说明
        schema_constraint = ""
        if problem_tool_schema:
            schema_constraint = f"""

⚠️ 重要约束：该工具已定义OUTPUT_JSON_SCHEMA，优化后的prompt必须遵守此schema：
{problem_tool_schema}

优化prompt时的关键规则：
1. **不要在prompt中定义新的JSON格式** - 工具的OUTPUT_JSON_SCHEMA已经定义了返回格式
2. **只优化任务描述部分** - 详细描述需要提取/分析什么内容、如何组织内容
3. **必须明确要求将所有内容整合为单一文本字符串** - 例如："将所有对话内容（包括发言人、时间、消息）整合为一段完整的文本字符串，按对话顺序组织"
4. **示例对比**：
   - ❌ 错误："返回JSON格式: {{'messages': [...], 'group_info': '...'}}" （定义了新格式，与schema冲突）
   - ❌ 错误："提取所有对话内容，包括发言人、时间戳和具体对话内容" （可能导致VL模型返回结构化数据而非单一文本）
   - ✅ 正确："提取所有对话内容（发言人、时间、消息），将它们整合为一段完整的文本字符串，按对话顺序组织，确保保留上下文关系" （明确要求整合为单一文本）
"""
        
        # 构建增强的prompt（包含实际vs期望对比和schema约束）
        prompt = f"""执行成功但用户反馈质量不佳，请进行深入分析：

任务描述：{trace.task_description}

执行步骤：
{json.dumps(trace.step_details, ensure_ascii=False, indent=2)}

输出质量对比：
- 实际输出: {actual_output if actual_output else '（见用户反馈）'}
- 期望输出: {expected_output if expected_output else '（未明确提供）'}

用户反馈：
{feedback}

请深入分析：
1. 对比分析：实际输出与期望输出的差距在哪里？
2. 根因定位：
   - 如果是VL工具：提取的内容是否准确？是否遗漏关键信息？
   - 如果是LLM工具：理解是否正确？生成的内容是否符合要求？
   - 如果是流程问题：步骤顺序是否合理？是否缺少必要步骤？
3. 改进方案：
   - Prompt优化：如何修改prompt来获得期望的输出？
   - 流程调整：是否需要调整步骤顺序或增加验证步骤？
   - 参数调整：是否需要调整temperature等参数？

{schema_constraint}

⚠️⚠️⚠️ 关键提醒：优化后的prompt中绝对不能包含JSON格式定义（如"返回JSON格式"、定义字段等），因为工具的OUTPUT_JSON_SCHEMA已经定义了返回格式！

返回JSON格式：
{{
  "problem_step": 步骤ID（整数），
  "root_cause": "根本原因（详细说明实际vs期望的差距）",
  "improvement_suggestions": ["具体的改进建议1", "具体的改进建议2"],
  "prompt_optimization": {{
    "tool": "工具名", 
    "suggested_prompt": "优化后的prompt（⚠️ 关键：只能包含任务描述、内容要求、组织方式，绝对不能包含JSON格式定义、不能定义返回字段！示例：'提取对话内容并按发言人组织'而非'返回JSON格式：{{..}}'）"
  }}
}}
"""
        
        # 记录质量分析输入到反思链
        if reflection_chain:
            reflection_chain.add_entry(
                stage="quality_analysis",
                input_data={
                    "task_description": trace.task_description,
                    "execution_steps": trace.step_details,
                    "user_feedback": feedback,
                    "analysis_prompt": prompt[:500] + "..." if len(prompt) > 500 else prompt,
                    "prompt_length": len(prompt)
                },
                model_info={
                    "model_name": getattr(self.model_client, 'model_name', 'unknown')
                }
            )
        
        try:
            insights = asyncio.run(
                self.model_client.call_model_with_json_response(prompt=prompt)
            )
            insights["failure_type"] = "quality_issue"
            
            # 记录质量分析输出到反思链
            if reflection_chain:
                reflection_chain.add_entry(
                    stage="quality_analysis_result",
                    output_data={
                        "problem_step": insights.get("problem_step"),
                        "root_cause": insights.get("root_cause", ""),
                        "improvement_suggestions": insights.get("improvement_suggestions", []),
                        "prompt_optimization": insights.get("prompt_optimization", {})
                    },
                    analysis=f"识别到质量问题: {insights.get('root_cause', '')}"
                )
            
            self.logger.info("质量问题分析完成")
            return insights
        except Exception as e:
            self.logger.error(f"质量问题分析失败: {str(e)}")
            raise ACEReflectionError(f"质量问题分析失败: {str(e)}")
    
    def identify_success_patterns(self, trace: ExecutionTrace) -> Dict[str, Any]:
        """
        识别成功模式
        
        Args:
            trace: 执行轨迹
            
        Returns:
            成功模式分析结果
        """
        self.logger.info("识别成功模式")
        
        # 构建 Prompt
        prompt = self._build_success_prompt(trace)
        
        # 调用 LLM 分析
        try:
            insights = asyncio.run(
                self.model_client.call_model_with_json_response(prompt=prompt)
            )
            
            insights["failure_type"] = "success"
            
            self.logger.info("成功模式识别完成")
            return insights
            
        except Exception as e:
            self.logger.error(f"成功模式识别失败: {str(e)}")
            # 返回默认结果
            return {
                "failure_type": "success",
                "success_strategies": ["工作流执行成功"],
                "tool_best_practices": {}
            }
    
    def _build_workflow_failure_prompt(self, trace: ExecutionTrace) -> str:
        """构建流程失败分析 Prompt"""
        failure_info = trace.get_failure_info()
        failed_step_id = failure_info.get("step_id") if failure_info else None
        error_message = failure_info.get("error", "") if failure_info else ""
        
        # 获取失败步骤的详情
        failed_step = None
        for step in trace.plan_json.get("steps", []):
            if step.get("step_id") == failed_step_id:
                failed_step = step
                break
        
        prompt = f"""你是工作流设计专家。分析以下流程设计问题：

【任务描述】
{trace.task_description}

【生成的工作流】
{json.dumps(trace.plan_json, ensure_ascii=False, indent=2)}

【执行情况】
- 已执行步骤：{trace.execution_result.get("executed_steps", [])}
- 失败步骤：{failed_step_id}
- 失败步骤详情：{json.dumps(failed_step, ensure_ascii=False) if failed_step else "N/A"}
- 错误信息：{error_message}

【分析要点】
1. 步骤依赖关系是否合理？
2. 步骤顺序是否正确？
3. 是否缺少必要的中间步骤？
4. 工具选择是否恰当？
5. 变量引用是否正确？

请以JSON格式返回分析结果：
{{
  "failure_type": "workflow",
  "root_cause": "流程设计的根本原因",
  "workflow_issues": [
    {{
      "issue": "具体问题描述",
      "location": "步骤X或依赖关系",
      "suggestion": "改进建议"
    }}
  ],
  "improved_workflow_strategy": "改进后的整体流程策略",
  "steps_to_add": ["建议添加的步骤描述"],
  "steps_to_remove": ["建议删除的步骤ID"],
  "steps_to_reorder": [{{"from": 2, "to": 1, "reason": "原因"}}]
}}

只返回JSON，不要有其他说明文字。"""
        
        return prompt
    
    def _build_tool_failure_prompt(self, trace: ExecutionTrace) -> str:
        """构建工具失败分析 Prompt"""
        failure_info = trace.get_failure_info()
        failed_step_id = failure_info.get("step_id") if failure_info else None
        error_message = failure_info.get("error", "") if failure_info else ""
        traceback = failure_info.get("traceback", "") if failure_info else ""
        
        # 获取失败步骤的详情
        failed_step_detail = None
        for detail in trace.step_details:
            if detail.get("step_id") == failed_step_id:
                failed_step_detail = detail
                break
        
        tool_name = failed_step_detail.get("tool_name", "unknown") if failed_step_detail else "unknown"
        tool_input = failed_step_detail.get("tool_input", {}) if failed_step_detail else {}
        tool_metadata = failed_step_detail.get("metadata", {}) if failed_step_detail else {}
        
        # 构建工具schema约束说明
        schema_constraint = ""
        if tool_metadata and "output_json_schema" in tool_metadata:
            schema_constraint = f"""

⚠️ 重要约束：该工具已定义OUTPUT_JSON_SCHEMA，优化后的prompt必须遵守此schema：
{tool_metadata["output_json_schema"]}

优化prompt时的关键规则：
1. **不要在prompt中定义新的JSON格式** - 工具的OUTPUT_JSON_SCHEMA已经定义了返回格式
2. **只优化任务描述部分** - 详细描述需要提取/分析什么内容、如何组织内容
3. **必须明确要求将所有内容整合为单一文本字符串** - 例如："将所有对话内容（包括发言人、时间、消息）整合为一段完整的文本字符串，按对话顺序组织"
4. **示例对比**：
   - ❌ 错误："返回JSON格式: {{'messages': [...], 'group_info': '...'}}" （定义了新格式，与schema冲突）
   - ❌ 错误："提取所有对话内容，包括发言人、时间戳和具体对话内容" （可能导致VL模型返回结构化数据而非单一文本）
   - ✅ 正确："提取所有对话内容（发言人、时间、消息），将它们整合为一段完整的文本字符串，按对话顺序组织，确保保留上下文关系" （明确要求整合为单一文本）
"""
        
        prompt = f"""你是工具调用优化专家。分析以下工具调用问题：

【任务描述】
{trace.task_description}

【失败的步骤】
- 步骤ID：{failed_step_id}
- 工具名称：{tool_name}
- 工具输入：{json.dumps(tool_input, ensure_ascii=False, indent=2)}
- 错误信息：{error_message}
- 错误堆栈：
{traceback}

【分析要点】
1. 工具输入参数是否正确？
2. 参数类型是否匹配？
3. 是否缺少必需参数？
4. 参数值是否在合理范围内？
5. 是否需要优化工具内部的 Prompt（如果工具内部调用 LLM）？
{schema_constraint}

请以JSON格式返回分析结果：
{{
  "failure_type": "tool",
  "tool_name": "{tool_name}",
  "root_cause": "工具失败的根本原因",
  "parameter_issues": [
    {{
      "parameter": "参数名",
      "issue": "问题描述",
      "current_value": "当前值",
      "suggested_value": "建议值",
      "reason": "原因"
    }}
  ],
  "tool_prompt_optimization": {{
    "needs_optimization": true,
    "current_issues": ["问题1", "问题2"],
    "suggested_prompt": "优化后的 Prompt",
    "optimization_reason": "优化原因"
  }},
  "tool_usage_best_practice": "该工具的最佳使用实践"
}}

只返回JSON，不要有其他说明文字。"""
        
        return prompt
    
    def _build_mixed_failure_prompt(self, trace: ExecutionTrace) -> str:
        """构建混合失败分析 Prompt"""
        failure_info = trace.get_failure_info()
        failed_step_id = failure_info.get("step_id") if failure_info else None
        error_message = failure_info.get("error", "") if failure_info else ""
        
        prompt = f"""你是全面的工作流诊断专家。以下工作流执行失败，请全面分析可能的原因。

【任务描述】
{trace.task_description}

【工作流】
{json.dumps(trace.plan_json, ensure_ascii=False, indent=2)}

【失败信息】
- 失败步骤：{failed_step_id}
- 错误信息：{error_message}
- 已执行步骤：{trace.execution_result.get("executed_steps", [])}

请同时分析：
1. 流程设计层面的问题
2. 工具调用层面的问题

返回JSON格式：
{{
  "failure_type": "mixed",
  "workflow_analysis": {{
    "has_workflow_issues": true,
    "issues": ["问题1", "问题2"],
    "suggestions": ["建议1", "建议2"]
  }},
  "tool_analysis": {{
    "has_tool_issues": true,
    "issues": ["问题1", "问题2"],
    "suggestions": ["建议1", "建议2"]
  }},
  "primary_cause": "workflow或tool",
  "recommendations": ["综合改进建议"]
}}

只返回JSON，不要有其他说明文字。"""
        
        return prompt
    
    def _build_success_prompt(self, trace: ExecutionTrace) -> str:
        """构建成功模式分析 Prompt"""
        prompt = f"""你是工作流分析专家。以下工作流执行成功，请提取关键成功经验。

【任务描述】
{trace.task_description}

【工作流】
{json.dumps(trace.plan_json, ensure_ascii=False, indent=2)}

【执行结果】
- 执行步骤：{trace.execution_result.get("executed_steps", [])}
- 总耗时：{trace.execution_result.get("execution_time", 0)}秒
- 使用的工具：{trace.tools_used}

请提取成功经验，返回JSON格式：
{{
  "success_strategies": ["成功策略1", "成功策略2"],
  "tool_best_practices": {{
    "tool1": "最佳实践描述",
    "tool2": "最佳实践描述"
  }},
  "workflow_patterns": ["可复用的流程模式"],
  "key_insights": ["关键洞见"]
}}

只返回JSON，不要有其他说明文字。"""
        
        return prompt


"""
工具推荐器
根据用户需求分析并推荐合适的工具
"""
from typing import Dict, Any, List, Optional
import json


class ToolRecommender:
    """
    工具推荐器
    
    职责：
    1. 分析用户需求
    2. 从可用工具池中推荐合适的工具
    3. 支持动态工具发现
    """
    
    def __init__(self, model_client, logger, available_tools: Optional[Dict[str, Any]] = None):
        """
        初始化工具推荐器
        
        Args:
            model_client: LLM客户端
            logger: 日志记录器
            available_tools: 可用工具字典 {tool_name: tool_info}
        """
        self.model_client = model_client
        self.logger = logger
        self.available_tools = available_tools or {}
    
    def register_available_tool(self, name: str, func: Any, description: str = "") -> None:
        """
        注册可用工具（但不立即分析metadata）
        
        Args:
            name: 工具名称
            func: 工具函数
            description: 简短描述
        """
        self.available_tools[name] = {
            "name": name,
            "func": func,
            "description": description
        }
        self.logger.debug(f"工具 '{name}' 已添加到可用工具池")
    
    async def recommend_tools(self, user_prompt: str) -> List[str]:
        """
        根据用户需求推荐工具
        
        Args:
            user_prompt: 用户需求描述
            
        Returns:
            推荐的工具名称列表（2-5个）
        """
        if not self.available_tools:
            self.logger.warning("可用工具池为空，无法推荐工具")
            return []
        
        # 记录工具库信息
        self.logger.info(f"工具库中有 {len(self.available_tools)} 个工具")
        
        # 构建工具列表描述
        tools_desc = self._build_tools_description()
        
        # 构建推荐prompt
        recommend_prompt = f"""你是一个工具推荐专家。根据用户的需求，从可用工具中选择最合适的工具。

**用户需求：**
{user_prompt}

**可用工具（共{len(self.available_tools)}个）：**
{tools_desc}

**任务：**
分析用户需求，根据每个工具的描述和适用场景，选择最合适的工具组合。

**分析步骤：**
1. 理解任务目标：用户想要实现什么？
2. 分解子任务：需要哪些步骤？
3. 匹配工具能力：仔细阅读每个工具的描述、特点、适用场景
4. 注意工具限制：避免在不适用场景使用工具

**工具选择原则：**
- VL（Vision-Language）工具：适合语义理解、场景识别、对话提取
- OCR工具：适合精确文字提取，需要完整原文的场景
- 根据任务特点选择合适的工具，不要生搬硬套
- 考虑工具之间的数据传递（如OCR需要图片路径输入）

**常见任务的标准工具组合**：

1. **微信/QQ聊天回复任务**（关键词：微信、QQ、聊天、回复）：
   → 推荐工具：["screenshot_and_analyze", "general_llm_processor"]
   → 原因：VL能识别气泡位置（左=对方，右=我），无需OCR

2. **文档续写/改写/扩写任务** 🔥 **（必须严格遵守）**：
   **触发关键词（满足任一即触发）**：
   - "续写" / "改写" / "扩写" / "补充" / "完善"
   - "记事本" / "notepad" / "Notepad"
   - "Word" / "word" / "winword" / "WINWORD"
   - "写字板" / "WordPad" / "wordpad"
   - "VSCode" / "vscode" / "Code" / "code"
   - "Notepad++" / "notepad++"
   - "Sublime" / "sublime"
   - "文档" / "文本编辑器" / "编辑器"
   
   → **强制推荐工具（必须3个）**：["screenshot_and_analyze", "ocr_extract_text", "general_llm_processor"]
   → 原因：需要精确的原文内容，必须使用OCR，缺一不可！

3. **聊天总结任务**（关键词：总结、微信、QQ、聊天记录）：
   → 推荐工具：["screenshot_and_analyze", "scroll", "general_llm_processor"]
   → 原因：需要滚动查看更多内容后总结

4. **界面操作任务**（关键词：点击、滚动、输入、操作）：
   → 推荐工具：["screenshot_and_analyze", "click_element", "type_text", "scroll"]
   → 原因：需要识别界面元素并操作

**选择数量：**
- 只选择完成任务必需的工具（2-5个）
- 优先选择直接相关的工具
- 避免冗余工具
- **重要**：必须选择足够的工具来完成整个任务流程

**输出格式（JSON）：**
{{
  "analysis": "对用户需求的分析",
  "recommended_tools": ["tool1", "tool2"],
  "reasoning": "推荐这些工具的理由"
}}

请严格按JSON格式返回。"""

        try:
            # 调用LLM（使用AgentScopeModelClient的call_model方法）
            import asyncio
            
            # 检测是否在事件循环中
            try:
                loop = asyncio.get_running_loop()
                # 在事件循环中，直接await
                content = await self.model_client.call_model(recommend_prompt)
            except RuntimeError:
                # 不在事件循环中，使用asyncio.run
                content = asyncio.run(self.model_client.call_model(recommend_prompt))
            
            self.logger.debug(f"工具推荐LLM响应: {content[:200]}...")
            
            # 提取JSON
            result = self._extract_json(content)
            
            if result and "recommended_tools" in result:
                recommended = result["recommended_tools"]
                
                # 验证推荐数量
                if len(recommended) > 5:
                    self.logger.warning(f"LLM推荐了{len(recommended)}个工具，超过限制(5个)，将截取前5个")
                    recommended = recommended[:5]
                
                # 详细日志
                self.logger.info(f"LLM推荐了 {len(recommended)} 个工具: {recommended}")
                self.logger.debug(f"需求分析: {result.get('analysis', 'N/A')}")
                self.logger.debug(f"推荐理由: {result.get('reasoning', 'N/A')}")
                
                return recommended
            else:
                self.logger.warning("LLM未返回有效的工具推荐")
                return []
                
        except Exception as e:
            self.logger.error(f"工具推荐失败: {e}")
            raise RuntimeError(f"工具推荐失败: {e}") from e
    
    def _build_tools_description(self) -> str:
        """构建工具列表描述（使用完整描述）"""
        desc_lines = []
        for tool_name, tool_info in self.available_tools.items():
            desc = tool_info.get("description", "无描述")
            # 格式化为结构化描述
            desc_lines.append(f"\n【{tool_name}】")
            desc_lines.append(desc)  # 完整的TOOL_DESCRIPTION（多行）
            desc_lines.append("")  # 空行分隔
        return "\n".join(desc_lines)
    
    def _extract_json(self, content: str) -> Optional[Dict[str, Any]]:
        """从LLM响应中提取JSON"""
        try:
            # 尝试直接解析
            return json.loads(content)
        except json.JSONDecodeError:
            # 尝试提取代码块中的JSON
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            
            # 尝试提取第一个完整的JSON对象
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass
            
            self.logger.warning(f"无法从响应中提取JSON: {content[:200]}")
            return None
    
    def get_tool_func(self, tool_name: str) -> Optional[Any]:
        """
        获取工具函数
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具函数，如果不存在返回None
        """
        tool_info = self.available_tools.get(tool_name)
        if tool_info:
            return tool_info.get("func")
        return None


"""
流程生成器
通过AgentScope调用LLM生成工作流JSON
"""
import json
import time
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from planscope.core.exceptions import PlanGenerationError
from planscope.utils.json_validator import PlanJSONValidator


class PlanGenerator:
    """
    流程生成器
    使用LLM根据用户prompt生成工作流JSON
    """
    
    DEFAULT_PROMPT_TEMPLATE = """你是一个工作流规划专家。请根据用户的需求和可用工具，生成一个详细的执行计划。

用户需求：{user_prompt}

可用工具：
{available_tools_description}

请生成一个JSON格式的工作流计划，包含以下结构：
{{
  "steps": [
    {{
      "step_id": 1,
      "description": "步骤描述",
      "tool": "工具名称",
      "tool_input": {{
        "参数名1": "参数值1",
        "参数名2": "参数值2"
      }},
      "dependencies": [],
      "reasoning": "选择该步骤的原因"
    }}
  ],
  "overall_strategy": "整体策略描述",
  "complexity_level": "simple/medium/complex",
  "estimated_steps": 步骤数量
}}

⚠️ 重要：tool_input中的示例
- 如果工具需要app_name参数（截图工具），写为："app_name": "应用名"（字符串，不是数组）
- 如果工具需要max_scrolls参数，写为："max_scrolls": 5
- 如果工具需要mouse_coords参数，写为："mouse_coords": {{"x": 10, "y": 80}} （注意：是JSON对象，不是字符串）

【关于prompt参数】
如果工具需要prompt参数（通常是VL/LLM类工具）：
- 只需描述任务内容，专注于"做什么"和"提取什么信息"
- 可以在prompt字段中使用 {{{{steps.X.field}}}} 引用前序步骤的输出
- 示例："prompt": "分析以下内容：{{{{steps.1.content}}}}"
- ⚠️ 禁止包含任何输出格式说明：不要写"输出格式"、"返回格式"、"JSON"、"Schema"等词汇

要求：
1. step_id必须从1开始连续递增
2. dependencies数组包含该步骤依赖的其他步骤的step_id
3. tool_input中引用前面步骤输出的变量，使用格式 {{{{steps.X.field}}}}（双层花括号）
   - 这是步骤输出引用，会被VariableResolver处理
   - 示例：{{{{steps.1.content}}}}、{{{{steps.2.content}}}}
   - ⚠️ 重要：必须根据工具的output_json_schema使用正确的字段名
4. 对于需要prompt参数的工具，只描述任务内容
   - 示例："prompt": "提取以下图片内容"（第一步，无依赖）
   - 示例："prompt": "分析聊天记录：{{{{steps.1.content}}}}"（第二步，依赖第一步）
   - ⚠️ 禁止包含任何格式说明：不要写"输出格式"、"返回"、"JSON"等词汇
5. 确保依赖关系正确，不能有循环依赖
6. 根据工具的能力范围和局限性选择合适的工具，不要超出工具的能力边界
7. 参考工具的最佳实践和适用场景进行规划
8. 只返回JSON，不要有其他说明文字

【重要提示】
请根据每个工具的描述、特点和适用场景来规划工作流：

**VL vs OCR 的关键区别**：
- **screenshot_and_analyze（VL工具）**：
  * 使用多模态大模型理解图片语义
  * 适合：聊天记录提取、界面理解、场景识别
  * 局限：不适合精确文字识别，对长文本可能有遗漏或改写
  * 输出：语义分析结果 + screenshot_path（截图路径）
  
- **ocr_extract_text（OCR工具）**：
  * 使用OCR技术逐字逐行精确识别
  * 适合：文档内容提取、需要完整原文的任务
  * 输入：image_path（通常来自screenshot_and_analyze的screenshot_path）
  * 输出：精确的完整文字内容（保持原格式）

🔥 **工具选择强制规则 - 必须严格遵守**：

**⚠️ 规则1：文档/代码编辑器 → 必须3步**
判断依据：如果 app_name 包含以下任一关键词（不区分大小写）：
- "记事本" / "notepad"
- "Word" / "word" / "winword"  
- "写字板" / "wordpad"
- "VSCode" / "vscode" / "code"
- "Notepad++" / "notepad++"
- "Sublime" / "sublime"
- "PDF" / "pdf"
- 或任何其他文档/代码编辑器名称

**强制要求（必须包含3个步骤，缺一不可）**：
```json
{{
  "steps": [
    {{
      "step_id": 1,
      "tool": "screenshot_and_analyze",
      "tool_input": {{
        "app_name": "记事本",
        "prompt": "截取文档编辑区域"
      }}
    }},
    {{
      "step_id": 2,
      "tool": "ocr_extract_text",
      "tool_input": {{
        "image_path": "{{{{steps.1.screenshot_path}}}}"
      }}
    }},
    {{
      "step_id": 3,
      "tool": "general_llm_processor",
      "tool_input": {{
        "content": "{{{{steps.2.content}}}}",
        "prompt": "**第一步**：删除工具栏文字。**第二步**：续写/改写/扩写正文"
      }}
    }}
  ]
}}
```

**⚠️ 禁止使用2步流程**：
❌ 错误示例（缺少OCR步骤）：
```json
{{
  "steps": [
    {{"step_id": 1, "tool": "screenshot_and_analyze", ...}},
    {{"step_id": 2, "tool": "general_llm_processor", ...}}  ← 错误！缺少OCR
  ]
}}
```

**规则2：聊天应用 → 使用2步**
如果 app_name 是聊天应用（微信、QQ、钉钉等）：
→ 使用 screenshot_and_analyze（VL能识别气泡位置）→ general_llm_processor

**常见任务的标准Workflow模板**：

1. **微信/QQ聊天回复任务**：
   步骤1: screenshot_and_analyze
     - app_name: "微信" 或 "QQ"
     - prompt: "提取聊天记录"
   步骤2: general_llm_processor
     - content: "{{{{steps.1.content}}}}"
     - prompt: "分析聊天内容并生成回复"
   
   ⚠️ 注意：
   - 第一步必须是screenshot_and_analyze（截图+VL分析）
   - 不要使用OCR工具，VL能识别气泡位置（左/右）

2. **文档续写/改写/扩写任务**（🔥 必须严格遵守）：
   
   ⚠️ 应用类型判断：
   如果 app_name 包含以下关键词之一，必须使用OCR流程：
   - "记事本" / "Notepad" / "notepad"
   - "Word" / "WINWORD"
   - "写字板" / "WordPad"
   - "VSCode" / "Code"
   - "Notepad++"
   - 其他任何文档/代码编辑器
   
   **强制三步流程**：
   步骤1: screenshot_and_analyze
     - app_name: "记事本" 或相应的文档应用
     - prompt: "截取文档编辑区域"（仅截图，不要求文字提取）
   
   步骤2: ocr_extract_text
     - image_path: "{{{{steps.1.screenshot_path}}}}"
     - language: "ch"
     ⚠️ OCR只负责图片→文字转换，不做内容过滤
   
   步骤3: general_llm_processor
     - content: "{{{{steps.2.content}}}}"
     - prompt: "**第一步**：识别并删除所有非正文内容（如果OCR结果中包含工具栏文字如'文件'、'编辑'、'查看'、'格式'等，这些通常在文本的最上方或最下方，请删除）。**第二步**：对纯正文内容进行续写/改写/扩写..."
     ⚠️ LLM负责过滤非正文内容，OCR只负责识别
     
   🔥 三个必须：
   1. 必须使用 ocr_extract_text（不能只用VL）
   2. 必须在步骤2引用 {{{{steps.1.screenshot_path}}}}
   3. 必须在步骤3的prompt最前面加过滤指令

3. **聊天总结任务**：
   步骤1: screenshot_and_analyze
     - app_name: "微信" 或 "QQ"
     - prompt: "提取聊天记录"
   步骤2: scroll
     - direction: "up"
     - distance: 500
     - app_name: "微信"
   步骤3: screenshot_and_analyze
     - app_name: "微信"
     - prompt: "提取更多聊天记录"
   步骤4: general_llm_processor
     - content: "{{{{steps.1.content}}}} {{{{steps.3.content}}}}"
     - prompt: "总结聊天内容"

**Prompt设计原则**：
- 根据任务需求设计合适的prompt
- **续写任务**：明确要求"只返回新续写的内容，不要重复原文"，续写长度100-200字
- **改写/扩写任务**：要求输出完整的改写后文本
- 让prompt清晰、具体、可执行
- **重要**：如果工具描述中有特殊识别规则（如微信聊天的左右识别规则），需要在prompt中明确要求VL模型遵循这些规则

**续写任务 Prompt 模板**：
```
**第一步**：识别并删除所有非正文内容（工具栏文字等）。
**第二步**：理解原文内容和风格。
**第三步**：从原文最后一个字开始续写新内容（100-200字）。
**重要**：只返回新续写的部分，不要重复原文。
```

请生成工作流计划："""
    
    def __init__(self, model_client, logger_manager, work_dir: str, storage_manager=None):
        """
        初始化流程生成器
        
        Args:
            model_client: AgentScope模型客户端
            logger_manager: 日志管理器
            work_dir: 工作目录
            storage_manager: 存储管理器（可选，用于统一管理目录）
        """
        self.model_client = model_client
        self.logger_manager = logger_manager
        self.logger = logger_manager.get_logger("plan_generator")
        self.work_dir = Path(work_dir)
        self.storage_manager = storage_manager
        
        # 使用StorageManager或默认路径
        if storage_manager:
            self.plans_dir = storage_manager.get_path("plans")
        else:
            # Fallback: 与StorageManager的定义保持一致
            self.plans_dir = self.work_dir / "persistent" / "plans"
            self.plans_dir.mkdir(parents=True, exist_ok=True)
    
    async def generate(self,
                      user_prompt: str,
                      tool_registry=None,
                      prompt_template: Optional[str] = None,
                      save_to_file: bool = True,
                      **kwargs) -> Dict[str, Any]:
        """
        生成工作流计划
        
        Args:
            user_prompt: 用户需求描述
            tool_registry: 工具注册表（可选），用于获取工具描述
            prompt_template: 自定义prompt模板（可选）
            save_to_file: 是否保存到文件
            **kwargs: 传递给LLM的额外参数
            
        Returns:
            工作流JSON对象
            
        Raises:
            PlanGenerationError: 生成失败
        """
        self.logger.info("开始生成工作流计划")
        self.logger.info(f"用户需求: {user_prompt}")
        
        try:
            # 获取工具描述
            tools_desc = ""
            if tool_registry:
                tools_desc = tool_registry.get_all_tools_description()
                self.logger.info(f"已注入 {len(tool_registry.list_tools())} 个工具的描述")
            else:
                tools_desc = "暂无可用工具"
                self.logger.warning("未提供工具注册表，LLM可能生成不可执行的计划")
            
            # 构建完整prompt
            template = prompt_template or self.DEFAULT_PROMPT_TEMPLATE
            full_prompt = template.format(
                user_prompt=user_prompt,
                available_tools_description=tools_desc
            )
            
            # 调用LLM生成JSON
            start_time = time.time()
            plan_json = await self.model_client.call_model_with_json_response(
                prompt=full_prompt,
                **kwargs
            )
            generation_time = time.time() - start_time
            
            # 验证JSON格式
            PlanJSONValidator.validate(plan_json)
            PlanJSONValidator.validate_dependencies(plan_json)
            
            # 添加元数据
            plan_json = self._add_metadata(plan_json, user_prompt, generation_time)
            
            # 保存到文件
            if save_to_file:
                file_path = self._save_plan(plan_json)
                plan_json["file_path"] = str(file_path)
                self.logger.info(f"工作流已保存到: {file_path}")
            
            self.logger.info(f"工作流生成成功，包含 {len(plan_json['steps'])} 个步骤")
            self.logger.info(f"生成耗时: {generation_time:.2f}秒")
            
            # 记录性能指标
            self.logger_manager.log_performance_metrics(
                operation="plan_generation",
                duration=generation_time,
                additional_metrics={
                    "step_count": len(plan_json["steps"]),
                    "prompt_length": len(user_prompt),
                    "complexity": plan_json.get("complexity_level", "unknown")
                }
            )
            
            return plan_json
            
        except json.JSONDecodeError as e:
            error_msg = f"LLM返回的内容不是有效的JSON: {str(e)}"
            self.logger.error(error_msg)
            raise PlanGenerationError(error_msg) from e
        except Exception as e:
            error_msg = f"工作流生成失败: {str(e)}"
            self.logger.error(error_msg)
            raise PlanGenerationError(error_msg) from e
    
    def _add_metadata(self,
                     plan_json: Dict[str, Any],
                     user_prompt: str,
                     generation_time: float) -> Dict[str, Any]:
        """
        添加元数据到工作流JSON
        
        Args:
            plan_json: 工作流JSON
            user_prompt: 用户需求
            generation_time: 生成耗时
            
        Returns:
            添加元数据后的JSON
        """
        # 生成唯一ID
        timestamp = int(time.time())
        prompt_hash = hashlib.md5(user_prompt.encode('utf-8')).hexdigest()[:8]
        flow_id = f"flow_{timestamp}_{prompt_hash}"
        
        # 添加元数据
        plan_json.setdefault("flow_id", flow_id)
        plan_json.setdefault("original_query", user_prompt)
        plan_json.setdefault("query_hash", hashlib.md5(user_prompt.encode('utf-8')).hexdigest())
        plan_json.setdefault("created_at", datetime.now().isoformat())
        plan_json.setdefault("generation_time", generation_time)
        plan_json.setdefault("estimated_steps", len(plan_json.get("steps", [])))
        
        return plan_json
    
    def _save_plan(self, plan_json: Dict[str, Any]) -> Path:
        """
        保存工作流到文件
        
        Args:
            plan_json: 工作流JSON
            
        Returns:
            保存的文件路径
        """
        flow_id = plan_json.get("flow_id", f"flow_{int(time.time())}")
        
        # 使用storage_manager或直接保存
        if self.storage_manager:
            file_path = self.storage_manager.get_plan_file(flow_id)
            file_path = self.storage_manager.save_json(file_path, plan_json)
        else:
            file_path = self.plans_dir / f"{flow_id}.json"
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(plan_json, f, ensure_ascii=False, indent=2)
        
        return file_path
    
    def load_plan(self, flow_id: str) -> Dict[str, Any]:
        """
        从文件加载工作流
        
        Args:
            flow_id: 工作流ID
            
        Returns:
            工作流JSON对象
            
        Raises:
            PlanGenerationError: 加载失败
        """
        try:
            # 使用storage_manager或直接加载
            if self.storage_manager:
                file_path = self.storage_manager.get_plan_file(flow_id)
                plan_json = self.storage_manager.load_json(file_path)
                if plan_json is None:
                    raise PlanGenerationError(f"工作流文件不存在: {file_path}")
            else:
                file_path = self.plans_dir / f"{flow_id}.json"
                
                if not file_path.exists():
                    raise PlanGenerationError(f"工作流文件不存在: {file_path}")
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    plan_json = json.load(f)
            
            # 验证加载的JSON
            PlanJSONValidator.validate(plan_json)
            
            self.logger.info(f"工作流加载成功: {flow_id}")
            return plan_json
            
        except Exception as e:
            error_msg = f"工作流加载失败: {str(e)}"
            self.logger.error(error_msg)
            raise PlanGenerationError(error_msg) from e
    
    def load_plan_from_file(self, file_path: str) -> Dict[str, Any]:
        """
        从指定文件加载工作流
        
        Args:
            file_path: 文件路径
            
        Returns:
            工作流JSON对象
            
        Raises:
            PlanGenerationError: 加载失败
        """
        path = Path(file_path)
        
        if not path.exists():
            raise PlanGenerationError(f"工作流文件不存在: {file_path}")
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                plan_json = json.load(f)
            
            # 验证加载的JSON
            PlanJSONValidator.validate(plan_json)
            
            self.logger.info(f"工作流加载成功: {file_path}")
            return plan_json
            
        except Exception as e:
            error_msg = f"工作流加载失败: {str(e)}"
            self.logger.error(error_msg)
            raise PlanGenerationError(error_msg) from e


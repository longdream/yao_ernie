"""
LLM工具 - 通用LLM处理工具
"""
import sys
from pathlib import Path
import json
import re
import asyncio
from typing import Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from planscope.tools.base_tool import BaseTool


class GeneralLLMProcessorTool(BaseTool):
    """通用LLM处理工具"""
    
    TOOL_NAME = "general_llm_processor"
    TOOL_DESCRIPTION = """使用LLM处理和分析文本内容，支持总结、分类、回复生成等任务。

重要说明：
- 返回的content字段应该是处理后的最终结果（如：生成的回复文本、总结内容等），而不是原始输入内容
- 对于聊天回复任务：直接返回回复文本内容，不要添加任何前缀（如[我]:、[对方]:等）
- 输出内容应该干净、可直接使用，不包含任何格式标记"""
    TOOL_TYPE = "llm"
    
    INPUT_PARAMETERS = {
        "content": {
            "type": "str",
            "required": True,
            "description": "要处理的文本内容"
        },
        "prompt": {
            "type": "str",
            "required": True,
            "description": "处理任务描述，由ACE动态生成"
        },
        "temperature": {
            "type": "float",
            "required": False,
            "default": 0.7,
            "description": "模型温度参数"
        }
    }
    
    OUTPUT_JSON_SCHEMA = """{
  "content": "处理后的最终结果（字符串）。⚠️ 重要说明：
    - 续写任务：只返回新续写的内容（100-200字），不要包含原文
    - 回复生成任务：直接返回回复文本，如果不需要回复则返回空字符串
    - 总结任务：返回总结内容
    - 改写/扩写任务：返回完整的改写/扩写后的文本"
}"""
    
    def __init__(self, llm_model_client):
        """
        初始化工具
        
        Args:
            llm_model_client: LLM模型客户端（必需）
        """
        super().__init__()
        if llm_model_client is None:
            raise ValueError("llm_model_client参数是必需的")
        self.llm_model_client = llm_model_client
    
    def _execute_impl(self, content: str, prompt: str, temperature: float = 0.7, **kwargs) -> Dict[str, Any]:
        """
        使用LLM处理文本内容
        
        Args:
            content: 要处理的文本内容
            prompt: 处理任务描述（已由BaseTool拼接schema）
            temperature: 模型温度
            
        Returns:
            处理结果
        """
        print(f"[LLM工具] 开始处理内容，长度: {len(content)}")
        
        # ⭐ 聊天回复任务的硬性检查
        # 如果是聊天回复任务，检查最后一条消息是否是"右侧-我"
        if "[右侧-我]" in content or "[左侧-" in content:  # 判断是否是聊天内容
            lines = content.strip().split('\n')
            if lines:
                last_line = lines[-1].strip()
                # 检查最后一条消息是否是"右侧-我"发送的
                if last_line.startswith("[右侧-我]") or "[右侧-我]:" in last_line:
                    print("[LLM工具] ⚠️ 检测到最后一条消息是'右侧-我'发送的，无需回复，返回空字符串")
                    return {
                        "content": ""
                    }
        
        # 处理prompt中的占位符
        if "{{content}}" in prompt:
            final_prompt = prompt.replace("{{content}}", content)
        else:
            # 如果没有占位符，将内容附加到prompt末尾
            final_prompt = f"{prompt}\n\n待处理内容：\n{content}"
        
        print(f"[LLM工具] Prompt长度: {len(final_prompt)}")
        
        try:
            # 调用LLM（同步方式，由外层处理事件循环）
            import asyncio
            
            # 检查是否在事件循环中运行（线程池中不应有事件循环）
            # 注意：call_model()返回协程，需要使用asyncio.run()同步执行
            has_running_loop = False
            try:
                asyncio.get_running_loop()
                has_running_loop = True
            except RuntimeError:
                # 没有事件循环（正常情况：run_in_executor的线程池）
                has_running_loop = False
            
            if has_running_loop:
                raise RuntimeError(
                    "LLM工具在事件循环中被调用，但_execute_impl是同步函数。"
                    "请确保从非异步上下文调用此工具（已在FastAPI层用run_in_executor处理）。"
                )
            
            # 执行异步LLM调用
            llm_response = asyncio.run(
                self.llm_model_client.call_model(prompt=final_prompt, temperature=temperature)
            )
            
            print(f"[LLM工具] LLM返回长度: {len(llm_response)}")
            
            # 自动保存QA记录到Memory
            self._save_qa_record(final_prompt, llm_response, kwargs)
            
            # 解析JSON
            llm_data = self._parse_json(llm_response)
            
            # 统一输出格式
            output = {
                "content": llm_data.get("content", "")
            }
            
            print("[LLM工具] 处理成功")
            return output
            
        except Exception as e:
            print(f"[LLM工具] 错误: {e}")
            raise RuntimeError(f"LLM处理失败: {str(e)}") from e
    
    def _parse_json(self, text: str) -> dict:
        """解析JSON"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        try:
            cleaned_text = re.sub(r'```json\s*|\s*```', '', text, flags=re.MULTILINE)
            return json.loads(cleaned_text.strip())
        except json.JSONDecodeError:
            pass
        
        try:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        
        raise RuntimeError(f"无法解析JSON: {text[:500]}")
    
    def _save_qa_record(self, prompt: str, response: str, kwargs: Dict[str, Any]):
        """保存LLM调用记录到Memory"""
        try:
            # 检查是否是PLAN生成过程的调用，如果是则不记录
            context = kwargs.get("context", "")
            if context == "plan_generation":
                print("[QA记录] 跳过PLAN生成过程的调用")
                return
            
            import uuid
            import time
            from datetime import datetime
            from pathlib import Path
            
            qa_id = f"qa_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            
            # 生成prompt预览（前100字符）
            prompt_preview = prompt[:100] + "..." if len(prompt) > 100 else prompt
            
            # 获取模型名称：优先从kwargs，其次从llm_model_client对象
            model_name = kwargs.get("model_name", "unknown")
            if model_name == "unknown" and hasattr(self.llm_model_client, 'model_name'):
                model_name = self.llm_model_client.model_name
            
            record = {
                "qa_id": qa_id,
                "prompt": prompt,
                "prompt_preview": prompt_preview,
                "response": response,
                "model_type": "llm",  # LLM类型
                "model_used": model_name,
                "tool_name": "general_llm_processor",
                "flow_id": kwargs.get("flow_id", ""),
                "status": "unmarked",
                "created_at": datetime.now().isoformat()
            }
            
            qa_dir = Path("service/data/memories/qa_records")
            qa_dir.mkdir(parents=True, exist_ok=True)
            
            with open(qa_dir / f"{qa_id}.json", 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            
            print(f"[QA记录] 已保存: {qa_id} (LLM)")
            
        except Exception as e:
            # QA记录保存失败不应影响主流程
            print(f"[WARN] 保存QA记录失败: {e}")


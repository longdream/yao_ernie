"""
LLM聊天分析和回复生成工具
使用LLM分析聊天内容并生成合适的回复

必须通过AgentScope访问LLM（遵循项目规则3）
"""
import sys
from pathlib import Path
import json
import re
import asyncio

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from planscope.tools.base_tool import BaseTool


class AnalyzeAndReplyTool(BaseTool):
    """LLM聊天分析和回复生成工具"""
    
    TOOL_NAME = "analyze_and_reply"
    TOOL_DESCRIPTION = "使用LLM分析文本内容并生成响应"
    TOOL_TYPE = "llm"  # LLM类型工具，BaseTool会自动拼接prompt+schema
    
    INPUT_PARAMETERS = {
        "chat_content": {
            "type": "str",
            "required": True,
            "description": "聊天内容文本"
        },
        "prompt": {
            "type": "str",
            "required": True,
            "description": "分析任务的详细描述，由ACE动态生成"
        },
        "participants": {
            "type": "list",
            "required": False,
            "description": "参与者列表"
        },
        "context": {
            "type": "str",
            "required": False,
            "description": "对话背景"
        },
        "key_topics": {
            "type": "list",
            "required": False,
            "description": "关键话题列表"
        }
    }
    
    OUTPUT_JSON_SCHEMA = """{
  "content": "处理后的内容（字符串）"
}"""
    
    def __init__(self, llm_model_client):
        """
        初始化LLM工具
        
        Args:
            llm_model_client: LLM模型客户端（必需）
        """
        super().__init__()
        if llm_model_client is None:
            raise ValueError("llm_model_client参数是必需的")
        self.llm_model_client = llm_model_client
    
    def _execute_impl(self, chat_content: str, prompt: str, participants: list = None, 
                     context: str = None, key_topics: list = None, **kwargs) -> dict:
        """
        使用LLM分析文本内容并生成响应
        
        必须通过AgentScope访问LLM（遵循项目规则3）
        
        Args:
            chat_content: 输入文本内容（必需）
            prompt: 任务描述（由ACE动态生成，已由BaseTool拼接schema）
            participants: 参与者列表（可选）
            context: 上下文信息（可选）
            key_topics: 关键话题列表（可选）
            **kwargs: 其他参数
            
        Returns:
            dict: 统一输出格式
                - content: 处理后的内容
        
        Raises:
            ValueError: 参数缺失
            RuntimeError: LLM调用失败
        """
        print(f"[LLM工具] 开始处理内容...")
        
        # llm_model_client在__init__中已检查
        
        if prompt is None:
            raise ValueError("prompt参数是必需的，必须由ACE提供")
        
        # ⚠️ 注意：prompt已经由BaseTool自动拼接了OUTPUT_JSON_SCHEMA
        # 因为TOOL_TYPE="llm"，BaseTool.execute()会自动调用_build_final_prompt()
        print(f"[LLM工具] 使用拼接后的prompt（由BaseTool自动处理）")
        
        # 处理prompt中的工具内部占位符（如{{chat_content}}、{{context}}等）
        # 注意：{{steps.X.field}}格式的占位符已由VariableResolver处理
        import json as json_module
        replacements = {
            'chat_content': chat_content,
            'context': context if context else '',
            'participants': json_module.dumps(participants, ensure_ascii=False) if participants else '[]',
            'key_topics': json_module.dumps(key_topics, ensure_ascii=False) if key_topics else '[]'
        }
        
        # 先尝试替换占位符
        for key, value in replacements.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in prompt:
                # 将值转换为字符串（如果是list/dict，转为JSON字符串）
                if isinstance(value, (list, dict)):
                    value_str = json_module.dumps(value, ensure_ascii=False)
                else:
                    value_str = str(value) if value is not None else ''
                prompt = prompt.replace(placeholder, value_str)
        
        # 如果prompt中没有{{chat_content}}占位符，但有"以下"、"聊天内容"等关键词，
        # 说明prompt期望内容但没有占位符，需要手动添加
        if '{{chat_content}}' not in prompt and chat_content and ('以下' in prompt or '聊天内容' in prompt or '对话内容' in prompt):
            # 在prompt末尾添加实际的聊天内容
            prompt = f"{prompt}\n\n聊天内容：\n{chat_content}"
        
        print(f"[LLM工具] 最终Prompt长度: {len(prompt)}字符")
        print(f"[LLM工具] 输入的chat_content长度: {len(chat_content) if chat_content else 0}")
        print("[LLM工具] 调用LLM...")
        
        try:
            # 使用AgentScope的model_client调用LLM
            try:
                loop = asyncio.get_running_loop()
                raise RuntimeError(
                    "工具在事件循环中被调用，但analyze_and_reply是同步函数。"
                    "请确保从非异步上下文调用此工具。"
                )
            except RuntimeError as e:
                if "no running event loop" in str(e).lower():
                    llm_response = asyncio.run(self.llm_model_client.call_model(prompt=prompt))
                else:
                    raise
            
            print(f"[LLM工具] LLM返回内容长度: {len(llm_response)}")
            
            # 解析LLM返回的JSON
            llm_data = _parse_json(llm_response)
            
            print(f"[LLM工具] 处理成功")
            
            # 统一输出格式：使用"content"字段
            output = {
                "content": llm_data.get("content", "")
            }
            
            return output
            
        except Exception as e:
            print(f"[LLM工具] LLM调用失败: {e}")
            raise RuntimeError(f"LLM调用失败: {str(e)}")


def _parse_json(text: str) -> dict:
    """解析LLM返回的JSON"""
    try:
        result = json.loads(text)
        print("[LLM工具] JSON直接解析成功")
        return result
    except json.JSONDecodeError:
        pass
    
    try:
        cleaned_text = re.sub(r'```json\s*|\s*```', '', text, flags=re.MULTILINE)
        result = json.loads(cleaned_text.strip())
        print("[LLM工具] 去除markdown后解析成功")
        return result
    except json.JSONDecodeError:
        pass
    
    try:
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            print("[LLM工具] 提取JSON块后解析成功")
            return result
    except json.JSONDecodeError:
        pass
    
    print("[LLM工具] JSON解析失败")
    raise RuntimeError(f"LLM返回的内容无法解析为JSON格式。返回内容: {text[:500]}")


# 向后兼容：保留原有的函数接口
def analyze_and_reply(chat_content: str, prompt: str, participants: list = None, 
                     context: str = None, key_topics: list = None, 
                     model_client=None, **kwargs) -> dict:
    """
    LLM工具的函数接口（向后兼容）
    
    注意：推荐使用AnalyzeAndReplyTool类，函数接口保留用于向后兼容
    """
    tool = AnalyzeAndReplyTool(llm_model_client=model_client)
    return tool.execute(
        chat_content=chat_content,
        prompt=prompt,
        participants=participants,
        context=context,
        key_topics=key_topics,
        **kwargs
    )


# 导出常量（向后兼容）
LLM_TOOL_DESCRIPTION = AnalyzeAndReplyTool.TOOL_DESCRIPTION
LLM_INPUT_PARAMETERS = AnalyzeAndReplyTool.INPUT_PARAMETERS
LLM_OUTPUT_JSON_SCHEMA = AnalyzeAndReplyTool.OUTPUT_JSON_SCHEMA


if __name__ == "__main__":
    # 测试工具
    print("LLM工具元数据:")
    metadata = AnalyzeAndReplyTool.get_metadata()
    print(json.dumps(metadata, ensure_ascii=False, indent=2))

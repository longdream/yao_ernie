"""
通用LLM处理工具
支持灵活的多参数输入（最多3个参数），参数可以是长文本
Plan生成prompt时使用占位符（{{param1}}, {{param2}}, {{param3}}），工具内部自动替换

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


class GeneralLLMProcessorTool(BaseTool):
    """
    通用LLM处理工具
    
    特点：
    - 支持最多3个参数输入（param1, param2, param3）
    - 参数可以是长文本
    - Plan中使用{{param1}}等占位符，工具自动替换
    - 继承BaseTool，TOOL_TYPE="llm"，自动拼接schema
    - 统一输出格式：{"content": "..."}
    """
    
    TOOL_NAME = "general_llm_processor"
    TOOL_DESCRIPTION = "通用LLM文本处理工具，可接收最多3个参数进行灵活处理"
    TOOL_TYPE = "llm"  # LLM类型，BaseTool会自动拼接OUTPUT_JSON_SCHEMA
    
    INPUT_PARAMETERS = {
        "prompt": {
            "type": "str",
            "required": True,
            "description": "处理任务描述，由ACE动态生成，可使用{{param1}}, {{param2}}, {{param3}}占位符"
        },
        "param1": {
            "type": "str",
            "required": False,
            "description": "第一个参数（可以是长文本）"
        },
        "param2": {
            "type": "str",
            "required": False,
            "description": "第二个参数（可以是长文本）"
        },
        "param3": {
            "type": "str",
            "required": False,
            "description": "第三个参数（可以是长文本）"
        }
    }
    
    OUTPUT_JSON_SCHEMA = """{
  "content": "处理后的内容（字符串）"
}"""
    
    def __init__(self, llm_model_client):
        """
        初始化通用LLM工具
        
        Args:
            llm_model_client: LLM模型客户端（必需）
        """
        super().__init__()
        if llm_model_client is None:
            raise ValueError("llm_model_client参数是必需的")
        self.llm_model_client = llm_model_client
    
    def _execute_impl(self, prompt: str, param1: str = None, param2: str = None, 
                     param3: str = None, **kwargs) -> dict:
        """
        执行通用LLM处理
        
        Args:
            prompt: 任务描述（由ACE生成，已由BaseTool拼接schema）
            param1: 第一个参数（可选）
            param2: 第二个参数（可选）
            param3: 第三个参数（可选）
            **kwargs: 其他参数
            
        Returns:
            dict: {"content": "处理结果"}
        """
        print(f"[通用LLM工具] 开始处理...")
        
        # ⚠️ 注意：prompt已经由BaseTool自动拼接了OUTPUT_JSON_SCHEMA
        # 因为TOOL_TYPE="llm"，BaseTool.execute()会自动调用_build_final_prompt()
        
        if prompt is None:
            raise ValueError("prompt参数是必需的，必须由ACE提供")
        
        # 1. 替换占位符
        replacements = {
            'param1': param1 or '',
            'param2': param2 or '',
            'param3': param3 or ''
        }
        
        for key, value in replacements.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in prompt:
                print(f"[通用LLM工具] 替换占位符 {placeholder}")
                prompt = prompt.replace(placeholder, str(value))
        
        print(f"[通用LLM工具] 最终Prompt长度: {len(prompt)}字符")
        
        # 显示参数信息
        param_info = []
        if param1:
            param_info.append(f"param1长度: {len(param1)}")
        if param2:
            param_info.append(f"param2长度: {len(param2)}")
        if param3:
            param_info.append(f"param3长度: {len(param3)}")
        if param_info:
            print(f"[通用LLM工具] 参数: {', '.join(param_info)}")
        
        print("[通用LLM工具] 调用LLM...")
        
        try:
            # 使用AgentScope的model_client调用LLM
            try:
                loop = asyncio.get_running_loop()
                raise RuntimeError(
                    "工具在事件循环中被调用，但general_llm_processor是同步函数。"
                    "请确保从非异步上下文调用此工具。"
                )
            except RuntimeError as e:
                if "no running event loop" in str(e).lower():
                    llm_response = asyncio.run(self.llm_model_client.call_model(prompt=prompt))
                else:
                    raise
            
            print(f"[通用LLM工具] LLM返回内容长度: {len(llm_response)}")
            print(f"[通用LLM工具] LLM返回内容: {llm_response}")
            # 解析LLM返回的JSON
            llm_data = _parse_json(llm_response)
            
            # 统一输出格式：智能处理各种返回格式
            if isinstance(llm_data, dict) and "content" in llm_data:
                # 标准格式：{"content": "..."}
                content = llm_data["content"]
                print(f"[通用LLM工具] 使用标准content字段")
            elif isinstance(llm_data, str):
                # 纯文本
                content = llm_data
                print(f"[通用LLM工具] 直接使用字符串")
            else:
                # 其他格式（复杂对象、列表等）：转换为JSON字符串
                import json as json_module
                content = json_module.dumps(llm_data, ensure_ascii=False, indent=2)
                print(f"[通用LLM工具] 将{type(llm_data)}转换为JSON字符串")
            
            print(f"[通用LLM工具] 最终content长度: {len(content) if content else 0}")
            print(f"[通用LLM工具] 处理成功")
            
            output = {
                "content": content
            }
            
            return output
            
        except Exception as e:
            print(f"[通用LLM工具] LLM调用失败: {e}")
            raise RuntimeError(f"LLM调用失败: {str(e)}")


def _parse_json(text: str) -> dict:
    """解析LLM返回的JSON"""
    try:
        result = json.loads(text)
        print("[通用LLM工具] JSON直接解析成功")
        return result
    except json.JSONDecodeError:
        pass
    
    try:
        cleaned_text = re.sub(r'```json\s*|\s*```', '', text, flags=re.MULTILINE)
        result = json.loads(cleaned_text.strip())
        print("[通用LLM工具] 去除markdown后解析成功")
        return result
    except json.JSONDecodeError:
        pass
    
    try:
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            print("[通用LLM工具] 提取JSON块后解析成功")
            return result
    except json.JSONDecodeError:
        pass
    
    print("[通用LLM工具] JSON解析失败")
    raise RuntimeError(f"LLM返回的内容无法解析为JSON格式。返回内容: {text[:500]}")


# 向后兼容：保留函数接口（虽然推荐使用类）
def general_llm_processor(prompt: str, param1: str = None, param2: str = None, 
                         param3: str = None, llm_model_client=None, **kwargs) -> dict:
    """
    通用LLM处理工具的函数接口（向后兼容）
    
    注意：推荐使用GeneralLLMProcessorTool类
    """
    tool = GeneralLLMProcessorTool(llm_model_client=llm_model_client)
    return tool.execute(
        prompt=prompt,
        param1=param1,
        param2=param2,
        param3=param3,
        **kwargs
    )


if __name__ == "__main__":
    # 测试工具
    print("通用LLM工具元数据:")
    metadata = GeneralLLMProcessorTool.get_metadata()
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


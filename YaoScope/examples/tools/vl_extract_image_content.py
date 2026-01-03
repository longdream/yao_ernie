"""
VL模型图片内容提取工具
使用ERNIE-4.5-Turbo-VL从图片中提取内容

⚠️ VL（视觉语言模型）vs OCR的区别：
- VL：AI的"眼睛"，能理解图片内容、场景、布局，识别文字，但精度一般
- OCR：专业文字提取工具，精确识别文字位置和内容，但不理解语义

必须通过AgentScope访问VL模型（遵循项目规则3）
"""
import sys
from pathlib import Path
import base64
import json
import re
import asyncio

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from planscope.tools.base_tool import BaseTool

try:
    from json_repair import repair_json
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False
    print("[VL工具] 警告: json_repair未安装，JSON修复功能不可用")


class VLExtractTool(BaseTool):
    """VL模型图片内容提取工具"""
    
    TOOL_NAME = "vl_extract_image_content"
    TOOL_DESCRIPTION = "使用视觉语言模型理解和分析图片内容"
    TOOL_TYPE = "vl"  # VL类型工具，BaseTool会自动拼接prompt+schema
    
    INPUT_PARAMETERS = {
        "image_path": {
            "type": "str",
            "required": True,
            "description": "图片路径，支持png/jpg格式"
        },
        "prompt": {
            "type": "str",
            "required": True,
            "description": "提取任务的详细描述，由ACE动态生成"
        },
        "temperature": {
            "type": "float",
            "required": False,
            "default": 0.3,
            "description": "模型温度参数，控制输出随机性"
        }
    }
    
    OUTPUT_JSON_SCHEMA = """{
  "content": "提取的主要内容（字符串）"
}"""
    
    def __init__(self, vl_model_client):
        """
        初始化VL工具
        
        Args:
            vl_model_client: VL模型客户端（必需）
        """
        super().__init__()
        if vl_model_client is None:
            raise ValueError("vl_model_client参数是必需的")
        self.vl_model_client = vl_model_client
    
    def _execute_impl(self, image_path: str, prompt: str, temperature: float = 0.3, **kwargs) -> dict:
        """
        使用视觉语言模型理解和分析图片内容
        
        ⚠️ VL（视觉语言模型）vs OCR的区别：
        - VL：AI的"眼睛"，能理解图片内容、场景、布局，识别文字，但精度一般
        - OCR：专业文字提取工具，精确识别文字位置和内容，但不理解语义
        
        必须通过AgentScope访问VL模型（遵循项目规则3）
        
        Args:
            image_path: 图片路径（支持png/jpg格式）
            prompt: 分析任务描述（由ACE动态生成，已由BaseTool拼接schema）
            temperature: 模型温度参数（默认0.3）
            **kwargs: 其他参数
            
        Returns:
            dict: 统一输出格式
                - content: 分析结果内容
        
        Raises:
            FileNotFoundError: 图片文件不存在
            RuntimeError: VL模型调用失败
        """
        print(f"[VL工具] 开始提取图片内容: {image_path}")
        
        # vl_model_client在__init__中已检查，这里直接使用
        
        # 读取图片并转为base64
        image_file = Path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        
        with open(image_file, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        # prompt参数是必需的，必须由ACE提供
        if prompt is None:
            raise ValueError("prompt参数是必需的，必须由ACE提供")
        
        # ⚠️ 注意：prompt已经由BaseTool自动拼接了OUTPUT_JSON_SCHEMA
        # 因为TOOL_TYPE="vl"，BaseTool.execute()会自动调用_build_final_prompt()
        print(f"[VL工具] 使用拼接后的prompt（由BaseTool自动处理）")
        
        try:
            print(f"[VL工具] Prompt预览: {prompt[:150]}...")
        except UnicodeEncodeError:
            print(f"[VL工具] Prompt长度: {len(prompt)}字符")
        
        print("[VL工具] 调用VL模型...")
        
        try:
            # 使用vl_model_client的底层OpenAI client调用VL模型
            # vl_model_client是AgentScopeModelClient，其model_wrapper是OpenAIChatModel
            # OpenAIChatModel有client属性可以访问底层OpenAI客户端
            # 注意：client.chat.completions.create()返回协程，需要使用asyncio.run()同步执行
            try:
                loop = asyncio.get_running_loop()
                raise RuntimeError(
                    "VL工具在事件循环中被调用，但vl_extract_image_content是同步函数。"
                    "请确保从非异步上下文调用此工具。"
                )
            except RuntimeError as e:
                if "no running event loop" in str(e).lower():
                    # 没有运行中的事件循环，可以安全使用asyncio.run()
                    response = asyncio.run(
                        self.vl_model_client.model_wrapper.client.chat.completions.create(
                            model="ernie-4.5-turbo-vl",
                            messages=[{
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{image_data}"
                                        }
                                    },
                                    {
                                        "type": "text",
                                        "text": prompt  # 使用BaseTool已拼接的prompt
                                    }
                                ]
                            }],
                            temperature=temperature
                        )
                    )
                else:
                    raise
            
            result_text = response.choices[0].message.content
            print(f"[VL工具] VL模型返回内容长度: {len(result_text)}")
            
            # 解析JSON
            vl_data = _parse_json(result_text)
            
            print(f"[VL工具] VL返回数据类型: {type(vl_data)}")
            
            # 统一输出格式：智能处理各种返回格式
            if isinstance(vl_data, dict) and "content" in vl_data:
                # 标准格式：{"content": "..."}
                content = vl_data["content"]
                print(f"[VL工具] 使用标准content字段")
            elif isinstance(vl_data, str):
                # 纯文本
                content = vl_data
                print(f"[VL工具] 直接使用字符串")
            else:
                # 其他格式（列表、复杂对象等）：转换为JSON字符串
                import json as json_module
                content = json_module.dumps(vl_data, ensure_ascii=False, indent=2)
                print(f"[VL工具] 将{type(vl_data)}转换为JSON字符串")
            
            print(f"[VL工具] 最终content长度: {len(content) if content else 0}")
            # 避免编码问题，只输出长度
            print(f"[VL工具] 提取成功")
            
            output = {
                "content": content
            }
            
            return output
            
        except Exception as e:
            # 直接抛出异常，避免编码问题
            raise RuntimeError(f"VL模型调用失败") from e


def _parse_json(text: str) -> dict:
    """
    解析VL模型返回的JSON（支持多种格式）
    """
    # 方式1：直接解析
    try:
        result = json.loads(text)
        print("[VL工具] 直接解析JSON成功")
        return result
    except json.JSONDecodeError:
        pass
    
    # 方式2：去除markdown代码块
    try:
        cleaned_text = re.sub(r'```json\s*|\s*```', '', text, flags=re.MULTILINE)
        result = json.loads(cleaned_text.strip())
        print("[VL工具] 去除markdown后解析成功")
        return result
    except json.JSONDecodeError:
        pass
    
    # 方式3：提取JSON块
    try:
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            result = json.loads(json_str)
            print("[VL工具] 提取JSON块后解析成功")
            return result
    except json.JSONDecodeError:
        pass
    
    # 方式4：使用json_repair
    if HAS_JSON_REPAIR:
        try:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                repaired = repair_json(json_str)
                # repair_json可能返回字符串，需要再次解析
                if isinstance(repaired, str):
                    result = json.loads(repaired)
                else:
                    result = repaired
                print("[VL工具] JSON修复后解析成功")
                return result
        except Exception as e:
            print(f"[VL工具] JSON修复失败: {e}")
    
    # 所有解析方式都失败，抛出异常
    print("[VL工具] 所有JSON解析方式失败")
    # 使用repr避免编码问题
    text_preview = text[:500]
    try:
        error_msg = f"VL模型返回的内容无法解析为JSON格式。返回内容: {text_preview}"
    except UnicodeEncodeError:
        error_msg = f"VL模型返回的内容无法解析为JSON格式。返回内容: {repr(text_preview)}"
    raise RuntimeError(error_msg)


# 向后兼容：保留原有的函数接口
def vl_extract_image_content(image_path: str, prompt: str, vl_model_client=None, temperature: float = 0.3, **kwargs) -> dict:
    """
    VL工具的函数接口（向后兼容）
    
    注意：推荐使用VLExtractTool类，函数接口保留用于向后兼容
    """
    tool = VLExtractTool(vl_model_client=vl_model_client)
    return tool.execute(image_path=image_path, prompt=prompt, temperature=temperature, **kwargs)


# 导出常量（向后兼容）
VL_TOOL_DESCRIPTION = VLExtractTool.TOOL_DESCRIPTION
VL_INPUT_PARAMETERS = VLExtractTool.INPUT_PARAMETERS
VL_OUTPUT_JSON_SCHEMA = VLExtractTool.OUTPUT_JSON_SCHEMA


if __name__ == "__main__":
    # 测试工具
    print("VL工具元数据:")
    metadata = VLExtractTool.get_metadata()
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


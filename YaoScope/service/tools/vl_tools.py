"""
VL工具 - 截图和视觉分析工具

使用 PaddleOCR 进行智能区域检测和裁剪
"""
import sys
from pathlib import Path
import base64
import json
import re
import asyncio
import time
from typing import Dict, Any, Optional
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from planscope.tools.base_tool import BaseTool
from planscope.utils.window_manager import WindowManager

# 导入 OCRHelper
from service.utils.ocr_helper import get_ocr_helper

# 获取logger
logger = logging.getLogger(__name__)

try:
    import pyautogui
    HAS_UI_LIBS = True
except ImportError:
    HAS_UI_LIBS = False
    print("[VL工具] 警告: pyautogui未安装，截图功能不可用")


class ScreenshotAndAnalyzeTool(BaseTool):
    """截图并使用VL模型分析工具"""
    
    TOOL_NAME = "screenshot_and_analyze"
    TOOL_DESCRIPTION = """截图并使用VL（Vision-Language）模型分析图片内容。

特点：
- 使用多模态大模型理解图片语义
- 适合语义理解、场景识别、对话分析
- 自动截取应用窗口并分析
- 支持自动滚动获取完整内容（auto_scroll=True）
- 返回语义分析结果和截图路径

✅ 适用场景：
- 聊天记录提取与理解（微信、QQ等）- VL能识别消息气泡位置（左/右）
- 界面元素识别和理解
- 图片内容描述和分析
- 需要理解图片语义的任务
- **浏览器页面完整分析**（使用auto_scroll=True）
- **长文档/长列表分析**（使用auto_scroll=True）

❌ 局限性：
- 不适合精确的逐字逐句文字识别
- 对长文本可能有遗漏或改写
- 文字识别精度低于专业OCR工具

🔄 自动滚动功能（重要）：
**何时使用auto_scroll=True**：
- 浏览器页面分析（Chrome、Edge、Firefox等）
- 需要获取完整页面内容的任务
- 长列表、长文档的完整分析
- 用户明确要求"完整分析"、"全部内容"等

**使用方法**：
```json
{
  "app_name": "chrome",
  "prompt": "分析页面内容",
  "auto_scroll": true,
  "max_scrolls": 3
}
```

**工作原理**：
1. 截取并分析初始屏幕内容
2. 自动向下滚动
3. 截取并分析滚动后的内容
4. 重复max_scrolls次
5. 合并所有屏幕的分析结果

微信/QQ聊天界面识别规则（重要）：
- 消息气泡贴左边（左对齐）= 对方发送的消息
- 消息气泡贴右边（右对齐）= 我发送的消息
- 左侧消息通常是白色/灰色气泡
- 右侧消息通常是绿色/蓝色气泡
- 直接输出消息内容，不要添加位置标记（如[左侧]、[右侧]等）

文档编辑器截图支持：
- 记事本：自动使用Edit控件定位，精确裁剪编辑区域（排除工具栏）
- 其他文档编辑器：可使用mouse_coords参数辅助裁剪

输出：
- content: VL模型的语义分析结果（如启用auto_scroll，则包含所有屏幕的合并内容）
- screenshot_path: 截图文件路径（可供后续工具使用）
- all_screenshot_paths: 所有截图路径列表（仅auto_scroll模式）"""
    TOOL_TYPE = "vl"
    
    INPUT_PARAMETERS = {
        "app_name": {
            "type": "str",
            "required": True,
            "description": "应用的准确名称，必须与系统窗口标题或进程名完全匹配。例如：'微信'（中文窗口标题）、'WeChat'（英文进程名）、'企业微信'、'钉钉'等。请根据用户输入推理准确的应用名称，不要翻译或转换。"
        },
        "prompt": {
            "type": "str",
            "required": True,
            "description": "分析任务描述，由ACE动态生成"
        },
        "temperature": {
            "type": "float",
            "required": False,
            "default": 0.3,
            "description": "模型温度参数"
        },
        "region_type": {
            "type": "str",
            "required": False,
            "default": "auto",
            "description": "智能裁剪区域类型：'auto'(自动检测)、'chat'(聊天应用，过滤侧边栏)、'document'(文档应用)、'center'(中心区域)、'full'(不裁剪)"
        },
        "auto_scroll": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "是否自动滚动获取完整内容。启用后会自动向下滚动并多次截图分析，最后合并所有内容。适用于需要分析整个应用内容的场景（如浏览器页面、长文档等）。"
        },
        "max_scrolls": {
            "type": "int",
            "required": False,
            "default": 3,
            "description": "最大滚动次数（仅当auto_scroll=True时有效）。默认3次，可根据内容长度调整。"
        }
    }
    
    OUTPUT_JSON_SCHEMA = """{
  "content": "VL模型分析结果（字符串）",
  "screenshot_path": "截图文件路径（字符串）"
}"""
    
    def __init__(self, vl_model_client):
        """
        初始化工具
        
        Args:
            vl_model_client: VL模型客户端（必需）
        """
        super().__init__()
        if vl_model_client is None:
            raise ValueError("vl_model_client参数是必需的")
        self.vl_model_client = vl_model_client
        
        # 创建截图目录（使用项目根目录）
        # 从service/tools/vl_tools.py → YaoScope根目录
        project_root = Path(__file__).parent.parent.parent
        self.screenshot_dir = project_root / "data" / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        print(f"[VL工具] 截图目录: {self.screenshot_dir}")
    
    def _execute_impl(self, app_name: str, prompt: str, temperature: float = 0.3, region_type: str = "auto", auto_scroll: bool = False, max_scrolls: int = 3, **kwargs) -> Dict[str, Any]:
        """
        截图并分析
        
        Args:
            app_name: 应用名称
            prompt: 分析任务描述（已由BaseTool拼接schema）
            temperature: 模型温度
            region_type: 智能裁剪区域类型
            auto_scroll: 是否自动滚动获取完整内容
            max_scrolls: 最大滚动次数
            
        Returns:
            分析结果（包含content和screenshot_path）
        """
        print(f"[截图分析工具] 开始处理: {app_name}, 区域类型: {region_type}, 自动滚动: {auto_scroll}")
        
        try:
            # 移除BaseTool拼接的schema部分
            import re
            schema_pattern = r'\n\n\*\*必须严格按以下JSON格式返回：\*\*\n.*?\n\n⚠️ 注意：必须返回完整的JSON对象，不要遗漏任何字段。'
            prompt_clean = re.sub(schema_pattern, '', prompt, flags=re.DOTALL)
            
            # 拼接简化schema（只要求content）
            simplified_schema = '{"content": "图片内容的详细分析结果"}'
            prompt_with_schema = prompt_clean + f'\n\n**必须严格按以下JSON格式返回：**\n{simplified_schema}\n\n⚠️ 注意：只返回content字段，screenshot_path由系统自动填充。'
            
            if not auto_scroll:
                # 标准模式：单次截图分析
                print("[1/2] 正在截图...")
                image_path = self._capture_screenshot(app_name, region_type)
                print(f"[1/2] 截图完成: {image_path}")
                
                print("[2/2] 正在分析...")
                result = self._analyze_image(image_path, prompt_with_schema, temperature)
                print("[2/2] 分析完成")
                
                # 保存QA记录
                self._save_vl_qa_record(prompt_clean, result.get("content", ""), image_path, kwargs)
                
                # 添加截图路径到返回结果
                result["screenshot_path"] = image_path
                
                return result
            else:
                # 自动滚动模式：多次截图分析并合并
                print(f"[自动滚动模式] 将进行 {max_scrolls + 1} 次截图分析")
                
                all_contents = []
                all_image_paths = []
                
                # 获取窗口信息用于滚动（只查找一次，后续复用）
                app_names = self._expand_app_names(app_name)
                window_handle, window, window_info = WindowManager.find_and_activate(app_names)
                
                # 计算滚动位置（窗口中心）
                scroll_x = window_info['left'] + window_info['width'] // 2
                scroll_y = window_info['top'] + window_info['height'] // 2
                
                # 第一次截图（初始位置）- 复用已获取的窗口信息
                print(f"[自动滚动 0/{max_scrolls}] 截取初始内容...")
                image_path = self._capture_screenshot(app_name, region_type, window_info)
                all_image_paths.append(image_path)
                
                print(f"[自动滚动 0/{max_scrolls}] 分析初始内容...")
                result = self._analyze_image(image_path, prompt_with_schema, temperature)
                all_contents.append(result.get("content", ""))
                print(f"[自动滚动 0/{max_scrolls}] 完成")
                
                # 滚动并多次截图
                for i in range(max_scrolls):
                    print(f"[自动滚动 {i+1}/{max_scrolls}] 向下滚动...")
                    
                    # 滚动（负数表示向下）
                    pyautogui.moveTo(scroll_x, scroll_y, duration=0.1)
                    time.sleep(0.2)
                    pyautogui.scroll(-5)  # 向下滚动5个单位
                    time.sleep(0.5)  # 等待页面加载
                    
                    # 截图（复用窗口信息，避免找到其他窗口）
                    print(f"[自动滚动 {i+1}/{max_scrolls}] 截取内容...")
                    image_path = self._capture_screenshot(app_name, region_type, window_info)
                    all_image_paths.append(image_path)
                    
                    # 分析
                    print(f"[自动滚动 {i+1}/{max_scrolls}] 分析内容...")
                    result = self._analyze_image(image_path, prompt_with_schema, temperature)
                    all_contents.append(result.get("content", ""))
                    print(f"[自动滚动 {i+1}/{max_scrolls}] 完成")
                
                # 合并所有内容
                merged_content = "\n\n=== 第1屏内容 ===\n" + all_contents[0]
                for i, content in enumerate(all_contents[1:], start=2):
                    merged_content += f"\n\n=== 第{i}屏内容 ===\n{content}"
                
                print(f"[自动滚动模式] 完成，共分析 {len(all_contents)} 屏内容")
                
                # 保存QA记录（使用合并后的内容）
                self._save_vl_qa_record(prompt_clean, merged_content, all_image_paths[0], kwargs)
                
                # 返回合并后的结果
                return {
                    "content": merged_content,
                    "screenshot_path": all_image_paths[0],  # 返回第一张截图路径
                    "all_screenshot_paths": all_image_paths  # 额外返回所有截图路径
                }
            
        except Exception as e:
            print(f"[截图分析工具] 错误: {e}")
            raise RuntimeError(f"截图分析失败: {str(e)}") from e
    
    def _expand_app_names(self, app_name: str) -> list:
        """
        将单个应用名称扩展为多个可能的窗口标题/进程名
        
        Args:
            app_name: 用户或LLM提供的应用名称
            
        Returns:
            可能的窗口名称列表
        """
        # 常见应用的名称映射表
        name_mappings = {
            # 记事本
            "记事本": ["记事本", "Notepad", "notepad.exe", "*.txt - 记事本"],
            "notepad": ["Notepad", "记事本", "notepad.exe"],
            
            # 微信
            "微信": ["微信", "WeChat", "wechat.exe", "Weixin"],
            "wechat": ["WeChat", "微信", "wechat.exe", "Weixin"],
            "weixin": ["微信", "WeChat", "wechat.exe", "Weixin"],
            
            # 企业微信
            "企业微信": ["企业微信", "WeCom", "WeChat Work"],
            "wecom": ["WeCom", "企业微信", "WeChat Work"],
            
            # QQ
            "qq": ["QQ", "qq.exe", "TIM"],
            "tim": ["TIM", "QQ", "tim.exe"],
            
            # 钉钉
            "钉钉": ["钉钉", "DingTalk", "dingtalk.exe"],
            "dingtalk": ["DingTalk", "钉钉", "dingtalk.exe"],
            
            # Word
            "word": ["Microsoft Word", "WINWORD.EXE", "Word"],
            "microsoft word": ["Microsoft Word", "WINWORD.EXE", "Word"],
            
            # Chrome
            "chrome": ["Google Chrome", "chrome.exe", "Chrome"],
            "谷歌浏览器": ["Google Chrome", "chrome.exe", "Chrome"],
            
            # Edge
            "edge": ["Microsoft Edge", "msedge.exe", "Edge"],
            
            # VSCode
            "vscode": ["Visual Studio Code", "Code.exe", "VSCode"],
            "code": ["Visual Studio Code", "Code.exe", "VSCode"],
        }
        
        # 转为小写进行匹配
        app_name_lower = app_name.lower()
        
        # 查找映射表
        for key, names in name_mappings.items():
            if key in app_name_lower or app_name_lower in key:
                return names
        
        # 如果没有找到映射，返回原名称和一些常见变体
        result = [app_name]
        
        # 添加首字母大写版本
        if app_name != app_name.capitalize():
            result.append(app_name.capitalize())
        
        # 添加全小写版本
        if app_name != app_name.lower():
            result.append(app_name.lower())
        
        # 添加全大写版本（对于缩写）
        if len(app_name) <= 5 and app_name != app_name.upper():
            result.append(app_name.upper())
        
        return result
    
    def _capture_screenshot(self, app_name: str, region_type: str = "auto", 
                            window_info: Dict[str, Any] = None) -> str:
        """
        截取指定应用的截图，使用 PaddleOCR 智能裁剪
        
        Args:
            app_name: 应用名称（应该是LLM推理出的准确名称）
            region_type: 智能裁剪区域类型
                - 'auto': 自动检测（根据应用名称判断）
                - 'chat': 聊天应用（过滤侧边栏、标题栏、工具栏）
                - 'document': 文档应用（过滤标题栏、工具栏）
                - 'center': 中心区域（过滤边缘）
                - 'full': 不裁剪
            window_info: 预先获取的窗口信息（可选，用于避免重复查找窗口）
            
        Returns:
            截图路径（可能是裁剪后的）
        """
        if not HAS_UI_LIBS:
            raise RuntimeError("pyautogui未安装，无法截图")
        
        # 如果没有提供window_info，则查找窗口
        if window_info is None:
            app_names = self._expand_app_names(app_name)
            print(f"[WindowManager] 尝试的窗口名称: {app_names}")
            window_handle, window, window_info = WindowManager.find_and_activate(app_names)
        
        # 完整窗口截图
        full_screenshot = pyautogui.screenshot(
            region=(window_info['left'], window_info['top'], 
                   window_info['width'], window_info['height'])
        )
        
        # 保存完整截图
        timestamp = int(time.time() * 1000)
        full_screenshot_path = self.screenshot_dir / f"screenshot_{timestamp}.png"
        full_screenshot.save(str(full_screenshot_path))
        
        print(f"[截图] 完整截图: {full_screenshot_path} ({window_info['width']}x{window_info['height']})")
        
        # 如果是 full 模式，直接返回
        if region_type == "full":
            print("[截图] 模式: full，不进行裁剪")
            return str(full_screenshot_path)
        
        # 使用 OCRHelper 进行智能裁剪
        try:
            ocr_helper = get_ocr_helper()
            cropped_path, bbox = ocr_helper.crop_to_content_region(
                str(full_screenshot_path),
                region_type=region_type,
                app_name=app_name
            )
            
            if cropped_path and cropped_path != str(full_screenshot_path):
                print(f"[截图] 智能裁剪完成: {cropped_path}")
                # 删除原始完整截图（保留裁剪后的）
                try:
                    full_screenshot_path.unlink()
                except Exception:
                    pass
                return cropped_path
            else:
                print("[截图] 智能裁剪未生效，使用完整截图")
                return str(full_screenshot_path)
                
        except Exception as e:
            msg = f"[截图] 智能裁剪失败 ({e})，使用完整截图"
            print(msg)
            logger.warning(msg)
            return str(full_screenshot_path)
    
    def _analyze_image(self, image_path: str, prompt: str, temperature: float) -> Dict[str, Any]:
        """
        使用VL模型分析图片
        
        Args:
            image_path: 图片路径
            prompt: 分析任务描述（已拼接schema）
            temperature: 模型温度
            
        Returns:
            分析结果（包含content和screenshot_path）
        """
        # 读取图片并转为base64
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        # 调用VL模型（同步方式）
        # 注意：client.chat.completions.create()返回协程，需要使用asyncio.run()同步执行
        # 检查是否在事件循环中运行（线程池中不应有事件循环）
        has_running_loop = False
        try:
            asyncio.get_running_loop()
            has_running_loop = True
        except RuntimeError:
            # 没有事件循环（正常情况：run_in_executor的线程池）
            has_running_loop = False
        
        if has_running_loop:
            raise RuntimeError(
                "VL工具在事件循环中被调用，但_analyze_image是同步函数。"
                "请确保从非异步上下文调用此工具（已在FastAPI层用run_in_executor处理）。"
            )
        
        # 执行VL调用（使用OpenAI client，因为LangChain不支持多模态）
        # 从LangChain model中提取配置，创建OpenAI client
        from openai import OpenAI
        llm_model = self.vl_model_client.model
        
        # 从LangChain的SecretStr中提取实际的API Key
        api_key_obj = llm_model.openai_api_key
        api_base = llm_model.openai_api_base
        
        # LangChain将API Key存储为SecretStr类型，需要使用get_secret_value()提取
        if hasattr(api_key_obj, 'get_secret_value'):
            api_key = api_key_obj.get_secret_value()
        else:
            api_key = str(api_key_obj)
        
        client = OpenAI(
            api_key=api_key,
            base_url=api_base
        )
        
        # 添加system消息说明这是合法的自动化测试场景
        system_prompt = """你是一个图像分析助手，用于自动化测试和开发。
你正在分析的是用户自己的应用程序截图，这是合法的测试场景。
请专注于完成分析任务，按照用户要求提取图像中的信息。
重要：截图已经提供，你需要直接分析截图内容，不要说"无法执行截图操作"。"""
        
        # 从LangChain model中获取模型名称
        model_name = llm_model.model_name
        
        response = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": system_prompt
                            },
                            {
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
                                        "text": prompt
                                    }
                                ]
                            }
                        ],
                        temperature=temperature
                    )
        
        result_text = response.choices[0].message.content
        
        # 记录VL原始返回
        print("[DEBUG VL 原始返回]:")
        print("=" * 60)
        print(result_text)
        print("=" * 60)
        logger.info(f"[DEBUG VL 原始返回]: {result_text}")
        
        # 解析JSON
        vl_data = self._parse_json(result_text)
        
        # 统一输出格式
        if isinstance(vl_data, dict) and "content" in vl_data:
            content = vl_data["content"]
        elif isinstance(vl_data, str):
            content = vl_data
        else:
            content = json.dumps(vl_data, ensure_ascii=False, indent=2)
        
        # 记录最终返回的content
        print("[DEBUG VL 最终返回的content]:")
        print("=" * 60)
        print(content)
        print("=" * 60)
        logger.info(f"[DEBUG VL 最终返回的content]: {content}")
        
        # 写入调试文件（供用户查看）
        try:
            debug_file = Path(__file__).parent.parent / "data" / "vl_debug_last.txt"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("最新VL调试信息\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"截图路径: {image_path}\n\n")
                f.write("VL原始返回:\n")
                f.write("-" * 80 + "\n")
                f.write(result_text + "\n")
                f.write("-" * 80 + "\n\n")
                f.write("最终返回的content:\n")
                f.write("-" * 80 + "\n")
                f.write(content + "\n")
                f.write("-" * 80 + "\n")
        except Exception as e:
            print(f"[警告] 无法写入调试文件: {e}")
        
        return {"content": content}
    
    def _save_vl_qa_record(self, prompt: str, response: str, image_path: str, kwargs: Dict[str, Any]):
        """保存VL调用记录到Memory"""
        try:
            # 检查是否是PLAN生成过程的调用，如果是则不记录
            context = kwargs.get("context", "")
            if context == "plan_generation":
                print("[QA记录] 跳过PLAN生成过程的调用")
                return
            
            import uuid
            from datetime import datetime
            
            qa_id = f"qa_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            
            # 生成prompt预览（前100字符）
            prompt_preview = prompt[:100] + "..." if len(prompt) > 100 else prompt
            
            record = {
                "qa_id": qa_id,
                "prompt": prompt,
                "prompt_preview": prompt_preview,
                "response": response,
                "model_type": "vl",  # VL类型
                "model_used": "ernie-4.5-turbo-vl",
                "tool_name": "screenshot_and_analyze",
                "image_path": image_path,
                "flow_id": kwargs.get("flow_id", ""),
                "status": "unmarked",
                "created_at": datetime.now().isoformat()
            }
            
            qa_dir = Path("service/data/memories/qa_records")
            qa_dir.mkdir(parents=True, exist_ok=True)
            
            with open(qa_dir / f"{qa_id}.json", 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            
            print(f"[QA记录] 已保存: {qa_id} (VL)")
            
        except Exception as e:
            # QA记录保存失败不应影响主流程
            print(f"[WARN] 保存VL QA记录失败: {e}")
    
    def _parse_json(self, text: str) -> dict:
        """解析JSON"""
        # 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 去除markdown
        try:
            cleaned_text = re.sub(r'```json\s*|\s*```', '', text, flags=re.MULTILINE)
            return json.loads(cleaned_text.strip())
        except json.JSONDecodeError:
            pass
        
        # 提取JSON块
        try:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        
        raise RuntimeError(f"无法解析JSON: {text[:500]}")


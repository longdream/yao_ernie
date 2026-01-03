"""
交互工具 - UI自动化交互工具
"""
import sys
from pathlib import Path
import time
from typing import Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from planscope.tools.base_tool import BaseTool

try:
    import pyautogui
    HAS_UI_LIBS = True
except ImportError:
    HAS_UI_LIBS = False
    print("[交互工具] 警告: pyautogui未安装，UI自动化功能不可用")


class TypeTextTool(BaseTool):
    """文字输入工具"""
    
    TOOL_NAME = "type_text"
    TOOL_DESCRIPTION = "在当前焦点位置输入文字"
    TOOL_TYPE = "function"
    
    INPUT_PARAMETERS = {
        "text": {
            "type": "str",
            "required": True,
            "description": "要输入的文字"
        },
        "interval": {
            "type": "float",
            "required": False,
            "default": 0.05,
            "description": "按键间隔时间（秒）"
        }
    }
    
    OUTPUT_JSON_SCHEMA = """{
  "content": "执行结果（字符串）"
}"""
    
    def __init__(self):
        """初始化工具"""
        super().__init__()
    
    def _execute_impl(self, text: str, interval: float = 0.05, **kwargs) -> Dict[str, Any]:
        """
        输入文字
        
        Args:
            text: 要输入的文字
            interval: 按键间隔
            
        Returns:
            执行结果
        """
        print(f"[输入工具] 开始输入文字，长度: {len(text)}")
        
        if not HAS_UI_LIBS:
            raise RuntimeError("pyautogui未安装，无法使用输入功能")
        
        try:
            # 使用pyperclip粘贴（支持中文）
            try:
                import pyperclip
                pyperclip.copy(text)
                pyautogui.hotkey('ctrl', 'v')
                print("[输入工具] 使用剪贴板粘贴")
            except ImportError:
                # 回退到逐字输入
                pyautogui.write(text, interval=interval)
                print("[输入工具] 使用逐字输入")
            
            return {"content": f"已输入文字，长度: {len(text)}"}
            
        except Exception as e:
            print(f"[输入工具] 错误: {e}")
            raise RuntimeError(f"输入失败: {str(e)}") from e


class ClickElementTool(BaseTool):
    """鼠标点击工具"""
    
    TOOL_NAME = "click_element"
    TOOL_DESCRIPTION = "在指定坐标位置执行鼠标点击"
    TOOL_TYPE = "function"
    
    INPUT_PARAMETERS = {
        "x": {
            "type": "int",
            "required": True,
            "description": "X坐标"
        },
        "y": {
            "type": "int",
            "required": True,
            "description": "Y坐标"
        },
        "button": {
            "type": "str",
            "required": False,
            "default": "left",
            "description": "鼠标按钮：left、right、middle"
        },
        "clicks": {
            "type": "int",
            "required": False,
            "default": 1,
            "description": "点击次数"
        }
    }
    
    OUTPUT_JSON_SCHEMA = """{
  "content": "执行结果（字符串）"
}"""
    
    def __init__(self):
        """初始化工具"""
        super().__init__()
    
    def _execute_impl(self, x: int, y: int, button: str = "left", clicks: int = 1, **kwargs) -> Dict[str, Any]:
        """
        执行点击
        
        Args:
            x: X坐标
            y: Y坐标
            button: 鼠标按钮
            clicks: 点击次数
            
        Returns:
            执行结果
        """
        print(f"[点击工具] 点击位置: ({x}, {y}), 按钮: {button}, 次数: {clicks}")
        
        if not HAS_UI_LIBS:
            raise RuntimeError("pyautogui未安装，无法使用点击功能")
        
        try:
            pyautogui.click(x, y, clicks=clicks, button=button)
            return {"content": f"已在({x}, {y})执行{clicks}次{button}点击"}
            
        except Exception as e:
            print(f"[点击工具] 错误: {e}")
            raise RuntimeError(f"点击失败: {str(e)}") from e


class ScrollTool(BaseTool):
    """滚动工具"""
    
    TOOL_NAME = "scroll"
    TOOL_DESCRIPTION = "在当前鼠标位置执行滚轮滚动"
    TOOL_TYPE = "function"
    
    INPUT_PARAMETERS = {
        "clicks": {
            "type": "int",
            "required": True,
            "description": "滚动量，正数向上，负数向下"
        },
        "x": {
            "type": "int",
            "required": False,
            "description": "X坐标（可选，不提供则使用当前位置）"
        },
        "y": {
            "type": "int",
            "required": False,
            "description": "Y坐标（可选，不提供则使用当前位置）"
        }
    }
    
    OUTPUT_JSON_SCHEMA = """{
  "content": "执行结果（字符串）"
}"""
    
    def __init__(self):
        """初始化工具"""
        super().__init__()
    
    def _execute_impl(self, clicks: int, x: int = None, y: int = None, **kwargs) -> Dict[str, Any]:
        """
        执行滚动
        
        Args:
            clicks: 滚动量
            x: X坐标（可选）
            y: Y坐标（可选）
            
        Returns:
            执行结果
        """
        print(f"[滚动工具] 滚动量: {clicks}")
        
        if not HAS_UI_LIBS:
            raise RuntimeError("pyautogui未安装，无法使用滚动功能")
        
        try:
            if x is not None and y is not None:
                pyautogui.moveTo(x, y, duration=0.1)
                time.sleep(0.1)
            
            pyautogui.scroll(clicks)
            
            direction = "向上" if clicks > 0 else "向下"
            return {"content": f"已{direction}滚动{abs(clicks)}单位"}
            
        except Exception as e:
            print(f"[滚动工具] 错误: {e}")
            raise RuntimeError(f"滚动失败: {str(e)}") from e


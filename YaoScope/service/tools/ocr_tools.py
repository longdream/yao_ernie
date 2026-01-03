"""
OCR工具 - 图像文字识别工具

使用 PaddleOCR 进行智能区域检测和文字提取
"""
import sys
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from planscope.tools.base_tool import BaseTool

# 导入 OCRHelper
from service.utils.ocr_helper import get_ocr_helper, HAS_PADDLE_OCR


class OCRExtractTool(BaseTool):
    """OCR文字识别工具（使用共享的 OCRHelper）"""

    TOOL_NAME = "ocr_extract_text"
    TOOL_DESCRIPTION = """使用OCR（Optical Character Recognition）技术精确识别和提取图片中的文字。

工具职责：
- 纯粹的图片→文字转换
- 逐字逐行精确识别图片中的所有可见文字
- 支持智能区域裁剪，自动过滤 UI 噪音

特点：
- 基于PaddleOCR深度学习模型
- 逐字逐行精确识别
- 保持原文换行和格式
- 支持中英文混合识别
- 支持智能区域检测（自动过滤侧边栏、标题栏、工具栏）

适用场景：
- 文档内容提取（Word、记事本、PDF等）
- 需要精确文字内容的场景
- 文本续写、改写、扩写等需要完整原文的任务
- 聊天记录提取（自动过滤联系人列表等噪音）

智能区域模式：
- 'auto': 自动检测（根据应用名称判断）
- 'chat': 聊天应用（过滤侧边栏、标题栏、工具栏）
- 'document': 文档应用（过滤标题栏、工具栏）
- 'center': 中心区域（过滤边缘）
- 'full': 不裁剪

输入：
- image_path: 图片文件路径（必须引用前序步骤的screenshot_path，如{{steps.1.screenshot_path}}）
- region_type: 智能裁剪区域类型（可选，默认'full'）
- app_name: 应用名称（可选，用于auto模式判断）

输出：
- content: 识别出的完整文字内容（原样输出所有识别到的文字，保持原格式）"""
    
    TOOL_TYPE = "function"
    
    INPUT_PARAMETERS = {
        "image_path": {
            "type": "str",
            "required": True,
            "description": "图片路径。⚠️ 重要：应该引用前序步骤（如screenshot_and_analyze）的screenshot_path输出，格式为{{steps.X.screenshot_path}}，不要使用user_input引用"
        },
        "region_type": {
            "type": "str",
            "required": False,
            "default": "full",
            "description": "智能裁剪区域类型：'auto'(自动检测)、'chat'(聊天应用)、'document'(文档应用)、'center'(中心区域)、'full'(不裁剪，默认)"
        },
        "app_name": {
            "type": "str",
            "required": False,
            "default": "",
            "description": "应用名称（用于auto模式判断区域类型）"
        },
        "language": {
            "type": "str",
            "required": False,
            "default": "ch",
            "description": "语言代码，如'ch'(中文)、'en'(英文)"
        }
    }
    
    OUTPUT_JSON_SCHEMA = """{
  "content": "识别的文字内容（字符串）"
}"""
    
    def __init__(self):
        """初始化工具"""
        super().__init__()
        self.ocr_helper = None
    
    @classmethod
    def pre_initialize(cls):
        """
        预初始化 PaddleOCR（在服务启动时调用）
        使用 OCRHelper 的单例模式
        """
        if not HAS_PADDLE_OCR:
            print("[OCR预初始化] PaddleOCR未安装，跳过")
            return
        
        print("[OCR预初始化] 初始化 PaddleOCR (文字检测，首次会下载模型)...")
        ocr_helper = get_ocr_helper()
        # 触发 PaddleOCR 初始化
        ocr_helper._ensure_ocr_initialized()
        print("[OCR预初始化] 完成")
    
    def _execute_impl(
        self,
        image_path: str,
        region_type: str = "full",
        app_name: str = "",
        language: str = "ch",
        **kwargs
    ) -> Dict[str, Any]:
        """
        使用OCR识别图片中的文字
        
        Args:
            image_path: 图片路径
            region_type: 智能裁剪区域类型
            app_name: 应用名称（用于auto模式）
            language: 语言代码
            
        Returns:
            识别结果
        """
        print(f"[OCR工具] 开始识别: {image_path}, 区域类型: {region_type}")
        
        if not HAS_PADDLE_OCR:
            raise RuntimeError("PaddleOCR未安装，无法使用OCR功能")
        
        # 检查文件存在
        if not Path(image_path).exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        
        try:
            import time
            
            # 获取 OCRHelper 单例
            if self.ocr_helper is None:
                self.ocr_helper = get_ocr_helper()
            
            start_time = time.time()
            
            # 根据区域类型选择处理方式
            if region_type == "full":
                # 不裁剪，直接提取文本
                print("[OCR工具] 模式: full，直接提取文本")
                content = self.ocr_helper.extract_text(image_path)
            else:
                # 智能裁剪后提取文本
                print(f"[OCR工具] 模式: {region_type}，使用智能裁剪")
                content, cropped_path = self.ocr_helper.extract_text_with_crop(
                    image_path,
                    region_type=region_type,
                    app_name=app_name
                )
                
                # 清理裁剪后的临时文件
                if cropped_path and cropped_path != image_path:
                    try:
                        Path(cropped_path).unlink()
                    except Exception:
                        pass
            
            elapsed = time.time() - start_time
            print(f"[OCR工具] 识别完成，提取文字长度: {len(content)}，耗时: {elapsed:.2f}秒")
            
            return {"content": content}
            
        except Exception as e:
            print(f"[OCR工具] 错误: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"OCR识别失败: {str(e)}") from e

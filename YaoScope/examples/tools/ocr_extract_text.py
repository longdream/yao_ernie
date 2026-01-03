"""
OCR文字提取工具
使用PaddleOCR从图片中精确提取文字

⚠️ OCR vs VL的区别：
- OCR：专业文字提取，精确识别文字位置和内容，但不理解语义
- VL：AI的"眼睛"，能理解图片语义，但文字识别精度一般

最佳实践：
- 需要精确文字时使用OCR
- 需要理解图片语义时使用VL
- 可以配合使用：VL理解整体+OCR提取精确文字
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from planscope.tools.base_tool import BaseTool

try:
    from paddleocr import PaddleOCR
    HAS_PADDLEOCR = True
except ImportError:
    HAS_PADDLEOCR = False
    print("[OCR工具] 警告: PaddleOCR未安装，OCR功能不可用")


class OCRExtractTool(BaseTool):
    """OCR文字提取工具"""
    
    TOOL_NAME = "ocr_extract_text"
    TOOL_DESCRIPTION = "使用OCR技术精确提取图片中的文字"
    TOOL_TYPE = "function"
    
    INPUT_PARAMETERS = {
        "image_path": {
            "type": "str",
            "required": True,
            "description": "图片路径"
        },
        "language": {
            "type": "str",
            "required": False,
            "default": "ch",
            "description": "识别语言（ch=中文，en=英文）"
        }
    }
    
    OUTPUT_JSON_SCHEMA = """{
  "content": "提取的完整文本（字符串）"
}"""
    
    def __init__(self):
        """初始化OCR工具"""
        super().__init__()
        if not HAS_PADDLEOCR:
            raise ImportError("PaddleOCR未安装，请运行: pip install paddleocr")
    
    def _execute_impl(self, image_path: str, language: str = "ch", **kwargs) -> dict:
        """
        执行OCR文字提取
        
        Args:
            image_path: 图片路径
            language: 识别语言（ch=中文，en=英文）
            **kwargs: 其他参数
            
        Returns:
            dict: {"content": "提取的完整文本"}
            
        Raises:
            FileNotFoundError: 图片文件不存在
            RuntimeError: OCR识别失败
        """
        print(f"[OCR工具] 开始提取文字: {image_path}")
        
        image_file = Path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        
        try:
            # 初始化PaddleOCR
            ocr = PaddleOCR(
                use_angle_cls=True,
                lang=language,
                show_log=False
            )
            
            # 执行OCR
            result = ocr.ocr(str(image_file), cls=True)
            
            # 解析结果
            text_lines = []
            for line in result[0]:
                text_lines.append(line[1][0])
            
            full_text = "\n".join(text_lines)
            
            print(f"[OCR工具] 提取成功:")
            print(f"  - 识别行数: {len(text_lines)}")
            print(f"  - 文字总长度: {len(full_text)}字符")
            
            # 统一输出格式
            return {
                "content": full_text
            }
            
        except Exception as e:
            print(f"[OCR工具] OCR识别失败: {e}")
            raise RuntimeError(f"OCR识别失败: {str(e)}")


if __name__ == "__main__":
    # 测试工具
    print("请使用测试脚本进行测试")


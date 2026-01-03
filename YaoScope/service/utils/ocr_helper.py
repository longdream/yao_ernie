"""
PaddleOCR 智能区域检测工具

基于 PaddleOCR 实现智能区域检测和文本提取：
- 使用 PaddleOCR 检测文本框位置
- 根据文本框分布智能裁剪内容区域（过滤侧边栏、标题栏、工具栏等UI噪音）
- 支持多种区域模式：chat、document、center、full、auto
- 单例模式共享 PaddleOCR 实例

注意：这只是 OCR 文字检测，VL（视觉语言）模型通过 vl_tools.py 调用 API 实现
"""

import os
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from PIL import Image

# PaddleOCR 导入
try:
    from paddleocr import PaddleOCR
    HAS_PADDLE_OCR = True
except ImportError:
    HAS_PADDLE_OCR = False
    print("[OCRHelper] Warning: PaddleOCR not installed")


class OCRHelper:
    """
    PaddleOCR 智能区域检测工具
    
    特性：
    - 单例模式共享 PaddleOCR 实例
    - 智能区域检测（自动过滤 UI 噪音）
    - 支持多种区域模式
    """
    
    # 单例实例
    _instance: Optional['OCRHelper'] = None
    _lock = threading.Lock()
    
    # PaddleOCR 实例
    _ocr: Optional[PaddleOCR] = None
    _ocr_lock = threading.Lock()
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化（只执行一次）"""
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        print("[OCRHelper] Initializing singleton instance...")
    
    @classmethod
    def get_instance(cls) -> 'OCRHelper':
        """获取单例实例"""
        return cls()
    
    def _ensure_ocr_initialized(self) -> PaddleOCR:
        """确保 PaddleOCR 已初始化"""
        if not HAS_PADDLE_OCR:
            raise RuntimeError("PaddleOCR not installed")
        
        if OCRHelper._ocr is None:
            with OCRHelper._ocr_lock:
                if OCRHelper._ocr is None:
                    print("[OCRHelper] Initializing PaddleOCR (for text detection, not VL model)...")
                    start_time = time.time()
                    
                    # 设置模型缓存目录
                    project_root = Path(__file__).parent.parent.parent
                    models_dir = project_root / "models" / "paddleocr"
                    models_dir.mkdir(parents=True, exist_ok=True)
                    os.environ['PADDLEX_HOME'] = str(models_dir)
                    
                    # 初始化 PaddleOCR (用于文字检测和区域裁剪，首次会自动下载模型)
                    # 注意: use_angle_cls 和 use_textline_orientation 互斥，只能选一个
                    OCRHelper._ocr = PaddleOCR(
                        lang='ch',
                        ocr_version='PP-OCRv4',
                        use_angle_cls=False  # 截图通常不需要旋转检测
                    )
                    
                    elapsed = time.time() - start_time
                    print(f"[OCRHelper] PaddleOCR initialized ({elapsed:.2f}s)")
        
        return OCRHelper._ocr
    
    def extract_boxes_from_result(self, ocr_result) -> List[Dict[str, Any]]:
        """
        从 PaddleOCR 结果中提取文本框信息
        
        Args:
            ocr_result: PaddleOCR predict 的结果
            
        Returns:
            包含文本框信息的列表
        """
        all_boxes = []
        
        for res in ocr_result:
            # PaddleOCR 3.0 API - 结果是字典形式
            if hasattr(res, 'keys'):
                texts = res.get('rec_texts', [])
                polys = res.get('dt_polys', [])
                scores = res.get('rec_scores', [])
                
                for text, poly, score in zip(texts, polys, scores):
                    if poly is not None and len(poly) >= 4:
                        x_coords = [p[0] for p in poly]
                        y_coords = [p[1] for p in poly]
                        x_min, x_max = min(x_coords), max(x_coords)
                        y_min, y_max = min(y_coords), max(y_coords)
                        
                        all_boxes.append({
                            'box': poly,
                            'text': text,
                            'confidence': float(score),
                            'x_min': float(x_min),
                            'x_max': float(x_max),
                            'y_min': float(y_min),
                            'y_max': float(y_max),
                            'center_x': (x_min + x_max) / 2,
                            'center_y': (y_min + y_max) / 2
                        })
        
        return all_boxes
    
    def get_content_region_bbox(
        self,
        all_boxes: List[Dict[str, Any]],
        image_width: int,
        image_height: int,
        region_type: str = 'auto',
        app_name: str = ''
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        根据文本框位置检测内容区域
        
        Args:
            all_boxes: 文本框信息列表
            image_width: 图像宽度
            image_height: 图像高度
            region_type: 区域类型
                - 'auto': 自动检测（根据 app_name 判断）
                - 'chat': 聊天模式（过滤侧边栏、标题栏、工具栏）
                - 'document': 文档模式（过滤标题栏、工具栏）
                - 'center': 中心模式（聚焦中心 80% 区域）
                - 'full': 完整模式（不过滤）
            app_name: 应用名称（用于 auto 模式判断）
            
        Returns:
            (x_min, y_min, x_max, y_max) 内容区域边界框，或 None
        """
        if not all_boxes:
            return None
        
        # auto 模式：根据应用名称选择区域类型
        if region_type == 'auto':
            app_lower = app_name.lower()
            if any(kw in app_lower for kw in ['微信', 'wechat', 'qq', '钉钉', 'dingtalk', '企业微信', 'wecom']):
                region_type = 'chat'
            elif any(kw in app_lower for kw in ['记事本', 'notepad', 'word', 'vscode', 'code']):
                region_type = 'document'
            else:
                region_type = 'center'
        
        # 根据区域类型设置过滤参数
        if region_type == 'chat':
            # 聊天模式：过滤左侧边栏（35%）、顶部标题栏（10%）、底部工具栏（15%）
            sidebar_threshold = image_width * 0.35
            title_bar_threshold = image_height * 0.10
            toolbar_threshold = image_height * 0.85
        elif region_type == 'document':
            # 文档模式：过滤顶部标题栏（8%）、底部工具栏（5%）
            sidebar_threshold = 0  # 不过滤侧边栏
            title_bar_threshold = image_height * 0.08
            toolbar_threshold = image_height * 0.95
        elif region_type == 'center':
            # 中心模式：过滤边缘 10%
            sidebar_threshold = image_width * 0.10
            title_bar_threshold = image_height * 0.10
            toolbar_threshold = image_height * 0.90
        else:  # full
            # 完整模式：不过滤
            sidebar_threshold = 0
            title_bar_threshold = 0
            toolbar_threshold = image_height
        
        # 过滤文本框
        filtered_boxes = []
        for box in all_boxes:
            # 检查是否在内容区域内
            if box['x_min'] >= sidebar_threshold:
                if box['y_min'] >= title_bar_threshold:
                    if box['y_max'] <= toolbar_threshold:
                        filtered_boxes.append(box)
        
        # 如果过滤后没有文本框，使用所有文本框
        if not filtered_boxes:
            print(f"[OCRHelper] No boxes after filtering ({region_type}), using all boxes")
            filtered_boxes = all_boxes
        
        # 计算边界框
        x_min = min(box['x_min'] for box in filtered_boxes)
        y_min = min(box['y_min'] for box in filtered_boxes)
        x_max = max(box['x_max'] for box in filtered_boxes)
        y_max = max(box['y_max'] for box in filtered_boxes)
        
        # 添加边距
        padding_x = (x_max - x_min) * 0.02
        padding_y = (y_max - y_min) * 0.02
        
        x_min = max(0, x_min - padding_x)
        y_min = max(0, y_min - padding_y)
        x_max = min(image_width, x_max + padding_x)
        y_max = min(image_height, y_max + padding_y)
        
        return (int(x_min), int(y_min), int(x_max), int(y_max))
    
    def extract_text(self, image_path: str) -> str:
        """
        提取图像中的所有文本
        
        Args:
            image_path: 图像路径
            
        Returns:
            提取的文本内容
        """
        ocr = self._ensure_ocr_initialized()
        
        with OCRHelper._ocr_lock:
            result = ocr.predict(image_path)
        
        if result and len(result) > 0:
            ocr_result = result[0]
            texts = ocr_result.get('rec_texts', [])
            return "\n".join(texts)
        
        return ""
    
    def extract_text_with_crop(
        self,
        image_path: str,
        region_type: str = 'auto',
        app_name: str = ''
    ) -> Tuple[str, Optional[str]]:
        """
        智能裁剪后提取文本
        
        Args:
            image_path: 图像路径
            region_type: 区域类型
            app_name: 应用名称
            
        Returns:
            (提取的文本, 裁剪后的图像路径)
        """
        ocr = self._ensure_ocr_initialized()
        
        # 获取图像尺寸
        image = Image.open(image_path)
        img_width, img_height = image.size
        
        # OCR 识别
        with OCRHelper._ocr_lock:
            result = ocr.predict(image_path)
        
        if not result or len(result) == 0:
            return "", None
        
        # 提取文本框
        all_boxes = self.extract_boxes_from_result(result)
        
        if not all_boxes:
            return "", None
        
        # 获取内容区域
        bbox = self.get_content_region_bbox(
            all_boxes, img_width, img_height,
            region_type=region_type, app_name=app_name
        )
        
        if bbox is None:
            # 无法检测区域，返回所有文本
            texts = [box['text'] for box in all_boxes]
            return "\n".join(texts), None
        
        # 过滤在区域内的文本
        x_min, y_min, x_max, y_max = bbox
        filtered_texts = []
        for box in all_boxes:
            # 检查文本框中心是否在区域内
            if (x_min <= box['center_x'] <= x_max and
                y_min <= box['center_y'] <= y_max):
                filtered_texts.append(box['text'])
        
        # 裁剪图像
        cropped = image.crop(bbox)
        
        # 保存裁剪后的图像
        cropped_path = str(Path(image_path).parent / f"cropped_{Path(image_path).name}")
        cropped.save(cropped_path)
        
        return "\n".join(filtered_texts), cropped_path
    
    def crop_to_content_region(
        self,
        image_path: str,
        region_type: str = 'auto',
        app_name: str = ''
    ) -> Tuple[Optional[str], Optional[Tuple[int, int, int, int]]]:
        """
        将图像裁剪到内容区域
        
        Args:
            image_path: 图像路径
            region_type: 区域类型
            app_name: 应用名称
            
        Returns:
            (裁剪后的图像路径, 边界框) 或 (None, None)
        """
        ocr = self._ensure_ocr_initialized()
        
        # 获取图像尺寸
        image = Image.open(image_path)
        img_width, img_height = image.size
        
        print(f"[OCRHelper] Cropping image: {img_width}x{img_height}, mode={region_type}, app={app_name}")
        
        # OCR 识别获取文本框位置
        with OCRHelper._ocr_lock:
            result = ocr.predict(image_path)
        
        if not result or len(result) == 0:
            print("[OCRHelper] No OCR result, returning original image")
            return image_path, None
        
        # 提取文本框
        all_boxes = self.extract_boxes_from_result(result)
        
        if not all_boxes:
            print("[OCRHelper] No text boxes found, returning original image")
            return image_path, None
        
        print(f"[OCRHelper] Found {len(all_boxes)} text boxes")
        
        # 获取内容区域
        bbox = self.get_content_region_bbox(
            all_boxes, img_width, img_height,
            region_type=region_type, app_name=app_name
        )
        
        if bbox is None:
            print("[OCRHelper] Could not detect content region")
            return image_path, None
        
        x_min, y_min, x_max, y_max = bbox
        crop_width = x_max - x_min
        crop_height = y_max - y_min
        
        print(f"[OCRHelper] Content region: ({x_min},{y_min}) - ({x_max},{y_max})")
        print(f"[OCRHelper] Crop size: {crop_width}x{crop_height} ({crop_width*100/img_width:.1f}% x {crop_height*100/img_height:.1f}%)")
        
        # 检查裁剪区域是否有意义（至少是原图的 20%）
        if crop_width < img_width * 0.2 or crop_height < img_height * 0.2:
            print("[OCRHelper] Crop region too small, returning original image")
            return image_path, None
        
        # 裁剪图像
        cropped = image.crop(bbox)
        
        # 保存裁剪后的图像
        cropped_path = str(Path(image_path).parent / f"cropped_{Path(image_path).name}")
        cropped.save(cropped_path)
        
        print(f"[OCRHelper] Cropped image saved: {cropped_path}")
        
        return cropped_path, bbox
    
    def get_text_from_boxes(self, all_boxes: List[Dict[str, Any]]) -> str:
        """
        从文本框列表中提取文本
        
        Args:
            all_boxes: 文本框信息列表
            
        Returns:
            提取的文本
        """
        return "\n".join(box['text'] for box in all_boxes)


# 便捷函数
def get_ocr_helper() -> OCRHelper:
    """获取 OCRHelper 单例实例"""
    return OCRHelper.get_instance()


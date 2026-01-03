"""
聊天记录完整获取工具（多次scroll+截图+分析）
专为微信等自定义滚动控件的应用设计

核心特性：
1. 自动校准：测试需要多少次scroll(3行)才能滚动一页
2. 多次scroll循环：执行N次pyautogui.scroll()实现一页滚动
3. 智能检测当前滚动位置（是否在底部）
4. 从底部向上滚动，确保获取所有历史记录
5. 图像哈希算法判断到达顶部
6. VL模型逐页分析截图内容
7. 拼接完整对话记录
8. 自动清理临时文件
9. PaddleOCR 智能区域裁剪（过滤 UI 噪音）

关键技术突破：
- 微信PC端会吃掉滚轮事件，每次只响应系统默认3行滚动
- pyautogui.scroll(100) 和 scroll(-500) 效果相同（都是3行）
- 解决方案：多次调用scroll() -> 累积滚动效果 -> 实现一页滚动

工作流程：
阶段1：校准 -> 测试需要多少次scroll才能滚动一页
阶段2：定位 -> 检测位置 -> 滚到底部（如需要）
阶段3：采集 -> 向上滚动(多次scroll) -> 截图 -> 智能裁剪 -> 判断结束
阶段4：分析 -> VL提取 -> 内容拼接 -> 返回结果
阶段5：清理 -> 删除临时文件
"""
import sys
from pathlib import Path
import time
import json
import shutil
from typing import Dict, Any, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from planscope.tools.base_tool import BaseTool
from planscope.utils.window_manager import WindowManager

# 导入 OCRHelper
from service.utils.ocr_helper import get_ocr_helper

# 导入依赖库
try:
    import pyautogui
    from PIL import Image
    import imagehash
    HAS_UI_LIBS = True
except ImportError:
    HAS_UI_LIBS = False
    Image = None  # 用于类型提示
    print("[滚动分析工具] 警告: pyautogui/Pillow/imagehash未安装，UI自动化功能不可用")


class ScrollAndAnalyzeTool(BaseTool):
    """
    多次scroll循环 + 截图分析的集成工具
    
    功能：
    - 自动校准：测试需要多少次scroll才能滚动一页
    - 多次scroll循环：执行N次pyautogui.scroll()实现一页滚动
    - 智能检测当前滚动位置（是否在底部）
    - 聊天工具专用：自动向上滚动获取历史记录
    - 智能停止判断（图像哈希对比）
    - VL模型逐张分析截图
    - 拼接完整对话记录
    - 自动清理临时文件
    
    滚动策略（针对微信等自定义控件应用）：
    1. 自动校准：测试需要多少次scroll(向下3行)才能滚动80%窗口
    2. 检测是否已经在底部
    3. 如果不在底部，多次scroll向下到底部
    4. 从底部开始多次scroll向上，获取所有历史记录
    """
    
    TOOL_NAME = "scroll_and_analyze"
    TOOL_DESCRIPTION = """自动滚动聊天窗口并分析完整内容（专为微信、QQ等聊天应用设计）

⚠️ 何时使用此工具（关键判断）：
- 用户要求"所有聊天记录"、"完整聊天记录"、"全部历史消息"、"所有历史记录"
- 用户要求"分析聊天记录"、"总结聊天内容"但没有限定范围（默认需要完整历史）
- 任务需要获取屏幕外的历史内容（向上滚动获取更多消息）
- 用户明确表示需要"完整"、"全部"、"所有"等词汇

⚠️ 何时不使用此工具：
- 仅回复最新一条消息 → 使用 screenshot_and_analyze（无需滚动）
- 浏览器页面滚动 → 使用 screenshot_and_analyze + auto_scroll=True
- 用户明确只要"当前屏幕"、"最新消息" → 使用 screenshot_and_analyze

核心功能：
1. 自动校准：基于窗口高度计算需要多少次scroll才能滚动一页
2. 智能定位：检测当前是否在底部，如果不在则自动滚到底部
3. 向上采集：从底部向上滚动，每滚动一页截图一次
4. 智能停止：使用图像哈希算法判断是否到达顶部（连续两张截图相同）
5. VL逐页分析：每页截图都用VL模型提取聊天内容
6. 内容拼接：将所有页面的内容按时间顺序拼接
7. 自动清理：完成后删除所有临时截图文件

技术特点：
- 针对微信等自定义控件优化（每次scroll只移动3行，需要多次累积）
- 使用经验值计算滚动次数（单次scroll约12像素，目标40%窗口高度）
- 保留60%内容重叠，避免消息丢失
- 支持智能底部检测，避免遗漏最新消息

微信/QQ聊天界面识别规则（重要）：
- 消息气泡贴左边（左对齐）= 对方发送的消息
- 消息气泡贴右边（右对齐）= 我发送的消息
- 左侧消息通常是白色/灰色气泡
- 右侧消息通常是绿色/蓝色气泡
- 直接输出消息内容，不要添加位置标记（如[左侧]、[右侧]等）

输出：
- content: 拼接后的完整聊天内容（字符串），包含所有历史记录
"""
    TOOL_TYPE = "vl"  # 工具有prompt参数，用于指导VL模型分析
    
    INPUT_PARAMETERS = {
        "app_names": {
            "type": "list",
            "required": True,
            "description": "应用名称列表（支持多个可能的名称），如['微信', 'WeChat', 'WeChat.exe']。由ACE智能推理生成，包含中文名、英文名、进程名等。"
        },
        "prompt": {
            "type": "str",
            "required": True,
            "description": "内容提取任务描述，由ACE动态生成，用于指导VL分析截图。应该包含聊天记录提取的具体要求，如'提取聊天消息内容'。"
        },
        "max_scrolls": {
            "type": "int",
            "required": False,
            "default": 20,
            "description": "最大滚动次数，防止无限循环。默认20次，可根据聊天记录长度调整。"
        },
        "region_type": {
            "type": "str",
            "required": False,
            "default": "chat",
            "description": "智能裁剪区域类型：'chat'(聊天应用，过滤侧边栏，默认)、'document'(文档应用)、'center'(中心区域)、'full'(不裁剪)"
        }
    }
    
    OUTPUT_JSON_SCHEMA = """{
    "content": "拼接后的完整聊天内容（字符串）"
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
    
    def _execute_impl(self, app_names: List[str], prompt: str, max_scrolls: int = 20, region_type: str = "chat", **kwargs) -> Dict[str, Any]:
        """
        执行滚动截图分析
        
        Args:
            app_names: 应用名称列表（由ACE智能推理生成）
            prompt: VL分析任务描述
            max_scrolls: 最大滚动次数
            region_type: 智能裁剪区域类型
            
        Returns:
            Dict包含拼接后的完整内容
        """
        print("=" * 80)
        print(f"[滚动分析工具] 开始执行，区域类型: {region_type}")
        print("=" * 80)
        
        try:
            # 1. 滚动并截图
            print(f"\n[步骤1] 滚动窗口并截图...")
            print(f"[步骤1] 应用名称: {app_names}")
            screenshots = self._scroll_and_capture(app_names, max_scrolls, region_type)
            
            if not screenshots:
                return {"content": "未能获取任何截图"}
            
            print(f"[步骤1] 完成，共获得 {len(screenshots)} 张截图")
            
            # 2. VL逐张分析
            print(f"\n[步骤2] 使用VL模型分析截图...")
            contents = []
            for i, img_path in enumerate(screenshots, 1):
                print(f"  分析截图 {i}/{len(screenshots)}: {img_path}")
                result = self._analyze_image(img_path, prompt)
                content = result.get('content', '')
                if content:
                    contents.append(content)
                else:
                    print(f"  警告: 截图 {i} 未提取到内容")
            
            print(f"[步骤2] 完成，成功分析 {len(contents)} 张截图")
            
            # 3. 拼接结果
            print(f"\n[步骤3] 拼接分析结果...")
            if not contents:
                merged_content = "未能从截图中提取到任何内容"
            else:
                # 确保所有元素都是字符串（VL可能返回list或其他类型）
                merged_content = "\n\n--- 下一页 ---\n\n".join([str(c) for c in contents])
            
            print(f"[步骤3] 完成，总长度: {len(merged_content)} 字符")
            
            # 4. 清理临时文件
            print(f"\n[步骤4] 清理临时截图文件...")
            self._cleanup(screenshots)
            print(f"[步骤4] 完成")
            
            print("=" * 80)
            print("[滚动分析工具] 执行成功")
            print("=" * 80)
            
            return {"content": merged_content}
            
        except Exception as e:
            error_msg = f"滚动分析失败: {str(e)}"
            print(f"[滚动分析工具] 错误: {error_msg}")
            return {"content": error_msg}
    
    
    def _calibrate_scroll_times(self, center_x: int, center_y: int, 
                                rect_left: int, rect_top: int, 
                                rect_width: int, rect_height: int,
                                window_height: int, temp_dir: Path) -> int:
        """
        自动校准：基于经验值计算需要多少次scroll才能滚动一页
        
        关键发现（通过实际测试）：
        - 微信限制每次scroll只移动约6像素（系统默认3行）
        - 但是scroll(-50)参数实际效果比scroll(-10)好很多
        - 经验值：约30次scroll(-50)可以滚动50%聊天区域（避免消息丢失）
        
        策略：
        1. 不再依赖不可靠的图像匹配测量
        2. 使用经验公式：聊天区域高度 / 12px（估算单次移动）
        3. 目标：50%聊天区域（保留50%重叠）
        
        Args:
            center_x, center_y: 窗口中心坐标
            rect_left, rect_top, rect_width, rect_height: 窗口区域
            window_height: 窗口高度
            temp_dir: 临时目录
            
        Returns:
            需要执行的scroll次数
        """
        print(f"\n  [校准] 基于经验值计算滚动次数...")
        print(f"  [提示] 窗口高度: {window_height}px")
        
        # 定义聊天内容区域（窗口中间80%）
        chat_area_start = int(window_height * 0.1)  # 顶部10%是标题栏
        chat_area_end = int(window_height * 0.9)    # 底部10%是输入框
        chat_area_height = chat_area_end - chat_area_start
        print(f"  [提示] 聊天区域高度: {chat_area_height}px (占窗口{chat_area_height/window_height*100:.0f}%)")
        
        # 经验值：单次scroll(-50)实际移动约12像素
        estimated_single_scroll_pixels = 12.0
        print(f"  [经验值] 单次scroll(-50)预估移动: {estimated_single_scroll_pixels} 像素")
        
        # 计算需要多少次scroll才能滚动一页
        # 目标：滚动聊天区域高度的40%（保留60%重叠，避免消息丢失）
        target_scroll_distance = chat_area_height * 0.4
        times_needed = max(1, int(target_scroll_distance / estimated_single_scroll_pixels))
        
        print(f"\n  [校准] 计算结果:")
        print(f"    目标距离: {int(target_scroll_distance)} 像素 (40%聊天区域)")
        print(f"    预估单次移动: {estimated_single_scroll_pixels} 像素")
        print(f"    [结论] 需要 {times_needed} 次scroll(-50)才能滚动一页")
        print(f"    [策略] 每页保留60%内容重叠，避免消息丢失")
        
        return times_needed
    
    def _are_images_similar(self, img1_path: str, img2_path: str, threshold: int = 8) -> bool:
        """
        使用imagehash算法对比两张图片是否相似
        
        Args:
            img1_path: 第一张图片路径
            img2_path: 第二张图片路径
            threshold: 哈希距离阈值（默认8，越小越严格）
            
        Returns:
            相似返回True，否则返回False
        """
        try:
            hash1 = imagehash.average_hash(Image.open(img1_path))
            hash2 = imagehash.average_hash(Image.open(img2_path))
            distance = hash1 - hash2
            is_similar = distance < threshold
            return is_similar
        except Exception as e:
            print(f"[滚动分析工具] 图像对比失败: {e}")
            return False
    
    def _scroll_and_capture(self, app_names: List[str], max_scrolls: int, region_type: str = "chat") -> List[str]:
        """
        智能滚动窗口并截图（针对聊天工具）
        
        策略：
        1. 检测是否在底部
        2. 如果不在底部，先滚到底部
        3. 从底部向上滚动，获取所有历史记录
        4. 使用 OCRHelper 智能裁剪每张截图
        
        Args:
            app_names: 应用名称列表
            max_scrolls: 最大滚动次数
            region_type: 智能裁剪区域类型
            
        Returns:
            截图路径列表（从最新到最旧，已裁剪）
        """
        # 1. 查找并激活窗口（使用统一的WindowManager）
        window_handle, window, window_info = WindowManager.find_and_activate(app_names)
        
        # 获取窗口信息
        window_height = window_info['height']
        rect_left = window_info['left']
        rect_top = window_info['top']
        rect_width = window_info['width']
        rect_height = window_info['height']
        center_x = window_info['center_x']
        center_y = window_info['center_y']
        
        # 重要说明
        print(f"\n  [重要] 使用scroll(-50)参数进行滚动")
        print(f"  [方案] 基于经验值计算（单次12px） -> 快速精确")
        print(f"  [效果] 滚动40%聊天区域，保留60%重叠，避免消息丢失")
        
        # 调试信息
        print(f"\n  [调试] 窗口信息:")
        print(f"    - 句柄: {window_handle}")
        print(f"    - 尺寸: {rect_width}x{rect_height}")
        print(f"    - 位置: ({rect_left},{rect_top})")
        print(f"    - 中心: ({center_x},{center_y})")
        
        # 2. 创建临时截图目录
        temp_dir = Path("temp_screenshots")
        temp_dir.mkdir(exist_ok=True)
        
        # 3. 自动校准滚动次数
        print(f"\n  [阶段1] 自动校准滚动次数...")
        scroll_times = self._calibrate_scroll_times(
            center_x, center_y, 
            rect_left, rect_top, rect_width, rect_height,
            window_height, temp_dir
        )
        
        print(f"  [阶段1] 校准完成：需要 {scroll_times} 次scroll才能滚动一页")
        
        # 4. 检测是否在底部
        print(f"\n  [阶段2] 检测当前滚动位置...")
        
        # 尝试向下滚动一次，检查是否在底部
        before_screenshot = temp_dir / "check_before.png"
        pyautogui.screenshot(region=(rect_left, rect_top, rect_width, rect_height)).save(str(before_screenshot))
        
        # 向下滚动
        pyautogui.moveTo(center_x, center_y, duration=0.1)
        time.sleep(0.1)
        for _ in range(scroll_times):
            pyautogui.scroll(-50)  # 负数=向下，使用大值加快速度
            time.sleep(0.02)
        time.sleep(0.2)
        
        after_screenshot = temp_dir / "check_after.png"
        pyautogui.screenshot(region=(rect_left, rect_top, rect_width, rect_height)).save(str(after_screenshot))
        
        is_at_bottom = self._are_images_similar(str(before_screenshot), str(after_screenshot))
        
        # 清理检测截图
        before_screenshot.unlink()
        after_screenshot.unlink()
        
        if is_at_bottom:
            print(f"  已在底部，直接开始向上滚动获取历史记录")
        else:
            print(f"  不在底部，先滚动到底部...")
            # 快速滚到底部
            self._scroll_to_bottom_multi(center_x, center_y, rect_left, rect_top, 
                                        rect_width, rect_height, temp_dir, scroll_times)
            print(f"  已到达底部")
        
        # 5. 从底部开始向上滚动并截图
        print(f"\n  [阶段3] 从底部向上滚动（每次{scroll_times}次scroll），获取所有历史记录...")
        screenshots = []
        
        # 获取 OCRHelper 用于智能裁剪
        ocr_helper = get_ocr_helper()
        app_name = app_names[0] if app_names else ""  # 用于 OCRHelper 的 auto 模式判断
        
        for i in range(max_scrolls):
            # 5.1 截图
            screenshot_path = temp_dir / f"screenshot_{i:03d}.png"
            screenshot = pyautogui.screenshot(
                region=(rect_left, rect_top, rect_width, rect_height)
            )
            screenshot.save(str(screenshot_path))
            
            # 5.1.1 使用 OCRHelper 智能裁剪（如果不是 full 模式）
            final_path = str(screenshot_path)
            if region_type != "full":
                try:
                    cropped_path, bbox = ocr_helper.crop_to_content_region(
                        str(screenshot_path),
                        region_type=region_type,
                        app_name=app_name
                    )
                    if cropped_path and cropped_path != str(screenshot_path):
                        final_path = cropped_path
                        print(f"  截图 {i+1}/{max_scrolls}: {Path(final_path).name} (已裁剪)")
                    else:
                        print(f"  截图 {i+1}/{max_scrolls}: {screenshot_path.name} (未裁剪)")
                except Exception as e:
                    print(f"  截图 {i+1}/{max_scrolls}: {screenshot_path.name} (裁剪失败: {e})")
            else:
                print(f"  截图 {i+1}/{max_scrolls}: {screenshot_path.name}")
            
            screenshots.append(final_path)
            
            # 5.2 检查是否与上一张相同（到达顶部）
            if i > 0 and self._are_images_similar(screenshots[-2], screenshots[-1]):
                print(f"  检测到相同截图，已到达顶部")
                # 删除重复的最后一张截图
                Path(screenshots[-1]).unlink()
                screenshots.pop()
                break
            
            # 5.3 向上滚动一页（执行N次scroll）
            if i < max_scrolls - 1:
                pyautogui.moveTo(center_x, center_y, duration=0.1)
                time.sleep(0.1)
                
                # 执行多次scroll向上
                for _ in range(scroll_times):
                    pyautogui.scroll(50)  # 正数=向上，使用大值加快速度
                    time.sleep(0.02)
                time.sleep(0.2)
        
        print(f"  滚动完成，共截取 {len(screenshots)} 页")
        return screenshots
    
    def _scroll_to_bottom_multi(self, center_x: int, center_y: int,
                                rect_left: int, rect_top: int,
                                rect_width: int, rect_height: int,
                                temp_dir: Path, scroll_times: int, max_attempts: int = 15):
        """
        快速滚动到底部（多次scroll）
        
        关键修复：
        1. 每次只执行一部分scroll（不是全部scroll_times）
        2. 增加连续相同计数，更可靠地判断是否到底
        3. 最大尝试次数保护，避免死循环
        
        Args:
            center_x, center_y: 窗口中心坐标
            rect_left, rect_top, rect_width, rect_height: 窗口区域
            temp_dir: 临时目录
            scroll_times: 每页需要的总scroll次数（用于计算每次执行多少）
            max_attempts: 最大尝试次数（默认15次，约3页）
        """
        print(f"  快速滚动到底部（最多尝试{max_attempts}次）...")
        
        # 每次只执行一部分scroll，避免一次滚太多
        scroll_per_attempt = max(10, scroll_times // 5)  # 每次至少10次，最多1/5页
        print(f"  每次执行{scroll_per_attempt}次scroll(-50)")
        
        consecutive_same = 0  # 连续相同次数
        
        for attempt in range(max_attempts):
            print(f"  [尝试 {attempt + 1}/{max_attempts}] 向下滚动...")
            
            # 截图前状态
            before = temp_dir / "before_bottom.png"
            pyautogui.screenshot(region=(rect_left, rect_top, rect_width, rect_height)).save(str(before))
            
            # 向下滚动（执行部分scroll，不是全部）
            pyautogui.moveTo(center_x, center_y, duration=0.05)
            time.sleep(0.05)
            for _ in range(scroll_per_attempt):
                pyautogui.scroll(-50)  # 负数=向下，使用大值
                time.sleep(0.01)
            time.sleep(0.3)  # 等待滚动完成和UI更新
            
            # 截图后状态
            after = temp_dir / "after_bottom.png"
            pyautogui.screenshot(region=(rect_left, rect_top, rect_width, rect_height)).save(str(after))
            
            # 检查是否到底
            if self._are_images_similar(str(before), str(after)):
                consecutive_same += 1
                print(f"    → 图像相同（连续{consecutive_same}次）")
                
                # 连续2次相同，确认到底
                if consecutive_same >= 2:
                    before.unlink()
                    after.unlink()
                    print(f"\n  ✓ 到达底部（总尝试 {attempt + 1} 次）")
                    return
            else:
                consecutive_same = 0  # 重置计数
                print(f"    → 继续滚动（图像不同）")
            
            before.unlink()
            after.unlink()
        
        # 达到最大尝试次数，强制停止
        print(f"\n  ⚠ 达到最大尝试次数({max_attempts})，强制停止滚动")
    
    def _analyze_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
        """
        使用VL模型分析图片
        
        Args:
            image_path: 图片路径
            prompt: 分析任务描述（由调用方提供，包含应用特定规则）
            
        Returns:
            VL分析结果
        """
        try:
            # 导入VL工具（避免循环导入）
            from service.tools.vl_tools import ScreenshotAndAnalyzeTool
            
            # 直接使用调用方提供的prompt（不添加任何应用特定规则）
            # 使用VL工具的_analyze_image方法
            vl_tool = ScreenshotAndAnalyzeTool(self.vl_model_client)
            result = vl_tool._analyze_image(image_path, prompt, temperature=0.3)
            
            # 确保 content 字段是字符串类型（VL可能返回list或其他类型）
            if 'content' in result:
                content = result['content']
                if isinstance(content, list):
                    # 如果是list，转换为JSON字符串
                    result['content'] = json.dumps(content, ensure_ascii=False)
                elif not isinstance(content, str):
                    # 如果是其他类型，转换为字符串
                    result['content'] = str(content)
            
            return result
            
        except Exception as e:
            print(f"[滚动分析工具] VL分析失败: {e}")
            return {"content": f"图片分析失败: {str(e)}"}
    
    def _cleanup(self, screenshots: List[str]):
        """
        清理临时截图文件
        
        Args:
            screenshots: 截图路径列表
        """
        try:
            temp_dir = Path("temp_screenshots")
            if temp_dir.exists() and temp_dir.is_dir():
                shutil.rmtree(temp_dir)
                print(f"  已清理临时文件: {temp_dir}")
        except Exception as e:
            print(f"  清理临时文件失败: {e}")


# 测试代码
if __name__ == "__main__":
    print("=" * 80)
    print("滚动截图分析工具测试")
    print("=" * 80)
    print("\n注意: 此工具需要实际的VL模型客户端和应用窗口")
    print("请在实际项目中通过PlanScope调用此工具")
    print("\n工具元数据:")
    metadata = ScrollAndAnalyzeTool.get_metadata()
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


"""
统一的窗口管理工具
提供跨工具的窗口查找、激活和信息获取功能
"""
import time
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# 导入依赖库
try:
    from pywinauto import Application
    from pywinauto.findwindows import find_windows
    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False


class WindowNotFoundError(Exception):
    """窗口未找到异常"""
    pass


class WindowActivationError(Exception):
    """窗口激活失败异常"""
    pass


class WindowManager:
    """
    统一的窗口管理器
    
    核心功能：
    1. 根据多个应用名称查找窗口（支持进程名和标题）
    2. 激活指定窗口
    3. 获取窗口信息（位置、大小等）
    
    设计理念：
    - 应用名称列表由ACE在plan生成时智能推理
    - 无硬编码、无默认值
    - 错误时抛出异常（遵循No Fallback原则）
    - 详细日志输出
    """
    
    @staticmethod
    def find_window_by_names(
        app_names: List[str], 
        strategy: str = "first_match"
    ) -> int:
        """
        根据多个应用名称查找窗口
        
        Args:
            app_names: 应用名称列表，如 ["微信", "WeChat", "WeChat.exe"]
                      由ACE在plan生成时智能推理，支持：
                      - 中文名称（如：微信）
                      - 英文名称（如：WeChat）
                      - 进程名称（如：WeChat.exe）
                      - 其他可能的别名
            strategy: 查找策略
                     - "first_match": 返回第一个匹配的窗口（默认）
                     - "all_matches": 返回所有匹配的窗口列表
        
        Returns:
            窗口句柄（hwnd）
        
        Raises:
            WindowNotFoundError: 未找到匹配的窗口
            RuntimeError: pywinauto未安装
        
        Example:
            >>> window = WindowManager.find_window_by_names(["微信", "WeChat", "WeChat.exe"])
            >>> print(f"找到窗口句柄: {window}")
        """
        if not HAS_PYWINAUTO:
            raise RuntimeError(
                "pywinauto未安装，无法使用窗口管理功能。\n"
                "请运行: uv pip install pywinauto"
            )
        
        if not app_names:
            raise ValueError("app_names不能为空，必须提供至少一个应用名称")
        
        print(f"[WindowManager] 开始查找窗口...")
        print(f"[WindowManager] 应用名称列表: {app_names}")
        
        all_matches = []
        
        # 遍历所有应用名称，尝试查找窗口
        for app_name in app_names:
            print(f"[WindowManager] 尝试查找: {app_name}")
            
            # 策略1: 按窗口标题搜索（支持模糊匹配）
            try:
                windows = find_windows(title_re=f".*{app_name}.*")
                if windows:
                    print(f"[WindowManager] [OK] Found {len(windows)} windows by title: {app_name}")
                    all_matches.extend(windows)
                    if strategy == "first_match":
                        return windows[0]
            except Exception as e:
                print(f"[WindowManager] Title search failed: {e}")
            
            # 策略2: 按进程名搜索
            try:
                # 移除.exe后缀（如果有）
                process_name = app_name.replace(".exe", "")
                windows = find_windows(process=process_name)
                if windows:
                    print(f"[WindowManager] [OK] Found {len(windows)} windows by process: {process_name}")
                    all_matches.extend(windows)
                    if strategy == "first_match":
                        return windows[0]
            except Exception as e:
                print(f"[WindowManager] Process search failed: {e}")
        
        # 去重
        all_matches = list(set(all_matches))
        
        if not all_matches:
            error_msg = (
                f"未找到匹配的窗口。\n"
                f"尝试的应用名称: {app_names}\n"
                f"请确保：\n"
                f"1. 应用已打开\n"
                f"2. 应用名称正确（包含中文名、英文名、进程名）\n"
                f"3. 如果是ACE生成的名称，请检查推理是否准确"
            )
            raise WindowNotFoundError(error_msg)
        
        print(f"[WindowManager] 共找到 {len(all_matches)} 个匹配的窗口")
        
        if strategy == "all_matches":
            return all_matches
        else:
            return all_matches[0]
    
    @staticmethod
    def activate_window(window_handle: int, wait_time: float = 0.5) -> Any:
        """
        激活指定窗口
        
        Args:
            window_handle: 窗口句柄
            wait_time: 激活后等待时间（秒）
        
        Returns:
            激活的窗口对象
        
        Raises:
            WindowActivationError: 窗口激活失败
            RuntimeError: pywinauto未安装
        """
        if not HAS_PYWINAUTO:
            raise RuntimeError("pywinauto未安装")
        
        print(f"[WindowManager] 激活窗口 (句柄: {window_handle})...")
        
        try:
            app = Application().connect(handle=window_handle)
            window = app.top_window()
            
            # 设置焦点
            window.set_focus()
            time.sleep(wait_time)
            
            print(f"[WindowManager] [OK] Window activated: {window.window_text()}")
            return window
            
        except Exception as e:
            error_msg = f"激活窗口失败 (句柄: {window_handle}): {str(e)}"
            raise WindowActivationError(error_msg)
    
    @staticmethod
    def get_window_info(window_handle: int) -> Dict[str, Any]:
        """
        获取窗口信息
        
        Args:
            window_handle: 窗口句柄
        
        Returns:
            窗口信息字典，包含：
            - title: 窗口标题
            - left, top: 窗口左上角坐标
            - width, height: 窗口宽度和高度
            - center_x, center_y: 窗口中心坐标
        
        Raises:
            RuntimeError: pywinauto未安装或获取信息失败
        """
        if not HAS_PYWINAUTO:
            raise RuntimeError("pywinauto未安装")
        
        try:
            app = Application().connect(handle=window_handle)
            window = app.top_window()
            rect = window.rectangle()
            
            info = {
                "title": window.window_text(),
                "handle": window_handle,
                "left": rect.left,
                "top": rect.top,
                "width": rect.width(),
                "height": rect.height(),
                "center_x": rect.left + rect.width() // 2,
                "center_y": rect.top + rect.height() // 2
            }
            
            print(f"[WindowManager] 窗口信息: {info['title']} "
                  f"({info['width']}x{info['height']} @ {info['left']},{info['top']})")
            
            return info
            
        except Exception as e:
            raise RuntimeError(f"获取窗口信息失败: {str(e)}")
    
    @staticmethod
    def find_and_activate(app_names: List[str], wait_time: float = 0.5) -> Tuple[int, Any, Dict[str, Any]]:
        """
        查找并激活窗口的便捷方法
        
        Args:
            app_names: 应用名称列表
            wait_time: 激活后等待时间
        
        Returns:
            (window_handle, window_object, window_info) 元组
        
        Example:
            >>> handle, window, info = WindowManager.find_and_activate(["微信", "WeChat"])
            >>> print(f"窗口标题: {info['title']}, 大小: {info['width']}x{info['height']}")
        """
        print(f"[WindowManager] 查找并激活窗口...")
        
        # 1. 查找窗口
        window_handle = WindowManager.find_window_by_names(app_names)
        
        # 2. 激活窗口
        window = WindowManager.activate_window(window_handle, wait_time)
        
        # 3. 获取窗口信息
        info = WindowManager.get_window_info(window_handle)
        
        print(f"[WindowManager] [OK] Complete: Window activated and info retrieved")
        
        return window_handle, window, info


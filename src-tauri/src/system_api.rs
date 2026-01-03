/*!
系统 API 模块 - 提供系统级功能接口
包括：光标跟踪、应用检测、截图、文本输入等功能
这些方法会被暴露给 Python 插件使用
*/

use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::sync::{Arc, Mutex, OnceLock};
use std::collections::HashMap;

#[cfg(target_os = "windows")]
use winapi::um::{
    winuser::{GetCursorPos, WindowFromPoint, GetWindowTextW, GetWindowThreadProcessId},
    handleapi::CloseHandle,
    tlhelp32::{CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W, TH32CS_SNAPPROCESS},
};

/// 光标和应用信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CursorAppInfo {
    pub cursor_x: i32,
    pub cursor_y: i32,
    pub app_name: String,
    pub window_title: String,
    pub process_id: u32,
    pub timestamp: u64,
}

/// 截图信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScreenshotInfo {
    pub app_name: String,
    pub window_title: String,
    pub data: String, // Base64 编码的图片数据
    pub width: u32,
    pub height: u32,
    pub timestamp: u64,
}

/// 系统 API 管理器
pub struct SystemApiManager {
    current_cursor_info: Arc<Mutex<Option<CursorAppInfo>>>,
    #[allow(dead_code)]
    screenshot_cache: Arc<Mutex<HashMap<String, ScreenshotInfo>>>,
}

impl SystemApiManager {
    pub fn new() -> Self {
        Self {
            current_cursor_info: Arc::new(Mutex::new(None)),
            screenshot_cache: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// 记录当前光标位置和应用信息
    pub fn record_cursor_app_info(&self) -> Result<CursorAppInfo> {
        let info = self.get_cursor_app_info()?;
        
        // 存储当前信息
        {
            let mut current = self.current_cursor_info.lock().unwrap();
            *current = Some(info.clone());
        }
        
        println!("📍 Recorded cursor info: {} at ({}, {})", info.app_name, info.cursor_x, info.cursor_y);
        Ok(info)
    }

    /// 获取当前光标位置和应用信息
    pub fn get_cursor_app_info(&self) -> Result<CursorAppInfo> {
        #[cfg(target_os = "windows")]
        {
            self.get_cursor_app_info_windows()
        }
        #[cfg(not(target_os = "windows"))]
        {
            // 其他平台的实现
            Ok(CursorAppInfo {
                cursor_x: 0,
                cursor_y: 0,
                app_name: "Unknown".to_string(),
                window_title: "Unknown".to_string(),
                process_id: 0,
                timestamp: std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_secs(),
            })
        }
    }

    #[cfg(target_os = "windows")]
    fn get_cursor_app_info_windows(&self) -> Result<CursorAppInfo> {
        use winapi::shared::windef::POINT;
        use winapi::um::winuser::GetForegroundWindow;
        
        unsafe {
            // 获取光标位置
            let mut cursor_pos = POINT { x: 0, y: 0 };
            if GetCursorPos(&mut cursor_pos) == 0 {
                return Err(anyhow::anyhow!("Failed to get cursor position"));
            }

            // 获取前台焦点窗口（而不是光标位置的窗口）
            // 这样可以准确获取用户正在使用的应用
            let hwnd = GetForegroundWindow();
            if hwnd.is_null() {
                return Err(anyhow::anyhow!("No foreground window found"));
            }

            // 获取窗口标题
            let mut window_title = vec![0u16; 256];
            let title_len = GetWindowTextW(hwnd, window_title.as_mut_ptr(), window_title.len() as i32);
            let window_title = if title_len > 0 {
                String::from_utf16_lossy(&window_title[..title_len as usize])
            } else {
                "Unknown Window".to_string()
            };

            // 获取进程 ID
            let mut process_id = 0u32;
            GetWindowThreadProcessId(hwnd, &mut process_id);

            // 获取进程名称
            let mut app_name = self.get_process_name_by_id(process_id)
                .unwrap_or_else(|_| "Unknown Process".to_string());
            
            // 移除.exe后缀，方便Python服务匹配
            if app_name.to_lowercase().ends_with(".exe") {
                app_name = app_name[..app_name.len() - 4].to_string();
            }

            println!("📱 获取前台应用: {} (窗口标题: {}, PID: {})", app_name, window_title, process_id);

            Ok(CursorAppInfo {
                cursor_x: cursor_pos.x,
                cursor_y: cursor_pos.y,
                app_name,
                window_title,
                process_id,
                timestamp: std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_secs(),
            })
        }
    }

    #[cfg(target_os = "windows")]
    fn get_process_name_by_id(&self, process_id: u32) -> Result<String> {
        use winapi::um::handleapi::INVALID_HANDLE_VALUE;
        
        unsafe {
            let snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
            if snapshot == INVALID_HANDLE_VALUE {
                return Err(anyhow::anyhow!("Failed to create process snapshot"));
            }

            let mut process_entry = PROCESSENTRY32W {
                dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
                cntUsage: 0,
                th32ProcessID: 0,
                th32DefaultHeapID: 0,
                th32ModuleID: 0,
                cntThreads: 0,
                th32ParentProcessID: 0,
                pcPriClassBase: 0,
                dwFlags: 0,
                szExeFile: [0; 260],
            };

            if Process32FirstW(snapshot, &mut process_entry) != 0 {
                loop {
                    if process_entry.th32ProcessID == process_id {
                        let exe_name = String::from_utf16_lossy(
                            &process_entry.szExeFile[..process_entry.szExeFile.iter().position(|&x| x == 0).unwrap_or(260)]
                        );
                        CloseHandle(snapshot);
                        return Ok(exe_name);
                    }

                    if Process32NextW(snapshot, &mut process_entry) == 0 {
                        break;
                    }
                }
            }

            CloseHandle(snapshot);
            Err(anyhow::anyhow!("Process not found"))
        }
    }

    /// 获取存储的光标应用信息
    #[allow(dead_code)]
    pub fn get_stored_cursor_info(&self) -> Option<CursorAppInfo> {
        self.current_cursor_info.lock().unwrap().clone()
    }

    /// 对指定应用进行截图
    #[allow(dead_code)]
    pub fn capture_app_screenshot(&self, app_name: &str) -> Result<ScreenshotInfo> {
        // 首先尝试从缓存获取
        {
            let cache = self.screenshot_cache.lock().unwrap();
            if let Some(cached) = cache.get(app_name) {
                // 如果缓存时间不超过 5 秒，直接返回
                let now = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_secs();
                if now - cached.timestamp < 5 {
                    return Ok(cached.clone());
                }
            }
        }

        // 执行实际截图
        let screenshot = self.capture_app_screenshot_impl(app_name)?;
        
        // 更新缓存
        {
            let mut cache = self.screenshot_cache.lock().unwrap();
            cache.insert(app_name.to_string(), screenshot.clone());
        }

        println!("📸 Captured screenshot for app: {}", app_name);
        Ok(screenshot)
    }

    #[allow(dead_code)]
    fn capture_app_screenshot_impl(&self, app_name: &str) -> Result<ScreenshotInfo> {
        #[cfg(target_os = "windows")]
        {
            self.capture_app_screenshot_windows(app_name)
        }
        #[cfg(not(target_os = "windows"))]
        {
            // 其他平台的实现
            Ok(ScreenshotInfo {
                app_name: app_name.to_string(),
                window_title: "Unknown".to_string(),
                data: "".to_string(),
                width: 0,
                height: 0,
                timestamp: std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_secs(),
            })
        }
    }

    #[cfg(target_os = "windows")]
    #[allow(dead_code)]
    fn capture_app_screenshot_windows(&self, app_name: &str) -> Result<ScreenshotInfo> {
        use winapi::um::{
            winuser::{GetDC, ReleaseDC, GetWindowTextW},
            wingdi::{CreateCompatibleDC, CreateCompatibleBitmap, SelectObject, BitBlt, SRCCOPY, GetDIBits, BITMAPINFOHEADER, BITMAPINFO, DIB_RGB_COLORS},
        };
        use winapi::shared::windef::RECT;

        unsafe {
            // 查找窗口（这里简化处理，实际应该遍历所有窗口找到匹配的进程）
            let hwnd = self.find_window_by_process_name(app_name)?;
            
            // 获取窗口标题
            let mut window_title = vec![0u16; 256];
            let title_len = GetWindowTextW(hwnd, window_title.as_mut_ptr(), window_title.len() as i32);
            let window_title = if title_len > 0 {
                String::from_utf16_lossy(&window_title[..title_len as usize])
            } else {
                "Unknown Window".to_string()
            };

            // 获取窗口矩形
            let mut rect = RECT { left: 0, top: 0, right: 0, bottom: 0 };
            if winapi::um::winuser::GetWindowRect(hwnd, &mut rect) == 0 {
                return Err(anyhow::anyhow!("Failed to get window rect"));
            }

            let width = (rect.right - rect.left) as u32;
            let height = (rect.bottom - rect.top) as u32;

            // 获取窗口 DC
            let hdc = GetDC(hwnd);
            if hdc.is_null() {
                return Err(anyhow::anyhow!("Failed to get window DC"));
            }

            // 创建兼容 DC 和位图
            let mem_dc = CreateCompatibleDC(hdc);
            let bitmap = CreateCompatibleBitmap(hdc, width as i32, height as i32);
            let old_bitmap = SelectObject(mem_dc, bitmap as *mut _);

            // 复制窗口内容到位图
            BitBlt(mem_dc, 0, 0, width as i32, height as i32, hdc, 0, 0, SRCCOPY);

            // 获取位图数据
            let mut bmi = BITMAPINFO {
                bmiHeader: BITMAPINFOHEADER {
                    biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
                    biWidth: width as i32,
                    biHeight: -(height as i32), // 负值表示自上而下
                    biPlanes: 1,
                    biBitCount: 32,
                    biCompression: 0,
                    biSizeImage: 0,
                    biXPelsPerMeter: 0,
                    biYPelsPerMeter: 0,
                    biClrUsed: 0,
                    biClrImportant: 0,
                },
                bmiColors: [winapi::um::wingdi::RGBQUAD { rgbBlue: 0, rgbGreen: 0, rgbRed: 0, rgbReserved: 0 }; 1],
            };

            let mut buffer = vec![0u8; (width * height * 4) as usize];
            GetDIBits(mem_dc, bitmap as *mut _, 0, height, buffer.as_mut_ptr() as *mut _, &mut bmi, DIB_RGB_COLORS);

            // 转换为 PNG 并编码为 base64
            let base64_data = self.convert_to_base64_png(&buffer, width, height)?;

            // 清理资源
            SelectObject(mem_dc, old_bitmap);
            winapi::um::wingdi::DeleteObject(bitmap as *mut _);
            winapi::um::wingdi::DeleteDC(mem_dc);
            ReleaseDC(hwnd, hdc);

            Ok(ScreenshotInfo {
                app_name: app_name.to_string(),
                window_title,
                data: base64_data,
                width,
                height,
                timestamp: std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_secs(),
            })
        }
    }

    #[cfg(target_os = "windows")]
    #[allow(dead_code)]
    fn find_window_by_process_name(&self, _process_name: &str) -> Result<winapi::shared::windef::HWND> {
        // 这里应该实现遍历所有窗口，找到匹配进程名的窗口
        // 暂时返回桌面窗口作为示例
        unsafe {
            let hwnd = winapi::um::winuser::GetDesktopWindow();
            if hwnd.is_null() {
                Err(anyhow::anyhow!("Failed to find window"))
            } else {
                Ok(hwnd)
            }
        }
    }

    #[allow(dead_code)]
    fn convert_to_base64_png(&self, buffer: &[u8], _width: u32, _height: u32) -> Result<String> {
        // 这里应该将 BGRA 数据转换为 PNG 格式并编码为 base64
        // 暂时返回空字符串
        use base64::{Engine as _, engine::general_purpose};
        
        // 简化处理：直接对原始数据进行 base64 编码
        // 实际应用中应该使用 image crate 转换为 PNG
        let encoded = general_purpose::STANDARD.encode(buffer);
        Ok(encoded)
    }

    /// 向指定应用输入文本
    #[allow(dead_code)]
    pub fn input_text_to_app(&self, app_name: &str, text: &str) -> Result<bool> {
        println!("📝 Inputting text to {}: {}", app_name, text);
        
        #[cfg(target_os = "windows")]
        {
            self.input_text_windows(app_name, text)
        }
        #[cfg(not(target_os = "windows"))]
        {
            Ok(true)
        }
    }

    #[cfg(target_os = "windows")]
    #[allow(dead_code)]
    fn input_text_windows(&self, app_name: &str, text: &str) -> Result<bool> {
        use winapi::um::winuser::{SetForegroundWindow, SendMessageW, WM_CHAR};
        
        unsafe {
            // 找到目标窗口
            let hwnd = self.find_window_by_process_name(app_name)?;
            
            // 将窗口置于前台
            SetForegroundWindow(hwnd);
            
            // 发送文本字符
            for ch in text.chars() {
                SendMessageW(hwnd, WM_CHAR, ch as usize, 0);
                std::thread::sleep(std::time::Duration::from_millis(10));
            }
            
            // 发送回车键
            SendMessageW(hwnd, WM_CHAR, 13, 0); // 13 是回车键的 ASCII 码
            
            Ok(true)
        }
    }

    /// 清理截图缓存
    #[allow(dead_code)]
    pub fn clear_screenshot_cache(&self) {
        let mut cache = self.screenshot_cache.lock().unwrap();
        cache.clear();
        println!("🗑️ Screenshot cache cleared");
    }

    /// 获取系统信息
    #[allow(dead_code)]
    pub fn get_system_info(&self) -> HashMap<String, String> {
        let mut info = HashMap::new();
        info.insert("os".to_string(), std::env::consts::OS.to_string());
        info.insert("arch".to_string(), std::env::consts::ARCH.to_string());
        info.insert("family".to_string(), std::env::consts::FAMILY.to_string());
        info
    }
}

// 全局系统 API 管理器
static SYSTEM_API_MANAGER: OnceLock<Arc<SystemApiManager>> = OnceLock::new();

/// 初始化系统 API 管理器
pub fn initialize_system_api() {
    SYSTEM_API_MANAGER.get_or_init(|| Arc::new(SystemApiManager::new()));
}

/// 获取系统 API 管理器
pub fn get_system_api() -> Result<Arc<SystemApiManager>> {
    SYSTEM_API_MANAGER.get()
        .ok_or_else(|| anyhow::anyhow!("System API not initialized"))
        .map(|arc| arc.clone())
}

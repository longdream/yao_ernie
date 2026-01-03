use std::sync::{Arc, Mutex};
use enigo::{Enigo, Key, Keyboard, Settings};
use tauri::Emitter;

// 全局光标位置存储
pub static CURSOR_POSITION: std::sync::OnceLock<Arc<Mutex<Option<(i32, i32)>>>> = std::sync::OnceLock::new();

// 全局应用句柄存储
pub static APP_HANDLE: std::sync::OnceLock<Arc<Mutex<Option<tauri::AppHandle>>>> = std::sync::OnceLock::new();

#[cfg(target_os = "windows")]
use windows::Win32::UI::WindowsAndMessaging::{
    GetCursorPos, SetWindowsHookExW, CallNextHookEx, WH_MOUSE_LL, WM_LBUTTONDOWN, 
    GetSystemMetrics, SM_CXSCREEN, SM_CYSCREEN, SetCursorPos
};
#[cfg(target_os = "windows")]
use windows::Win32::Foundation::{POINT, WPARAM, LPARAM, LRESULT, HINSTANCE};
#[cfg(target_os = "windows")]
use windows::Win32::UI::Input::KeyboardAndMouse::{VK_CONTROL, VK_LCONTROL, VK_RCONTROL, VK_RETURN, GetAsyncKeyState, SendInput, INPUT, INPUT_MOUSE, INPUT_KEYBOARD, MOUSEINPUT, KEYBDINPUT, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, KEYEVENTF_KEYUP};
#[cfg(target_os = "windows")]
use windows::Win32::System::LibraryLoader::GetModuleHandleW;

use crate::window::show_main_window_with_context;

// 设置鼠标光标位置
#[cfg(target_os = "windows")]
pub fn set_cursor_position(x: i32, y: i32) -> Result<(), String> {
    unsafe {
        if SetCursorPos(x, y).is_ok() {
            Ok(())
        } else {
            Err("Failed to set cursor position".to_string())
        }
    }
}

#[cfg(not(target_os = "windows"))]
pub fn set_cursor_position(_x: i32, _y: i32) -> Result<(), String> {
    Err("Cursor position setting not supported on this platform".to_string())
}

// 在指定位置点击鼠标
#[cfg(target_os = "windows")]
pub fn click_at_position(x: i32, y: i32) -> Result<(), String> {
    unsafe {
        // 设置光标位置
        SetCursorPos(x, y).map_err(|e| format!("Failed to set cursor position: {}", e))?;
        
        // 创建鼠标按下事件
        let input_down = INPUT {
            r#type: INPUT_MOUSE,
            Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                mi: MOUSEINPUT {
                    dx: 0,
                    dy: 0,
                    mouseData: 0,
                    dwFlags: MOUSEEVENTF_LEFTDOWN,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        };
        
        // 创建鼠标释放事件
        let input_up = INPUT {
            r#type: INPUT_MOUSE,
            Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                mi: MOUSEINPUT {
                    dx: 0,
                    dy: 0,
                    mouseData: 0,
                    dwFlags: MOUSEEVENTF_LEFTUP,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        };
        
        // 发送按下事件
        SendInput(&[input_down], std::mem::size_of::<INPUT>() as i32);
        // 短暂延迟
        std::thread::sleep(std::time::Duration::from_millis(10));
        // 发送释放事件
        SendInput(&[input_up], std::mem::size_of::<INPUT>() as i32);
        
        Ok(())
    }
}

#[cfg(not(target_os = "windows"))]
pub fn click_at_position(_x: i32, _y: i32) -> Result<(), String> {
    Err("Mouse clicking not supported on this platform".to_string())
}

// Windows鼠标钩子回调函数
#[cfg(target_os = "windows")]
unsafe extern "system" fn mouse_hook_proc(n_code: i32, w_param: WPARAM, l_param: LPARAM) -> LRESULT {
    if n_code >= 0 {
        // 获取当前鼠标位置
        let mut cursor_pos = POINT { x: 0, y: 0 };
        let _ = GetCursorPos(&mut cursor_pos);
        let current_pos = (cursor_pos.x, cursor_pos.y);
        
        // 检查修饰键状态（严格检查左右Ctrl键）
        // 分别检查左Ctrl和右Ctrl，避免VK_CONTROL的模糊判断
        let left_ctrl = GetAsyncKeyState(VK_LCONTROL.0 as i32);
        let right_ctrl = GetAsyncKeyState(VK_RCONTROL.0 as i32);
        
        // 只检查高位（0x8000）：键当前是否被按下
        let left_ctrl_pressed = (left_ctrl as u16 & 0x8000) != 0;
        let right_ctrl_pressed = (right_ctrl as u16 & 0x8000) != 0;
        let ctrl_pressed = left_ctrl_pressed || right_ctrl_pressed;
        
        match w_param.0 as u32 {
            // 左键按下 - 检查修饰键
            WM_LBUTTONDOWN => {
                // Ctrl+左键 - 快速输入（更严格的检查）
                if ctrl_pressed {
                    println!("🎯 Ctrl+Left Click detected! (left={}, right={})", left_ctrl_pressed, right_ctrl_pressed);
                    
                    println!("📍 Mouse position: ({}, {})", current_pos.0, current_pos.1);
                    
                    // 存储光标位置
                    let cursor_pos_storage = CURSOR_POSITION.get_or_init(|| Arc::new(Mutex::new(None)));
                    if let Ok(mut pos) = cursor_pos_storage.lock() {
                        *pos = Some(current_pos);
                    }
                    
                    // 记录光标位置和应用信息，获取应用上下文
                    let (app_name, window_title) = if let Ok(system_api) = crate::system_api::get_system_api() {
                        match system_api.record_cursor_app_info() {
                            Ok(info) => (info.app_name.clone(), info.window_title.clone()),
                            Err(e) => {
                                println!("⚠️ Failed to record cursor app info: {}", e);
                                ("Unknown".to_string(), "Unknown".to_string())
                            }
                        }
                    } else {
                        ("Unknown".to_string(), "Unknown".to_string())
                    };
                    
                    let cursor_x = current_pos.0;
                    let cursor_y = current_pos.1;
                    
                    // 获取应用句柄并显示主窗口（带上下文）
                    if let Some(app_handle_storage) = APP_HANDLE.get() {
                        if let Ok(app_handle_opt) = app_handle_storage.lock() {
                            if let Some(app_handle) = app_handle_opt.as_ref() {
                                let app_clone = app_handle.clone();
                                let app_name_clone = app_name.clone();
                                let window_title_clone = window_title.clone();
                                tauri::async_runtime::spawn(async move {
                                    println!("📝 Starting to show main window with context from mouse hook...");
                                    if let Err(e) = show_main_window_with_context(
                                        app_clone,
                                        app_name_clone,
                                        window_title_clone,
                                        cursor_x,
                                        cursor_y
                                    ).await {
                                        eprintln!("❌ Failed to show main window: {}", e);
                                    } else {
                                        println!("✅ Main window shown successfully with context");
                                    }
                                });
                            }
                        }
                    }
                    
                    // 阻止默认的鼠标点击行为，防止误操作
                    return LRESULT(1);
                }
            }
            
            _ => {}
        }
    }
    
    CallNextHookEx(None, n_code, w_param, l_param)
}

// 设置全局鼠标钩子
#[cfg(target_os = "windows")]
pub fn setup_mouse_hook() -> Result<(), String> {
    unsafe {
        let h_instance = GetModuleHandleW(None).map_err(|e| format!("Failed to get module handle: {}", e))?;
        let hook = SetWindowsHookExW(
            WH_MOUSE_LL,
            Some(mouse_hook_proc),
            HINSTANCE(h_instance.0),
            0
        ).map_err(|e| format!("Failed to set mouse hook: {}", e))?;
        
        if hook.is_invalid() {
            return Err("Failed to install mouse hook".to_string());
        }
        
        println!("✅ Global mouse hook installed successfully");
        Ok(())
    }
}

#[cfg(not(target_os = "windows"))]
pub fn setup_mouse_hook() -> Result<(), String> {
    Err("Mouse hook not supported on this platform".to_string())
}

// 计算智能窗口位置
#[cfg(target_os = "windows")]
pub fn calculate_smart_position(mouse_x: i32, mouse_y: i32, window_width: i32, window_height: i32) -> Result<(i32, i32), String> {
    unsafe {
        let screen_width = GetSystemMetrics(SM_CXSCREEN);
        let screen_height = GetSystemMetrics(SM_CYSCREEN);
        
        println!("📐 Screen size: {}x{}, Mouse: ({}, {}), Window: {}x{}", 
                 screen_width, screen_height, mouse_x, mouse_y, window_width, window_height);
        
        let margin = 20; // 边距
        let mut x = mouse_x + margin; // 默认显示在鼠标右边
        let mut y = mouse_y - (window_height / 2); // 垂直居中
        
        // 检查右边界，如果超出则显示在左边
        if x + window_width > screen_width - margin {
            x = mouse_x - window_width - margin;
            println!("🔄 Adjusted to left side due to right boundary");
        }
        
        // 检查左边界
        if x < margin {
            x = margin;
            println!("🔄 Adjusted to margin due to left boundary");
        }
        
        // 检查下边界，如果超出则显示在上面
        if y + window_height > screen_height - margin {
            y = mouse_y - window_height - margin;
            println!("🔄 Adjusted to top due to bottom boundary");
        }
        
        // 检查上边界
        if y < margin {
            y = margin;
            println!("🔄 Adjusted to margin due to top boundary");
        }
        
        println!("✅ Final position: ({}, {})", x, y);
        Ok((x, y))
    }
}

#[cfg(not(target_os = "windows"))]
pub fn calculate_smart_position(mouse_x: i32, mouse_y: i32, window_width: i32, window_height: i32) -> Result<(i32, i32), String> {
    // 非Windows平台的简单实现
    let margin = 20;
    let x = mouse_x + margin;
    let y = mouse_y - (window_height / 2);
    Ok((x, y))
}

#[tauri::command]
pub async fn simulate_text_input(text: String) -> Result<(), String> {
    println!("🔤 Starting text input simulation: {}", text);
    
    // 短暂延迟确保窗口隐藏完成
    tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    
    // 获取记录的光标位置
    let cursor_pos = CURSOR_POSITION.get_or_init(|| Arc::new(Mutex::new(None)));
    let saved_position = if let Ok(pos) = cursor_pos.lock() {
        *pos
    } else {
        None
    };
    
    // 如果有保存的光标位置，先设置到该位置并点击
    if let Some((x, y)) = saved_position {
        println!("🎯 Moving cursor to saved position: ({}, {})", x, y);
        if let Err(e) = set_cursor_position(x, y) {
            println!("⚠️ Failed to set cursor position: {}", e);
        }
        
        // 点击一下确保焦点和激活文本输入位置
        println!("🖱️ Clicking at cursor position to activate");
        if let Err(e) = click_at_position(x, y) {
            println!("⚠️ Failed to click at position: {}", e);
        }
        
        // 等待点击生效
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
    } else {
        println!("⚠️ No saved cursor position found");
    }
    
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| e.to_string())?;
    
    // 逐字符输入，支持中文
    for char in text.chars() {
        if char == '\n' {
            enigo.key(Key::Return, enigo::Direction::Click).map_err(|e| e.to_string())?;
        } else {
            enigo.text(&char.to_string()).map_err(|e| e.to_string())?;
        }
        // 短暂延迟模拟自然打字
        tokio::time::sleep(std::time::Duration::from_millis(30)).await;
    }
    
    println!("✅ Text input simulation completed");
    Ok(())
}

#[tauri::command]
pub async fn simulate_key_press(key: String) -> Result<(), String> {
    println!("⌨️ Simulating key press: {}", key);
    
    // 短暂延迟确保准备就绪
    tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    
    let vk_code = match key.as_str() {
        "Return" | "Enter" => VK_RETURN.0,
        _ => {
            return Err(format!("Unsupported key: {}", key));
        }
    };
    
    unsafe {
        // 按下键
        let input_down = INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: windows::Win32::UI::Input::KeyboardAndMouse::VIRTUAL_KEY(vk_code),
                    wScan: 0,
                    dwFlags: windows::Win32::UI::Input::KeyboardAndMouse::KEYBD_EVENT_FLAGS(0),
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        };
        
        // 释放键
        let input_up = INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: windows::Win32::UI::Input::KeyboardAndMouse::VIRTUAL_KEY(vk_code),
                    wScan: 0,
                    dwFlags: KEYEVENTF_KEYUP,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        };
        
        // 发送按下事件
        SendInput(&[input_down], std::mem::size_of::<INPUT>() as i32);
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
        
        // 发送释放事件
        SendInput(&[input_up], std::mem::size_of::<INPUT>() as i32);
    }
    
    println!("✅ Key press simulation completed");
    Ok(())
}

#[tauri::command]
pub async fn register_global_shortcut(_app: tauri::AppHandle) -> Result<(), String> {
    // 全局快捷键已在 setup 中注册，这个命令主要用于前端确认注册状态
    Ok(())
}

pub fn setup_global_shortcuts(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    use tauri_plugin_global_shortcut::GlobalShortcutExt;
    
    // 设置全局截图快捷键 (Ctrl+Alt+A)
    println!("⌨️ Setting up global screenshot shortcut...");
    let app_handle_for_shortcut = app.handle().clone();
    if let Err(e) = app.global_shortcut().register("Ctrl+Alt+A") {
        println!("⚠️ Failed to register screenshot shortcut: {}", e);
    } else {
        println!("✅ Screenshot shortcut (Ctrl+Alt+A) registered successfully");
        
        // 监听快捷键事件
        let app_clone = app_handle_for_shortcut.clone();
        let _ = app.global_shortcut().on_shortcut("Ctrl+Alt+A", move |_, _, _| {
            println!("📸 Screenshot shortcut triggered!");
            let app_inner = app_clone.clone();
            tauri::async_runtime::spawn(async move {
                // 发送快捷键事件到前端
                if let Err(e) = app_inner.emit("shortcut", "Ctrl+Alt+A") {
                    println!("❌ Failed to emit shortcut event: {}", e);
                }
            });
        });
    }
    
    Ok(())
}

pub fn initialize_app_handle(app_handle: tauri::AppHandle) {
    let app_handle_storage = APP_HANDLE.get_or_init(|| Arc::new(Mutex::new(None)));
    if let Ok(mut handle) = app_handle_storage.lock() {
        *handle = Some(app_handle);
    }
}

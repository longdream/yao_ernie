use xcap::Monitor;
use base64::{Engine as _, engine::general_purpose};
use image::ImageFormat;
use tauri::Emitter;
use std::sync::{Arc, Mutex, OnceLock};

use crate::system::APP_HANDLE;

// 全局变量保存截图前的窗口可见状态 (main_visible, quick_visible)
static WINDOW_VISIBILITY_STATE: OnceLock<Arc<Mutex<(bool, bool)>>> = OnceLock::new();

#[derive(Debug)]
pub struct ScreenshotData {
    pub base64_data: String,
    #[allow(dead_code)]
    pub width: u32,
    #[allow(dead_code)]
    pub height: u32,
}

pub async fn capture_full_screen() -> Result<ScreenshotData, String> {
    println!("📸 Capturing full screen...");
    
    // 获取主显示器
    let monitors = Monitor::all().map_err(|e| format!("Failed to get monitors: {}", e))?;
    let primary_monitor = monitors.into_iter().next().ok_or("No monitor found")?;
    
    println!("🖥️ Monitor info: {}x{}", primary_monitor.width(), primary_monitor.height());
    
    // 截取屏幕
    let image = primary_monitor.capture_image().map_err(|e| format!("Failed to capture screen: {}", e))?;
    
    // 保存图像尺寸信息
    let image_width = image.width();
    let image_height = image.height();
    
    // 转换为DynamicImage然后转为RGB（JPEG不支持透明度）
    let dynamic_image = image::DynamicImage::ImageRgba8(image);
    let rgb_image = dynamic_image.to_rgb8();
    
    // 转换为JPEG字节数据（更小的文件大小）
    let mut jpeg_data = Vec::new();
    {
        use std::io::Cursor;
        let mut cursor = Cursor::new(&mut jpeg_data);
        rgb_image.write_to(&mut cursor, ImageFormat::Jpeg)
            .map_err(|e| format!("Failed to encode JPEG: {}", e))?;
    }
    
    // 转换为base64
    let base64_data = general_purpose::STANDARD.encode(&jpeg_data);
    
    println!("✅ Screenshot captured: {}x{}, size: {} bytes", 
             image_width, image_height, jpeg_data.len());
    
    Ok(ScreenshotData {
        base64_data,
        width: image_width,
        height: image_height,
    })
}

#[tauri::command]
pub async fn start_screenshot() -> Result<(), String> {
    println!("🖼️ Starting system screenshot...");
    
    // 获取应用句柄
    if let Some(app_handle_storage) = APP_HANDLE.get() {
        if let Ok(app_handle_opt) = app_handle_storage.lock() {
            if let Some(app_handle) = app_handle_opt.as_ref() {
                let app_clone = app_handle.clone();
                
                // 异步执行截图
                tauri::async_runtime::spawn(async move {
                    // 1. 首先记录当前主窗口的状态
                    let main_window_state = save_main_window_state(&app_clone).await;
                    
                    // 2. 截取屏幕（先截图，再隐藏窗口）
                    match capture_full_screen().await {
                        Ok(screenshot_data) => {
                            println!("✅ Screenshot captured, creating independent overlay window");
                            
                            // 3. 创建独立的全屏截图窗口
                            match create_independent_screenshot_window(&app_clone, &screenshot_data).await {
                                Ok(_) => {
                                    println!("✅ Screenshot window created successfully");
                                    // 4. 截图窗口创建成功后才隐藏主窗口
                                    hide_all_app_windows(&app_clone).await;
                                }
                                Err(e) => {
                                    println!("❌ Failed to create screenshot window: {}", e);
                                    // 如果创建窗口失败，恢复主窗口
                                    restore_main_window_state(&app_clone, main_window_state).await;
                                }
                            }
                        }
                        Err(e) => {
                            println!("❌ Screenshot failed: {}", e);
                            // 截图失败，不隐藏主窗口
                        }
                    }
                });
            }
        }
    }
    
    Ok(())
}

async fn hide_all_app_windows(app: &tauri::AppHandle) {
    use tauri::Manager;
    
    // 保存窗口可见状态
    let main_visible = if let Some(window) = app.get_webview_window("main") {
        window.is_visible().unwrap_or(false)
    } else {
        false
    };
    
    // 保存状态到全局变量 (second value is unused, kept for compatibility)
    let state_storage = WINDOW_VISIBILITY_STATE.get_or_init(|| Arc::new(Mutex::new((false, false))));
    if let Ok(mut state) = state_storage.lock() {
        *state = (main_visible, false);
        println!("💾 Saved window visibility state: main={}", main_visible);
    }
    
    // 隐藏主窗口
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
        println!("🙈 Hidden main window");
    }
}

async fn restore_app_windows(app: &tauri::AppHandle) {
    use tauri::Manager;
    
    // 从全局变量获取保存的窗口可见状态
    let state_storage = WINDOW_VISIBILITY_STATE.get_or_init(|| Arc::new(Mutex::new((false, false))));
    let (main_was_visible, _) = if let Ok(state) = state_storage.lock() {
        *state
    } else {
        (false, false)
    };
    
    println!("🔍 Restoring windows based on saved state: main={}", main_was_visible);
    
    // 只恢复之前可见的窗口
    if main_was_visible {
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.show();
            println!("👁️ Restored main window");
        }
    }
}

#[derive(Debug, Clone)]
struct WindowState {
    position: (f64, f64),
    size: (f64, f64),
    is_maximized: bool,
    is_visible: bool,
}

async fn save_main_window_state(app: &tauri::AppHandle) -> Option<WindowState> {
    use tauri::Manager;
    
    if let Some(window) = app.get_webview_window("main") {
        let position = window.outer_position().ok()?.to_logical(1.0);
        let size = window.outer_size().ok()?.to_logical(1.0);
        let is_maximized = window.is_maximized().unwrap_or(false);
        let is_visible = window.is_visible().unwrap_or(true);
        
        println!("💾 Saved window state: pos({:.0}, {:.0}), size({:.0}, {:.0}), max: {}, visible: {}", 
                position.x, position.y, size.width, size.height, is_maximized, is_visible);
        
        Some(WindowState {
            position: (position.x, position.y),
            size: (size.width, size.height),
            is_maximized,
            is_visible,
        })
    } else {
        None
    }
}

async fn restore_main_window_state(app: &tauri::AppHandle, state: Option<WindowState>) {
    use tauri::Manager;
    
    if let Some(window) = app.get_webview_window("main") {
        if let Some(state) = state {
            println!("🔄 Restoring window state: pos({:.0}, {:.0}), size({:.0}, {:.0})", 
                    state.position.0, state.position.1, state.size.0, state.size.1);
            
            // 恢复窗口位置和大小
            let _ = window.set_position(tauri::Position::Logical(tauri::LogicalPosition::new(
                state.position.0, state.position.1
            )));
            let _ = window.set_size(tauri::Size::Logical(tauri::LogicalSize::new(
                state.size.0, state.size.1
            )));
            
            // 恢复最大化状态
            if state.is_maximized {
                let _ = window.maximize();
            } else {
                let _ = window.unmaximize();
            }
            
            // 恢复可见性
            if state.is_visible {
                let _ = window.show();
            }
        } else {
            // 如果没有保存的状态，只是简单显示窗口
            let _ = window.show();
        }
        
        println!("✅ Main window state restored");
    }
}

async fn create_independent_screenshot_window(app: &tauri::AppHandle, screenshot_data: &ScreenshotData) -> Result<(), String> {
    
    println!("🖼️ Creating independent fullscreen screenshot window...");
    
    // 获取主显示器信息
    let monitors = xcap::Monitor::all().map_err(|e| format!("Failed to get monitors: {}", e))?;
    let primary_monitor = monitors.into_iter().next().ok_or("No monitor found")?;
    
    println!("🖥️ Monitor: {}x{} at ({}, {})", 
            primary_monitor.width(), primary_monitor.height(), 
            primary_monitor.x(), primary_monitor.y());
    
    // 创建内嵌截图数据的HTML内容
    let html_content = format!(r#"
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Screenshot</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            width: 100vw;
            height: 100vh;
            overflow: hidden;
            cursor: crosshair;
            user-select: none;
            background: #000;
            position: relative;
            /* 优化渲染性能 */
            will-change: transform;
            transform: translateZ(0);
        }}
        
        #screenshot {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
            /* 优化图片渲染 */
            image-rendering: -webkit-optimize-contrast;
            image-rendering: crisp-edges;
            backface-visibility: hidden;
            transform: translateZ(0);
        }}
        
        .selection-area {{
            position: absolute;
            border: 2px solid #007acc;
            background: rgba(0, 122, 204, 0.1);
            pointer-events: none;
            z-index: 10;
            /* 优化选择区域性能 */
            will-change: transform, width, height;
            transform: translateZ(0);
        }}
        
        .overlay {{
            position: absolute;
            background: rgba(0, 0, 0, 0.3);
            pointer-events: none;
            z-index: 5;
        }}
        
        .buttons {{
            position: absolute;
            display: none;
            gap: 8px;
            z-index: 20;
            background: white;
            padding: 8px;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }}
        
        .buttons.show {{
            display: flex;
        }}
        
        .btn {{
            width: 40px;
            height: 40px;
            border: 1px solid #d1d5db;
            border-radius: 50%;
            cursor: pointer;
            font-size: 16px;
            font-weight: 500;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .btn-confirm {{
            background: #374151;
            color: white;
            border: 1px solid #374151;
        }}
        
        .btn-confirm:hover {{
            background: #1f2937;
            border-color: #1f2937;
        }}
        
        .btn-confirm.loading {{
            background: #6b7280;
            border-color: #6b7280;
            cursor: not-allowed;
        }}
        
        .loading-spinner {{
            width: 16px;
            height: 16px;
            border: 2px solid transparent;
            border-top: 2px solid white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }}
        
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        
        .btn-cancel {{
            background: white;
            color: #6b7280;
            border: 1px solid #d1d5db;
        }}
        
        .btn-cancel:hover {{
            background: #f9fafb;
        }}
    </style>
</head>
<body>
    <img id="screenshot" src="data:image/jpeg;base64,{}" alt="Screenshot">
    
    <div class="buttons" id="buttons">
        <button class="btn btn-confirm" onclick="confirmSelection()" title="确认">✓</button>
        <button class="btn btn-cancel" onclick="cancelSelection()" title="取消">✕</button>
    </div>

    <script>
        let isSelecting = false;
        let startX = 0, startY = 0;
        let currentX = 0, currentY = 0;
        let selectionDiv = null;
        
        console.log('📸 Screenshot window initialized');
        
        const img = document.getElementById('screenshot');
        
        img.onload = function() {{
            console.log('✅ Screenshot image loaded successfully');
            console.log('📏 Image dimensions:', img.naturalWidth, 'x', img.naturalHeight);
            
            // 通知前端截图页面已准备好
            window.location.href = 'screenshot-action://ready';
        }};
        
        img.onerror = function() {{
            console.error('❌ Failed to load screenshot image');
            alert('截图加载失败');
        }};
        
        document.addEventListener('mousedown', function(e) {{
            if (e.target.classList.contains('btn')) return;
            
            isSelecting = true;
            startX = e.clientX;
            startY = e.clientY;
            currentX = startX;
            currentY = startY;
            
            console.log('🖱️ Selection started at:', startX, startY);
            
            if (selectionDiv) {{
                selectionDiv.remove();
            }}
            
            selectionDiv = document.createElement('div');
            selectionDiv.className = 'selection-area';
            document.body.appendChild(selectionDiv);
            
            e.preventDefault();
        }});
        
        document.addEventListener('mousemove', function(e) {{
            if (!isSelecting) return;
            
            currentX = e.clientX;
            currentY = e.clientY;
            
            const left = Math.min(startX, currentX);
            const top = Math.min(startY, currentY);
            const width = Math.abs(currentX - startX);
            const height = Math.abs(currentY - startY);
            
            if (selectionDiv) {{
                selectionDiv.style.left = left + 'px';
                selectionDiv.style.top = top + 'px';
                selectionDiv.style.width = width + 'px';
                selectionDiv.style.height = height + 'px';
            }}
        }});
        
        document.addEventListener('mouseup', function(e) {{
            if (!isSelecting) return;
            
            isSelecting = false;
            
            const left = Math.min(startX, currentX);
            const top = Math.min(startY, currentY);
            const width = Math.abs(currentX - startX);
            const height = Math.abs(currentY - startY);
            
            console.log('📐 Selection area:', left, top, width, height);
            
            if (width < 3 || height < 3) {{
                console.log('⚠️ Selection too small, removing');
                if (selectionDiv) {{
                    selectionDiv.remove();
                    selectionDiv = null;
                }}
                hideButtons();
            }} else {{
                showButtons(left, top, width, height);
            }}
        }});
        
        function showButtons(selectionLeft, selectionTop, selectionWidth, selectionHeight) {{
            const buttonsDiv = document.getElementById('buttons');
            buttonsDiv.classList.add('show');
            
            // 将按钮放在选择区域的右下角，但确保不超出屏幕
            let buttonLeft = selectionLeft + selectionWidth + 10;
            let buttonTop = selectionTop + selectionHeight + 10;
            
            // 如果按钮会超出屏幕右边，放到选择区域左边
            if (buttonLeft + 120 > window.innerWidth) {{
                buttonLeft = selectionLeft - 120 - 10;
            }}
            
            // 如果按钮会超出屏幕底部，放到选择区域上方
            if (buttonTop + 60 > window.innerHeight) {{
                buttonTop = selectionTop - 60 - 10;
            }}
            
            // 确保按钮不会超出屏幕边界
            buttonLeft = Math.max(10, Math.min(buttonLeft, window.innerWidth - 120));
            buttonTop = Math.max(10, Math.min(buttonTop, window.innerHeight - 60));
            
            buttonsDiv.style.left = buttonLeft + 'px';
            buttonsDiv.style.top = buttonTop + 'px';
        }}
        
        function hideButtons() {{
            const buttonsDiv = document.getElementById('buttons');
            buttonsDiv.classList.remove('show');
        }}
        
        let isConfirming = false;
        
        function confirmSelection() {{
            if (!selectionDiv) {{
                alert('请先选择截图区域');
                return;
            }}
            
            if (isConfirming) {{
                console.log('⚠️ Already confirming, ignoring click');
                return;
            }}
            
            isConfirming = true;
            
            // 显示loading状态
            const confirmBtn = document.querySelector('.btn-confirm');
            confirmBtn.classList.add('loading');
            confirmBtn.innerHTML = '<div class="loading-spinner"></div>';
            confirmBtn.disabled = true;
            
            const rect = selectionDiv.getBoundingClientRect();
            const imgRect = img.getBoundingClientRect();
            
            // 计算相对于图片的坐标
            const scaleX = img.naturalWidth / imgRect.width;
            const scaleY = img.naturalHeight / imgRect.height;
            
            const x = Math.round((rect.left - imgRect.left) * scaleX);
            const y = Math.round((rect.top - imgRect.top) * scaleY);
            const width = Math.round(rect.width * scaleX);
            const height = Math.round(rect.height * scaleY);
            
            console.log('✅ Confirming selection:', x, y, width, height);
            
            // 通过URL参数传递选择区域信息，然后关闭窗口
            const params = new URLSearchParams({{
                action: 'confirm',
                x: x,
                y: y,
                width: width,
                height: height
            }});
            
            // 使用window.location来触发导航，这样可以被Rust端捕获
            window.location.href = 'screenshot-action://confirm?' + params.toString();
        }}
        
        
        function cancelSelection() {{
            console.log('❌ Screenshot cancelled');
            window.location.href = 'screenshot-action://cancel';
        }}
        
        // 键盘快捷键
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                cancelSelection();
            }} else if (e.key === 'Enter') {{
                confirmSelection();
            }}
        }});
    </script>
</body>
</html>
"#, screenshot_data.base64_data);

    println!("🔗 Creating window with embedded HTML content");
    
    let app_clone = app.clone();
    let window = tauri::WebviewWindowBuilder::new(
        app,
        "screenshot-overlay",
        tauri::WebviewUrl::External(format!("data:text/html;charset=utf-8,{}", 
            urlencoding::encode(&html_content)).parse().unwrap())
    )
    .title("Screenshot")
    .fullscreen(true)  // 全屏模式
    .decorations(false)  // 无边框
    .transparent(false)  // 不透明，显示截图内容
    .always_on_top(true)
    .resizable(true)
    .focused(true)
    .visible(true)
    .skip_taskbar(true)  // 不在任务栏显示
    .on_navigation(move |url| {
        println!("🔗 Navigation to: {}", url);
        
        if url.scheme() == "screenshot-action" {
            let _app_handle = app_clone.clone();
            
            match url.host_str() {
                Some("ready") => {
                    println!("🎯 Screenshot page ready, notifying frontend");
                    // 发送截图页面准备就绪事件
                    if let Some(app_handle_storage) = crate::system::APP_HANDLE.get() {
                        if let Ok(app_handle_opt) = app_handle_storage.lock() {
                            if let Some(app_handle) = app_handle_opt.as_ref() {
                                let ready_event = serde_json::json!({
                                    "ready": true
                                });
                                let _ = app_handle.emit("screenshot-ready", &ready_event);
                                println!("✅ Screenshot ready event sent");
                            }
                        }
                    }
                }
                Some("confirm") => {
                    println!("✅ Confirm action detected");
                    if let Some(query) = url.query() {
                        if let Ok(params) = serde_urlencoded::from_str::<std::collections::HashMap<String, String>>(query) {
                            if let (Some(x), Some(y), Some(width), Some(height)) = (
                                params.get("x").and_then(|s| s.parse::<u32>().ok()),
                                params.get("y").and_then(|s| s.parse::<u32>().ok()),
                                params.get("width").and_then(|s| s.parse::<u32>().ok()),
                                params.get("height").and_then(|s| s.parse::<u32>().ok()),
                            ) {
                                println!("📐 Selection: x={}, y={}, width={}, height={}", x, y, width, height);
                                
                                // 异步处理截图保存
                                tauri::async_runtime::spawn(async move {
                                    match save_screenshot_area(x, y, width, height).await {
                                        Ok(image_data) => {
                                            println!("✅ Screenshot saved successfully");
                                            
                                            // 直接发送事件，只发送一次到全局
                                            if let Some(app_handle_storage) = crate::system::APP_HANDLE.get() {
                                                if let Ok(app_handle_opt) = app_handle_storage.lock() {
                                                    if let Some(app_handle) = app_handle_opt.as_ref() {
                                                        let screenshot_event = serde_json::json!({
                                                            "success": true,
                                                            "imageData": image_data,
                                                            "width": 0,
                                                            "height": 0
                                                        });
                                                        
                                                        // 只发送一次全局事件，让所有窗口都能收到
                                                        println!("📤 Sending screenshot event globally...");
                                                        if let Err(e) = app_handle.emit("screenshot-captured", &screenshot_event) {
                                                            println!("⚠️ Failed to send screenshot globally: {}", e);
                                                        } else {
                                                            println!("✅ Screenshot event sent globally successfully");
                                                        }
                                                    }
                                                }
                                            }
                                            
                                            // 关闭截图窗口
                                            if let Err(e) = close_screenshot_window().await {
                                                println!("❌ Failed to close window: {}", e);
                                            }
                                        }
                                        Err(e) => {
                                            println!("❌ Failed to save screenshot: {}", e);
                                            if let Err(e) = close_screenshot_window().await {
                                                println!("❌ Failed to close window: {}", e);
                                            }
                                        }
                                    }
                                });
                            }
                        }
                    }
                }
                Some("copy") => {
                    println!("📋 Copy action detected");
                    if let Some(query) = url.query() {
                        if let Ok(params) = serde_urlencoded::from_str::<std::collections::HashMap<String, String>>(query) {
                            if let (Some(x), Some(y), Some(width), Some(height)) = (
                                params.get("x").and_then(|s| s.parse::<u32>().ok()),
                                params.get("y").and_then(|s| s.parse::<u32>().ok()),
                                params.get("width").and_then(|s| s.parse::<u32>().ok()),
                                params.get("height").and_then(|s| s.parse::<u32>().ok()),
                            ) {
                                println!("📋 Copying: x={}, y={}, width={}, height={}", x, y, width, height);
                                
                                // 异步处理截图复制
                                tauri::async_runtime::spawn(async move {
                                    match save_screenshot_area(x, y, width, height).await {
                                        Ok(_image_data) => {
                                            println!("📋 Screenshot copied to clipboard");
                                            // TODO: 实际复制到剪贴板的逻辑
                                        }
                                        Err(e) => {
                                            println!("❌ Failed to copy screenshot: {}", e);
                                        }
                                    }
                                });
                            }
                        }
                    }
                }
                Some("cancel") => {
                    println!("❌ Cancel action detected");
                    tauri::async_runtime::spawn(async move {
                        if let Err(e) = close_screenshot_window().await {
                            println!("❌ Failed to close window: {}", e);
                        }
                    });
                }
                _ => {
                    println!("⚠️ Unknown action: {}", url);
                }
            }
            
            // 阻止导航
            false
        } else {
            // 允许其他导航
            true
        }
    })
    .build();
    
    match window {
        Ok(window) => {
            println!("✅ Screenshot window created successfully");
            
            // 确保窗口可见
            if let Err(e) = window.show() {
                println!("⚠️ Failed to show window: {}", e);
            }
            
            // 尝试将窗口置于前台
            if let Err(e) = window.set_focus() {
                println!("⚠️ Failed to focus window: {}", e);
            }
            
            println!("✅ Independent screenshot window setup completed");
            Ok(())
        }
        Err(e) => {
            println!("❌ Failed to create screenshot window: {}", e);
            // 如果窗口创建失败，恢复主窗口
            restore_app_windows(app).await;
            Err(format!("Failed to create screenshot window: {}", e))
        }
    }
}

#[tauri::command]
pub async fn save_screenshot_area(
    x: u32,
    y: u32,
    width: u32,
    height: u32
) -> Result<String, String> {
    println!("💾 Saving screenshot area: x={}, y={}, width={}, height={}", x, y, width, height);
    
    // 重新捕获全屏截图
    let screenshot_data = capture_full_screen()
        .await
        .map_err(|e| format!("Failed to capture screen: {}", e))?;
    
    // 解码base64图片数据
    let image_bytes = general_purpose::STANDARD
        .decode(&screenshot_data.base64_data)
        .map_err(|e| format!("Failed to decode base64: {}", e))?;
    
    // 加载图片
    let img = image::load_from_memory(&image_bytes)
        .map_err(|e| format!("Failed to load image: {}", e))?;
    
    // 裁剪图片
    let cropped = img.crop_imm(x, y, width, height);
    
    // 转换为PNG字节数组
    let mut output = Vec::new();
    {
        use std::io::Cursor;
        let mut cursor = Cursor::new(&mut output);
        cropped.write_to(&mut cursor, ImageFormat::Png)
            .map_err(|e| format!("Failed to write PNG: {}", e))?;
    }
    
    // 编码为base64，并添加data URL前缀
    let base64_result = format!("data:image/png;base64,{}", general_purpose::STANDARD.encode(&output));
    
    println!("✅ Screenshot area saved, size: {} bytes", output.len());
    Ok(base64_result)
}

// send_screenshot_to_main 函数已删除 - 现在直接在URL导航处理中发送事件

#[tauri::command]
pub async fn close_screenshot_window() -> Result<(), String> {
    println!("🔒 Closing screenshot window...");
    
    if let Some(app_handle_storage) = APP_HANDLE.get() {
        let app_handle = {
            if let Ok(app_handle_opt) = app_handle_storage.lock() {
                app_handle_opt.clone()
            } else {
                None
            }
        };
        
        if let Some(app_handle) = app_handle {
            use tauri::Manager;
            
            // 关闭截图窗口
            if let Some(window) = app_handle.get_webview_window("screenshot-overlay") {
                let _ = window.close();
                println!("🗑️ Screenshot overlay window closed");
            }
            
            // 恢复应用窗口
            restore_app_windows(&app_handle).await;
        }
    }
    
    Ok(())
}

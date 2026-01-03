use tauri::Manager;
use tauri::Emitter;

/// Show main window and emit context-invoked event with app context
pub async fn show_main_window_with_context(app: tauri::AppHandle, app_name: String, window_title: String, cursor_x: i32, cursor_y: i32) -> Result<(), String> {
    println!("🔍 show_main_window_with_context called");
    println!("📱 App: {}, Window: {}, Cursor: ({}, {})", app_name, window_title, cursor_x, cursor_y);
    
    if let Some(window) = app.get_webview_window("main") {
        // Show and focus the main window
        window.show().map_err(|e| e.to_string())?;
        window.set_focus().map_err(|e| e.to_string())?;
        window.unminimize().map_err(|e| e.to_string())?;
        
        // Emit context-invoked event to the frontend
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;
        
        let payload = serde_json::json!({
            "app_name": app_name,
            "window_title": window_title,
            "cursor_x": cursor_x,
            "cursor_y": cursor_y,
            "timestamp": timestamp
        });
        
        if let Err(e) = app.emit("context-invoked", payload) {
            println!("⚠️ Failed to emit context-invoked event: {}", e);
        } else {
            println!("✅ Emitted context-invoked event");
        }
        
        println!("🎉 show_main_window_with_context completed successfully");
    } else {
        return Err("Main window not found".to_string());
    }
    
    Ok(())
}

#[tauri::command]
pub async fn show_main_window(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        window.show().map_err(|e| e.to_string())?;
        window.set_focus().map_err(|e| e.to_string())?;
        window.unminimize().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub async fn hide_main_window(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        window.hide().map_err(|e| e.to_string())?;
    }
    Ok(())
}

pub fn setup_window_events(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    use tauri::Manager;
    
    // 设置主窗口关闭事件处理
    if let Some(main_window) = app.get_webview_window("main") {
        let app_handle = app.handle().clone();
        main_window.on_window_event(move |event| {
            match event {
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    println!("🔒 Main window close requested, hiding to tray instead");
                    // 阻止窗口关闭
                    api.prevent_close();
                    // 隐藏窗口到托盘
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.hide();
                        println!("🙈 Main window hidden to tray");
                    }
                }
                _ => {}
            }
        });
        println!("✅ Main window close event handler set up");
    }
    
    Ok(())
}

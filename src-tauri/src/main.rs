// 注释掉这行以启用F12开发者工具和控制台（即使在生产环境）
// #![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// 导入所有模块
mod api;
mod config;
mod screenshot;
mod system;
mod tray;
mod window;
mod agentic;
mod system_api;
// api_simple_agent removed - using python_agent_commands instead
// python_interface removed - using HTTP API instead

// 导入需要的函数
use api::*;
use screenshot::*;
use system::*;
use tray::*;
use window::*;
use agentic::initialize_agent_manager;
// Python Agent commands are imported via agentic module
use tauri::Manager;


#[tokio::main]
async fn main() {
  tauri::Builder::default()
    .plugin(tauri_plugin_store::Builder::new().build())
    .plugin(tauri_plugin_process::init())
    .plugin(tauri_plugin_shell::init())
    .plugin(tauri_plugin_fs::init())
    .plugin(tauri_plugin_global_shortcut::Builder::new().build())
    // Legacy agent manager removed - using HTTP-based agent manager
    .setup(|app| {
      println!("🚀 Setting up application...");
      
            // 初始化应用句柄
            initialize_app_handle(app.handle().clone());
      
      // 设置全局鼠标钩子 (Ctrl+鼠标左键)
      println!("🖱️ Setting up global mouse hook for Ctrl+Left Click...");
      match setup_mouse_hook() {
        Ok(_) => println!("✅ Global mouse hook set up successfully"),
        Err(e) => {
          println!("⚠️ Failed to set up mouse hook: {}", e);
          println!("⚠️ Ctrl+Left Click functionality will not be available");
        }
      }

            // 设置全局快捷键
            setup_global_shortcuts(app)?;
      
      // 设置系统托盘
      println!("🖥️ Setting up system tray...");
            setup_system_tray(app)?;
      
      // 设置窗口关闭事件处理
      setup_window_events(app)?;
      
      // 初始化Agentic系统（异步，不阻塞启动）
      println!("🤖 Initializing Agentic system...");
      let _app_handle = app.handle().clone();
      let window = app.get_webview_window("main").expect("Failed to get main window");
      tauri::async_runtime::spawn(async move {

        // 初始化系统 API
        crate::system_api::initialize_system_api();
        println!("✅ System API initialized successfully");

        // 初始化 Agent 管理器 (HTTP-based) - 保持向后兼容
        if let Err(e) = crate::agentic::initialize_agent_manager(window.clone()).await {
          println!("⚠️ Failed to initialize agent manager: {}", e);
          println!("⚠️ Agent functionality will be limited until Python service is available");
          
          // 即使初始化失败，也创建一个基础的Agent管理器，避免浮动输入框报错
          let basic_manager = crate::agentic::AgentManager::new();
          let manager_arc = std::sync::Arc::new(tokio::sync::Mutex::new(basic_manager));
          let _ = crate::agentic::set_global_agent_manager(manager_arc);
        } else {
          println!("✅ Agent manager initialized successfully");
        }

        
        // Embedding模型现在在Python服务中处理
        println!("📝 Embedding functionality handled by Python service");
        
        println!("🎯 Agentic system initialization completed");
      });
      
      println!("🎉 Application setup completed successfully");
      Ok(())
    })
    .invoke_handler(tauri::generate_handler![
            // API handlers
      proxy_models,
      proxy_chat_stream,
      proxy_chat,
      get_log_path,
      write_log_line,
      get_config_path,
      get_conversations_path,
      start_chat_stream,
      shell_open,
            // System handlers
      simulate_text_input,
      simulate_key_press,
            register_global_shortcut,
            // Window handlers
      show_main_window,
      hide_main_window,
            // Screenshot handlers
            start_screenshot,
            save_screenshot_area,
            close_screenshot_window,
            // Agent HTTP Service handlers
            agent_execute,
            agent_chat,
            agent_chat_stream,
            agent_take_screenshot,
            agent_input_text,
            agent_get_active_window,
            agent_health_check,
            agent_service_start,
            agent_service_stop,
            agent_service_status,
            update_python_service_config,
            // System API handlers
            get_cursor_app_info,
            // Agent Plugin handlers (removed - using HTTP service)
    ])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}

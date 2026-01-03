use anyhow::Result;
use reqwest::Client;
use serde::Deserialize;
use std::io::Write as _;
use tauri::{Window, WebviewWindow, Emitter, Manager};
use std::process::Command;

use crate::config::{AppConfig, Message};

/// 获取项目根目录，在开发模式下处理 src-tauri 目录问题
fn get_project_root() -> std::path::PathBuf {
    let current_dir = std::env::current_dir().unwrap();
    // 如果当前目录是 src-tauri，需要回到上级目录
    if current_dir.file_name().unwrap_or_default() == "src-tauri" {
        current_dir.parent().unwrap().to_path_buf()
    } else {
        current_dir
    }
}

#[tauri::command]
pub async fn proxy_models(config: AppConfig) -> Result<String, String> {
    let client = Client::new();
    let url = format!("{}/v1/models", config.base_url.trim_end_matches('/'));
    let mut req = client.get(url);
    if let Some(k) = config.api_key {
        req = req.bearer_auth(k);
    }
    let resp = req.send().await.map_err(|e| e.to_string())?;
    let v: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;
    let list = v.get("data").and_then(|m| m.as_array()).map(|arr| {
        arr.iter()
            .filter_map(|m| m.get("id").and_then(|n| n.as_str()).map(|s| s.to_string()))
            .collect::<Vec<String>>()
    }).unwrap_or_default();
    let result = serde_json::to_string(&list).map_err(|e| e.to_string())?;
    Ok(result)
}

#[tauri::command]
pub async fn proxy_chat_stream(body: String) -> Result<String, String> {
    // Return the body handle string back for processing
    Ok(body)
}

#[tauri::command]
pub async fn proxy_chat(handle: String) -> Result<String, String> {
    #[derive(Deserialize)]
    struct InBody { config: AppConfig, messages: Vec<Message>, model: String, #[serde(default)] think: bool }
    let parsed: InBody = serde_json::from_str(&handle).map_err(|e| e.to_string())?;
    chat_once(parsed.config, parsed.messages, parsed.model, parsed.think).await.map_err(|e| e.to_string())
}

pub async fn chat_once(config: AppConfig, messages: Vec<Message>, model: String, _think: bool) -> Result<String> {
    eprintln!("[DEBUG] chat_once called with config: provider={}, baseUrl={}, apiKey={:?}", 
        config.provider, config.base_url, config.api_key.as_ref().map(|k| format!("{}...", &k[..std::cmp::min(8, k.len())])));
    
    let client = Client::new();
    let url = format!("{}/chat/completions", config.base_url.trim_end_matches('/'));
    eprintln!("[DEBUG] OpenAI API URL: {}", url);
    
    // 转换消息格式以支持图片
    let api_messages: Vec<serde_json::Value> = messages.iter().map(|msg| {
        if let Some(images) = &msg.images {
            if !images.is_empty() {
                // 有图片的消息，使用Vision API格式
                let mut content_parts = vec![
                    serde_json::json!({
                        "type": "text",
                        "text": msg.content
                    })
                ];
                
                // 添加图片内容
                for image in images {
                    content_parts.push(serde_json::json!({
                        "type": "image_url",
                        "image_url": {
                            "url": format!("data:{};base64,{}", image.mime_type, image.base64)
                        }
                    }));
                }
                
                serde_json::json!({
                    "role": msg.role,
                    "content": content_parts
                })
            } else {
                // 无图片，使用普通格式
                serde_json::json!({
                    "role": msg.role,
                    "content": msg.content
                })
            }
        } else {
            // 无图片，使用普通格式
            serde_json::json!({
                "role": msg.role,
                "content": msg.content
            })
        }
    }).collect();
    
    let body = serde_json::json!({
        "model": model,
        "messages": api_messages,
        "stream": false,
        "temperature": config.temperature.unwrap_or(0.6)
    });
    eprintln!("[DEBUG] Request body: {}", serde_json::to_string_pretty(&body).unwrap_or_default());
    let mut req = client.post(url)
        .header("Content-Type", "application/json")
        .header("User-Agent", "Yao/1.0")
        .json(&body);
    if let Some(k) = &config.api_key {
        if !k.is_empty() {
            eprintln!("[DEBUG] Using API key: {}...", &k[..std::cmp::min(8, k.len())]);
            req = req.bearer_auth(k);
        } else {
            eprintln!("[DEBUG] API key is empty");
        }
    } else {
        eprintln!("[DEBUG] No API key provided");
    }
    let resp = req.send().await?;
    let status = resp.status();
    let text = resp.text().await?;
    eprintln!("[DEBUG] Response status: {}", status);
    eprintln!("[DEBUG] Response body: {}", text);
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) {
        if let Some(content) = v
            .get("choices")
            .and_then(|c| c.get(0))
            .and_then(|c| c.get("message"))
            .and_then(|m| m.get("content"))
            .and_then(|c| c.as_str())
        {
            return Ok(content.to_string());
        }
        if !status.is_success() {
            let err = v.get("error").and_then(|e| e.get("message")).and_then(|m| m.as_str()).unwrap_or(text.as_str());
            anyhow::bail!(err.to_string());
        }
    }
    anyhow::bail!(format!("openai empty response: status={} body={}", status, text))
}

#[tauri::command]
pub async fn get_log_path(_app: tauri::AppHandle) -> Result<String, String> {
    let log_dir = if cfg!(debug_assertions) {
        // 开发模式：使用项目根目录的logs文件夹
        let current_dir = std::env::current_dir().map_err(|e| e.to_string())?;
        current_dir.join("logs")
    } else {
        // 发布模式：优先使用exe同级目录
        if let Ok(exe) = std::env::current_exe() {
            if let Some(dir) = exe.parent() {
                dir.join("logs")
            } else {
                // Fallback to app data dir
                _app.path().app_local_data_dir().map_err(|e| e.to_string())?.join("logs")
            }
        } else {
            // Fallback to app data dir
            _app.path().app_local_data_dir().map_err(|e| e.to_string())?.join("logs")
        }
    };
    
    // 确保目录存在
    if let Err(e) = std::fs::create_dir_all(&log_dir) {
        eprintln!("Failed to create log directory: {}", e);
    }
    
    let log_file = log_dir.join("app.log");
    Ok(log_file.to_string_lossy().into_owned())
}

#[tauri::command]
pub async fn get_conversations_path(_app: tauri::AppHandle) -> Result<String, String> {
    let conversations_file = if cfg!(debug_assertions) {
        // 开发模式：使用项目根目录
        get_project_root().join("conversations.json")
    } else {
        // 发布模式：优先使用exe同级目录
        if let Ok(exe) = std::env::current_exe() {
            if let Some(dir) = exe.parent() {
                dir.join("conversations.json")
            } else {
                // Fallback to app data dir
                _app.path().app_local_data_dir().map_err(|e| e.to_string())?.join("conversations.json")
            }
        } else {
            // Fallback to app data dir
            _app.path().app_local_data_dir().map_err(|e| e.to_string())?.join("conversations.json")
        }
    };
    
    Ok(conversations_file.to_string_lossy().into_owned())
}

#[tauri::command]
pub async fn write_log_line(_app: tauri::AppHandle, line: String) -> Result<(), String> {
    let log_dir = if cfg!(debug_assertions) {
        // 开发模式：使用项目根目录的logs文件夹
        get_project_root().join("logs")
    } else {
        // 发布模式：使用exe同级目录
        let base = std::env::current_exe().map_err(|e| e.to_string())?;
        base.parent().ok_or("no parent")?.join("logs")
    };
    
    std::fs::create_dir_all(&log_dir).map_err(|e| e.to_string())?;
    let file = log_dir.join("app.log");
    let mut f = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(file)
        .map_err(|e| e.to_string())?;
    writeln!(f, "{}", line).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub async fn get_config_path(app: tauri::AppHandle) -> Result<String, String> {
    // 配置文件放在项目根目录的config文件夹（便于用户访问和修改）
    let config_dir = if cfg!(debug_assertions) {
        // 开发模式：使用项目根目录
        get_project_root().join("config")
    } else {
        // 发布模式：使用exe同级目录
        if let Ok(exe) = std::env::current_exe() {
            if let Some(dir) = exe.parent() {
                dir.join("config")
            } else {
                return Err("无法获取exe目录".to_string());
            }
        } else {
            return Err("无法获取当前exe路径".to_string());
        }
    };
    
    // 确保config目录存在
    if let Err(e) = std::fs::create_dir_all(&config_dir) {
        eprintln!("Failed to create config directory: {}", e);
        return Err(format!("创建配置目录失败: {}", e));
    }
    
    let config_file = config_dir.join("settings.json");
    
    // 检查是否需要从旧位置（AppData/Roaming）迁移配置文件
    if !config_file.exists() {
        if let Ok(old_config_dir) = app.path().app_config_dir() {
            let old_config_file = old_config_dir.join("settings.json");
            
            // 如果旧配置文件存在，复制到新位置
            if old_config_file.exists() {
                if let Err(e) = std::fs::copy(&old_config_file, &config_file) {
                    eprintln!("Failed to migrate config file: {}", e);
                } else {
                    println!("✅ Config file migrated from {:?} to {:?}", old_config_file, config_file);
                    println!("   配置文件已从AppData迁移到项目根目录，旧文件可以删除");
                }
            }
        }
    }
    
    Ok(config_file.to_string_lossy().into_owned())
}

#[tauri::command]
pub async fn shell_open(path: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("Failed to open path: {}", e))?;
    }
    
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("Failed to open path: {}", e))?;
    }
    
    #[cfg(target_os = "linux")]
    {
        Command::new("xdg-open")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("Failed to open path: {}", e))?;
    }
    
    Ok(())
}

#[tauri::command]
pub async fn start_chat_stream(window: Window, body: String) -> Result<String, String> {
    #[derive(Deserialize)]
    struct InBody { config: AppConfig, messages: Vec<Message>, model: String, #[serde(default)] think: bool }
    let parsed: InBody = serde_json::from_str(&body).map_err(|e| e.to_string())?;
    // simple unique id without external deps
    let millis = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_else(|_| std::time::Duration::from_millis(0))
        .as_millis();
    let stream_id = format!("stream-{}", millis);
    let sid = stream_id.clone();

    // log start
    if let Ok(_path) = get_log_path(window.app_handle().clone()).await {
        let _ = write_log_line(window.app_handle().clone(), format!(
            "[chat-start] id={} model={} think={} input={}",
            stream_id,
            parsed.model,
            parsed.think,
            parsed
                .messages
                .iter()
                .rev()
                .find(|m| m.role == "user")
                .map(|m| m.content.as_str())
                .unwrap_or("")
        ))
        .await;
    }

    // spawn task
    let win = window.clone();
    tauri::async_runtime::spawn(async move {
        match chat_once(parsed.config, parsed.messages.clone(), parsed.model.clone(), parsed.think).await {
            Ok(content) => {
                // emit chunks by characters batches of 8 for smoother UI
                let mut buf = String::new();
                for (i, ch) in content.chars().enumerate() {
                    buf.push(ch);
                    if buf.len() >= 8 || i == content.chars().count().saturating_sub(1) {
                        let _ = win.emit(&format!("chat-chunk:{}", sid), buf.clone());
                        buf.clear();
                    }
                }
                let _ = win.emit(&format!("chat-end:{}", sid), "");
                let _ = write_log_line(win.app_handle().clone(), format!(
                    "[chat-end] id={} output_len={}",
                    sid,
                    content.len()
                ))
                .await;
            }
            Err(err) => {
                let _ = win.emit(&format!("chat-error:{}", sid), err.to_string());
                let _ = write_log_line(win.app_handle().clone(), format!(
                    "[chat-error] id={} err={}",
                    sid,
                    err.to_string()
                ))
                .await;
            }
        }
    });

    Ok(stream_id)
}

// ============ Agent API 端点 ============

#[derive(serde::Deserialize)]
pub struct AgentExecuteRequestData {
    pub app_name: String,
    pub window_title: Option<String>,
    pub prompt: String,
    pub session_id: Option<String>,
}

#[tauri::command]
pub async fn agent_execute(request: AgentExecuteRequestData) -> Result<serde_json::Value, String> {
    use crate::agentic::get_agent_manager;

    println!("🎯 Tauri command: agent_execute called");
    let prompt_preview: String = request.prompt.chars().take(50).collect();
    println!("   App: {}, Prompt: {}, Session: {:?}", request.app_name, prompt_preview, request.session_id);

    // Align screenshot/input context with the Ctrl+LeftClick position:
    // We intercept the original click, so we re-apply a controlled click at the saved cursor position
    // before running agent execution (which may take screenshots of the target app).
    #[cfg(target_os = "windows")]
    {
        if let Some(storage) = crate::system::CURSOR_POSITION.get() {
            if let Ok(guard) = storage.lock() {
                if let Some((x, y)) = *guard {
                    if let Err(e) = crate::system::click_at_position(x, y) {
                        println!("⚠️ Failed to click at saved cursor position: {}", e);
                    } else {
                        println!("🖱️ Clicked at saved cursor position: ({}, {})", x, y);
                    }
                }
            }
        }
    }

    let manager_arc = get_agent_manager()
        .ok_or_else(|| "Agent manager not initialized".to_string())?;

    let manager = manager_arc.lock().await;

    let response = manager.agent_execute(
        request.app_name.clone(), 
        request.window_title.clone(),
        request.prompt.clone(),
        request.session_id.clone()
    ).await
        .map_err(|e| {
            eprintln!("❌ Agent execute error: {}", e);
            format!("Agent execute failed: {}", e)
        })?;

    println!("📦 Agent response received:");
    println!("   Success: {}", response.success);
    println!("   Result: {:?}", response.result);
    println!("   Error: {:?}", response.error);

    // 将响应转换为JSON
    let result = serde_json::json!({
        "success": response.success,
        "result": response.result,
        "reasoning": response.reasoning,
        "error": response.error
    });

    println!("🚀 Returning JSON to frontend: {}", serde_json::to_string(&result).unwrap_or_else(|_| "failed to serialize".to_string()));

    Ok(result)
}

#[tauri::command]
pub async fn agent_chat(message: String, agent_type: Option<String>) -> Result<String, String> {
    use crate::agentic::get_agent_manager;

    let manager_arc = get_agent_manager()
        .ok_or_else(|| "Agent manager not initialized".to_string())?;

    let manager = manager_arc.lock().await;

    let response = manager.chat(message, agent_type).await
        .map_err(|e| format!("Agent chat failed: {}", e))?;

    if response.success {
        Ok(response.message)
    } else {
        Err(response.error.unwrap_or_else(|| "Unknown agent error".to_string()))
    }
}

#[tauri::command]
pub async fn agent_chat_stream(
    window: Window,
    message: String, 
    agent_type: Option<String>
) -> Result<String, String> {
    use crate::agentic::get_agent_manager;
    use futures_util::StreamExt;
    use uuid::Uuid;

    let manager_arc = get_agent_manager()
        .ok_or_else(|| "Agent manager not initialized".to_string())?;

    let stream_id = Uuid::new_v4().to_string();

    // 启动异步任务处理流式响应
    let window_clone = window.clone();
    let stream_id_clone = stream_id.clone();
    let manager_arc_clone = manager_arc.clone();
    
    tokio::spawn(async move {
        // 获取响应，在锁内完成
        let response = {
            let manager = manager_arc_clone.lock().await;
            
            manager.chat_stream(message, agent_type).await
        };
        
        match response {
            Ok(response) => {
                let mut stream = response.bytes_stream();
                
                while let Some(chunk_result) = stream.next().await {
                    match chunk_result {
                        Ok(chunk) => {
                            if let Ok(text) = String::from_utf8(chunk.to_vec()) {
                                // 解析SSE格式的数据
                                for line in text.lines() {
                                    if line.starts_with("data: ") {
                                        let json_str = &line[6..]; // 去掉 "data: " 前缀
                                        if let Ok(data) = serde_json::from_str::<serde_json::Value>(json_str) {
                                            let _ = window_clone.emit("agent-stream", serde_json::json!({
                                                "id": stream_id_clone,
                                                "data": data
                                            }));
                                        }
                                    }
                                }
                            }
                        }
                        Err(e) => {
                            let _ = window_clone.emit("agent-stream-error", serde_json::json!({
                                "id": stream_id_clone,
                                "error": e.to_string()
                            }));
                            break;
                        }
                    }
                }

                // 发送流结束信号
                let _ = window_clone.emit("agent-stream-end", serde_json::json!({
                    "id": stream_id_clone
                }));
            }
            Err(e) => {
                let _ = window_clone.emit("agent-stream-error", serde_json::json!({
                    "id": stream_id_clone,
                    "error": e.to_string()
                }));
            }
        }
    });

    Ok(stream_id)
}

#[tauri::command]
pub async fn agent_take_screenshot(save_path: Option<String>) -> Result<String, String> {
    use crate::agentic::get_agent_manager;

    let manager_arc = get_agent_manager()
        .ok_or_else(|| "Agent manager not initialized".to_string())?;

    let manager = manager_arc.lock().await;

    let result = manager.take_screenshot(save_path).await
        .map_err(|e| format!("Screenshot failed: {}", e))?;

    Ok(serde_json::to_string(&result).unwrap_or_default())
}

#[tauri::command]
pub async fn agent_input_text(text: String, target_app: Option<String>) -> Result<String, String> {
    use crate::agentic::get_agent_manager;

    let manager_arc = get_agent_manager()
        .ok_or_else(|| "Agent manager not initialized".to_string())?;

    let manager = manager_arc.lock().await;

    let result = manager.input_text(text, target_app).await
        .map_err(|e| format!("Input text failed: {}", e))?;

    Ok(serde_json::to_string(&result).unwrap_or_default())
}

#[tauri::command]
pub async fn agent_get_active_window() -> Result<String, String> {
    use crate::agentic::get_agent_manager;

    let manager_arc = get_agent_manager()
        .ok_or_else(|| "Agent manager not initialized".to_string())?;

    let manager = manager_arc.lock().await;

    let result = manager.get_active_window().await
        .map_err(|e| format!("Get active window failed: {}", e))?;

    Ok(serde_json::to_string(&result).unwrap_or_default())
}

#[tauri::command]
pub async fn agent_health_check() -> Result<bool, String> {
    use crate::agentic::get_agent_manager;

    let manager_arc = get_agent_manager()
        .ok_or_else(|| "Agent manager not initialized".to_string())?;

    let manager = manager_arc.lock().await;

    Ok(manager.is_server_healthy().await)
}

#[tauri::command]
pub async fn agent_service_start(window: WebviewWindow) -> Result<bool, String> {
    use crate::agentic::{get_agent_manager, initialize_agent_manager};

    // 检查是否已经有管理器实例
    if let Some(manager_arc) = get_agent_manager() {
        let manager = manager_arc.lock().await;
        
        if manager.is_server_healthy().await {
            return Ok(true); // 服务已经在运行
        }
    }

    // 启动新的管理器
    match initialize_agent_manager(window).await {
        Ok(_) => Ok(true),
        Err(e) => Err(format!("Failed to start agent service: {}", e))
    }
}

#[tauri::command]
pub async fn agent_service_stop() -> Result<bool, String> {
    use crate::agentic::cleanup_agent_manager;

    match cleanup_agent_manager() {
        Ok(_) => Ok(true),
        Err(e) => Err(format!("Failed to stop agent service: {}", e))
    }
}

#[tauri::command]
pub async fn agent_service_status() -> Result<String, String> {
    use crate::agentic::get_agent_manager;

    if let Some(manager_arc) = get_agent_manager() {
        let manager = manager_arc.lock().await;
        
        if manager.is_server_healthy().await {
            Ok("running".to_string())
        } else {
            Ok("stopped".to_string())
        }
    } else {
        Ok("stopped".to_string())
    }
}

#[tauri::command]
pub async fn update_python_service_config(app: tauri::AppHandle) -> Result<(), String> {
    use crate::agentic::update_python_service_config;
    use crate::config::load_app_config;
    
    println!("🔄 Updating Python service configuration...");
    
    // 重新加载配置
    let config = load_app_config(app).await
        .map_err(|e| format!("Failed to load config: {}", e))?;
    
    // 发送配置到Python服务
    update_python_service_config(&config).await
        .map_err(|e| format!("Failed to update Python service config: {}", e))?;
    
    println!("✅ Python service configuration updated successfully");
    Ok(())
}

#[tauri::command]
pub fn get_cursor_app_info() -> Result<serde_json::Value, String> {
    use crate::system_api::get_system_api;
    
    let system_api = get_system_api()
        .map_err(|e| format!("System API not initialized: {}", e))?;
    
    if let Some(info) = system_api.get_stored_cursor_info() {
        serde_json::to_value(&info)
            .map_err(|e| format!("Failed to serialize cursor info: {}", e))
    } else {
        Err("No cursor info stored".to_string())
    }
}
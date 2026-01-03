use anyhow::Result;
use std::sync::Arc;
use tokio::sync::Mutex;
use tokio::time::{sleep, Duration};
use tauri::{WebviewWindow, Manager};
use serde_json;
use chrono;

use crate::agentic::http_client::{AgentHttpClient, ChatRequest, ChatResponse, ConfigResponse, AgentExecuteRequest, AgentExecuteResponse};
use crate::config::AppConfig;

// 全局Agent管理器 - 使用OnceLock避免静态可变引用警告
static GLOBAL_AGENT_MANAGER: std::sync::OnceLock<Arc<Mutex<AgentManager>>> = std::sync::OnceLock::new();

pub struct AgentManager {
    client: AgentHttpClient,
    #[allow(dead_code)]
    server_url: String,
}

impl AgentManager {
    pub fn new() -> Self {
        let server_url = "http://127.0.0.1:8765".to_string();
        let client = AgentHttpClient::new(server_url.clone());
        
        Self {
            client,
            server_url,
        }
    }

    /// 等待Python Agent服务器可用
    pub async fn wait_for_server_ready(&self) -> Result<()> {
        println!("⏳ Waiting for Python Agent server to be ready...");
        
        self.wait_for_server().await?;
        
        println!("✅ Python Agent server is ready");
        Ok(())
    }

    /// 等待服务器启动
    async fn wait_for_server(&self) -> Result<()> {
        let mut attempts = 0;
        let max_attempts = 60; // 增加到60秒超时

        while attempts < max_attempts {
            match self.client.health_check().await {
                Ok(health) => {
                    println!("🔍 Health check response: status={}", health.status);
                    // Python服务运行正常，无论是否已配置Agent都认为可用
                    if health.status == "healthy" || health.status == "waiting_for_config" {
                        return Ok(());
                    }
                }
                Err(e) => {
                    if attempts % 10 == 0 { // 每10秒打印一次错误
                        println!("⏳ Waiting for Python service... (attempt {}/{}): {}", attempts + 1, max_attempts, e);
                    }
                }
            }

            attempts += 1;
            sleep(Duration::from_secs(1)).await;
        }

        Err(anyhow::anyhow!("Python Agent server is not available after 60 seconds"))
    }

    /// 检查Python Agent服务器是否可用
    pub async fn is_server_available(&self) -> bool {
        self.client.health_check().await.is_ok()
    }

    /// 检查服务器状态（兼容旧接口）
    pub async fn is_server_healthy(&self) -> bool {
        self.is_server_available().await
    }

    /// 发送聊天消息
    pub async fn chat(&self, message: String, agent_type: Option<String>) -> Result<ChatResponse> {
        let request = ChatRequest {
            message,
            agent_type: agent_type.unwrap_or_else(|| "assistant".to_string()),
            stream: false,
            context: None,
        };

        self.client.chat(request).await
    }

    /// 流式聊天
    pub async fn chat_stream(&self, message: String, agent_type: Option<String>) -> Result<reqwest::Response> {
        let request = ChatRequest {
            message,
            agent_type: agent_type.unwrap_or_else(|| "assistant".to_string()),
            stream: true,
            context: None,
        };

        self.client.chat_stream(request).await
    }

    /// 截图
    pub async fn take_screenshot(&self, save_path: Option<String>) -> Result<serde_json::Value> {
        let response = self.client.take_screenshot(save_path).await?;
        
        if response.success {
            Ok(response.result.unwrap_or_default())
        } else {
            Err(anyhow::anyhow!("Screenshot failed: {}", 
                response.error.unwrap_or_else(|| "Unknown error".to_string())))
        }
    }

    /// 输入文本
    pub async fn input_text(&self, text: String, target_app: Option<String>) -> Result<serde_json::Value> {
        let response = self.client.input_text(text, target_app).await?;
        
        if response.success {
            Ok(response.result.unwrap_or_default())
        } else {
            Err(anyhow::anyhow!("Input text failed: {}", 
                response.error.unwrap_or_else(|| "Unknown error".to_string())))
        }
    }

    /// 获取活动窗口
    pub async fn get_active_window(&self) -> Result<serde_json::Value> {
        let response = self.client.get_active_window().await?;
        
        if response.success {
            Ok(response.result.unwrap_or_default())
        } else {
            Err(anyhow::anyhow!("Get active window failed: {}", 
                response.error.unwrap_or_else(|| "Unknown error".to_string())))
        }
    }

    /// 执行Agent任务
    pub async fn agent_execute(&self, app_name: String, window_title: Option<String>, prompt: String, session_id: Option<String>) -> Result<AgentExecuteResponse> {
        // 先检查服务是否可用
        match self.client.health_check().await {
            Ok(health) => {
                // 检查Agent是否已初始化（需要配置后才能执行任务）
                if health.status == "waiting_for_config" {
                    return Ok(AgentExecuteResponse {
                        success: false,
                        result: None,
                        reasoning: None,
                        error: Some("Python Agent服务等待配置中，请先完成模型配置".to_string()),
                        intent_type: None,
                        session_id: None,
                    });
                } else if health.status != "healthy" {
                    return Ok(AgentExecuteResponse {
                        success: false,
                        result: None,
                        reasoning: None,
                        error: Some("Python Agent服务状态异常，请检查服务是否正常运行".to_string()),
                        intent_type: None,
                        session_id: None,
                    });
                }
            }
            Err(_) => {
                return Ok(AgentExecuteResponse {
                    success: false,
                    result: None,
                    reasoning: None,
                    error: Some("无法连接到Python Agent服务，请确保服务已启动并运行在端口8765".to_string()),
                    intent_type: None,
                    session_id: None,
                });
            }
        }

        let request = AgentExecuteRequest {
            app_name: app_name.clone(),
            window_title,
            prompt: prompt.clone(),
            session_id,
        };
        
        println!("📡 AgentManager: Executing agent task for app: {}", app_name);
        let response = self.client.agent_execute(request).await?;
        println!("📡 AgentManager: Received response - success: {}, has result: {}", 
            response.success, response.result.is_some());
        
        if let Some(ref result) = response.result {
            let result_preview: String = result.chars().take(100).collect();
            println!("📡 AgentManager: Result content (first 100 chars): {}", result_preview);
        }
        
        Ok(response)
    }

    /// 初始化Agent系统 - 只创建HTTP客户端，不启动服务器
    pub async fn initialize(_config: &AppConfig) -> Result<Self> {
        let manager = Self::new();
        
        // 等待Python服务器可用（由start.bat启动）
        manager.wait_for_server_ready().await?;
        
        Ok(manager)
    }
}

// Drop实现不再需要，因为不管理Python服务器进程

/// 全局初始化函数，替代原来的initialize_plugin_manager
pub async fn initialize_agent_manager(window: WebviewWindow) -> Result<()> {
    println!("🤖 Initializing Agent Manager (HTTP-based)...");

    // 加载配置
    let app_handle = window.app_handle();
    let config = crate::config::load_app_config(app_handle.clone()).await?;

    // 打印加载的配置信息
    println!("📋 Loaded config from file: provider={}, base_url={}", 
        config.provider, config.base_url);

    // 创建并初始化Agent管理器
    let manager = AgentManager::initialize(&config).await?;

    // 存储到全局变量
    let manager_arc = Arc::new(Mutex::new(manager));
    let _ = GLOBAL_AGENT_MANAGER.set(manager_arc.clone());

    // 发送配置到Python服务
    println!("📤 Sending LLM configuration to Python service...");
    let manager_lock = manager_arc.lock().await;
    match manager_lock.update_python_config(&config).await {
        Ok(_) => {
            println!("🎯 LLM configuration successfully sent to Python service");
        }
        Err(e) => {
            println!("❌ Failed to send LLM configuration to Python service: {}", e);
            return Err(anyhow::anyhow!("Python service configuration failed, 主线零降级: {}", e));
        }
    }

    println!("✅ Agent Manager initialized successfully");
    Ok(())
}

/// 获取全局Agent管理器
pub fn get_agent_manager() -> Option<Arc<Mutex<AgentManager>>> {
    GLOBAL_AGENT_MANAGER.get().cloned()
}

/// 设置全局Agent管理器
pub fn set_global_agent_manager(manager: Arc<Mutex<AgentManager>>) -> Result<(), Arc<Mutex<AgentManager>>> {
    GLOBAL_AGENT_MANAGER.set(manager)
}

/// 清理全局Agent管理器 - 发送关闭信号给Python服务
pub fn cleanup_agent_manager() -> Result<()> {
    println!("🧹 Cleaning up Agent manager...");
    
    // 尝试优雅关闭Python服务
    if let Some(manager) = get_agent_manager() {
        println!("📡 Sending shutdown signal to Python service...");
        
        // 创建一个异步任务来发送关闭请求
        let rt = tokio::runtime::Runtime::new()?;
        let result = rt.block_on(async {
            if let Ok(manager_guard) = manager.try_lock() {
                // 尝试发送关闭请求到Python服务
                match manager_guard.client.health_check().await {
                    Ok(_) => {
                        println!("📡 Python service is running, sending shutdown signal...");
                        // 发送关闭信号
                        if let Err(e) = manager_guard.client.shutdown_service().await {
                            println!("⚠️ Error sending shutdown signal: {}", e);
                        }
                        true
                    }
                    Err(_) => {
                        println!("📡 Python service already stopped or not responding");
                        false
                    }
                }
            } else {
                false
            }
        });
        
        if result {
            println!("✅ Python service notified of shutdown");
        } else {
            println!("⚠️ Could not notify Python service (may already be stopped)");
        }
    } else {
        println!("⚠️ No agent manager instance found");
    }
    
    println!("🧹 Agent manager cleanup completed");
    Ok(())
}

impl AgentManager {
    /// 更新Python服务的LLM配置
    pub async fn update_python_config(&self, app_config: &AppConfig) -> Result<ConfigResponse> {
        // 主线零降级：所有必要配置都必须存在，不允许默认值
        
        // 检查基础配置是否存在
        if app_config.models.is_none() {
            return Err(anyhow::anyhow!("Missing required 'models' configuration in settings"));
        }
        
        let models = app_config.models.as_ref().unwrap();
        if models.is_empty() {
            return Err(anyhow::anyhow!("Empty 'models' configuration in settings"));
        }
        
        // 查找各类型模型配置
        let mut main_model: Option<String> = None;
        let mut main_api_base: Option<String> = None;
        let mut main_api_key: Option<String> = None;
        
        let mut advanced_model: Option<String> = None;
        let mut advanced_api_base: Option<String> = None;
        let mut advanced_api_key: Option<String> = None;
        
        let mut vl_model: Option<String> = None;
        let mut vl_api_base: Option<String> = None;
        let mut vl_api_key: Option<String> = None;
        
        let mut light_model: Option<String> = None;
        let mut light_api_base: Option<String> = None;
        let mut light_api_key: Option<String> = None;

        let mut embedding_model: Option<String> = None;
        let mut embedding_api_base: Option<String> = None;
        let mut embedding_api_key: Option<String> = None;

        // 从models配置中查找各类型模型
        println!("📋 Processing {} model configurations", models.len());
        
        for model in models {
            println!("🔍 Found model: {} (category: {:?})", model.name, model.category);
            
            match model.category.as_deref() {
                Some("light") => {
                    light_model = Some(model.name.clone());
                    light_api_base = Some(model.base_url.clone());
                    light_api_key = model.api_key.clone();
                    println!("✅ Light model configured: {}", model.name);
                },
                Some("advanced") => {
                    advanced_model = Some(model.name.clone());
                    advanced_api_base = Some(model.base_url.clone());
                    advanced_api_key = model.api_key.clone();
                    println!("✅ Advanced model configured: {}", model.name);
                },
                Some("vl") => {
                    vl_model = Some(model.name.clone());
                    vl_api_base = Some(model.base_url.clone());
                    vl_api_key = model.api_key.clone();
                    println!("✅ VL model configured: {}", model.name);
                },
                Some("embedding") => {
                    embedding_model = Some(model.name.clone());
                    embedding_api_base = Some(model.base_url.clone());
                    embedding_api_key = model.api_key.clone();
                    println!("✅ Embedding model configured: {}", model.name);
                },
                _ => {
                    println!("ℹ️ Model {} has no specific category, skipping", model.name);
                }
            }
        }
        
        // 如果配置中明确指定了特定模型，优先使用指定的模型
        if let Some(ref specified_advanced) = app_config.advanced_model {
            if let Some(model) = models.iter().find(|m| m.name == *specified_advanced) {
                advanced_model = Some(model.name.clone());
                advanced_api_base = Some(model.base_url.clone());
                advanced_api_key = model.api_key.clone();
                println!("🎯 Using specified advanced model: {}", model.name);
            } else {
                return Err(anyhow::anyhow!("Specified advanced_model '{}' not found in models configuration", specified_advanced));
            }
        }
        
        if let Some(ref specified_vl) = app_config.vl_model {
            if let Some(model) = models.iter().find(|m| m.name == *specified_vl) {
                vl_model = Some(model.name.clone());
                vl_api_base = Some(model.base_url.clone());
                vl_api_key = model.api_key.clone();
                println!("🎯 Using specified VL model: {}", model.name);
            } else {
                return Err(anyhow::anyhow!("Specified vl_model '{}' not found in models configuration", specified_vl));
            }
        }
        
        if let Some(ref specified_light) = app_config.light_model {
            if let Some(model) = models.iter().find(|m| m.name == *specified_light) {
                light_model = Some(model.name.clone());
                light_api_base = Some(model.base_url.clone());
                light_api_key = model.api_key.clone();
                println!("🎯 Using specified light model: {}", model.name);
            } else {
                return Err(anyhow::anyhow!("Specified light_model '{}' not found in models configuration", specified_light));
            }
        }
        
        // Embedding 模型：优先使用 Agent Service 页面的独立配置，不需要在 models 列表中
        if app_config.embedding_model.is_some() && app_config.embedding_url.is_some() {
            // 使用 Agent Service 页面配置的 Embedding 服务
            embedding_model = app_config.embedding_model.clone();
            embedding_api_base = app_config.embedding_url.clone();
            embedding_api_key = app_config.embedding_api_key.clone();
            println!("🎯 Using Embedding service config: {} @ {}", 
                embedding_model.as_ref().unwrap_or(&"".to_string()),
                embedding_api_base.as_ref().unwrap_or(&"".to_string()));
        } else if let Some(ref specified_embedding) = app_config.embedding_model {
            // 尝试从 models 列表中查找（兼容旧配置）
            if let Some(model) = models.iter().find(|m| m.name == *specified_embedding) {
                embedding_model = Some(model.name.clone());
                embedding_api_base = Some(model.base_url.clone());
                embedding_api_key = model.api_key.clone();
                println!("🎯 Using embedding model from models list: {}", model.name);
            }
        }
        
        // 主线零降级：使用高级模型作为主模型（不再独立配置主模型）
        if advanced_model.is_some() {
            main_model = advanced_model.clone();
            main_api_base = advanced_api_base.clone();
            main_api_key = advanced_api_key.clone();
            println!("🎯 Using advanced model as main model: {:?}", main_model);
        } else {
            return Err(anyhow::anyhow!("Advanced model not configured, 主线零降级"));
        }
        
        // 验证所有必要的配置都已设置
        let final_main_model = main_model.ok_or_else(|| anyhow::anyhow!("No main model configured. Please set 'model' or add a 'light' category model"))?;
        let final_main_api_base = main_api_base.ok_or_else(|| anyhow::anyhow!("No main model API base URL configured"))?;
        let final_main_api_key = main_api_key.unwrap_or_default();
        
        let final_advanced_model = advanced_model.ok_or_else(|| anyhow::anyhow!("No advanced model configured. Please set 'advanced_model' or add an 'advanced' category model"))?;
        let final_advanced_api_base = advanced_api_base.ok_or_else(|| anyhow::anyhow!("No advanced model API base URL configured"))?;
        let final_advanced_api_key = advanced_api_key.unwrap_or_default();
        
        let final_vl_model = vl_model.ok_or_else(|| anyhow::anyhow!("No VL model configured. Please set 'vl_model' or add a 'vl' category model"))?;
        let final_vl_api_base = vl_api_base.ok_or_else(|| anyhow::anyhow!("No VL model API base URL configured"))?;
        let final_vl_api_key = vl_api_key.unwrap_or_default();
        
        let final_light_model = light_model.ok_or_else(|| anyhow::anyhow!("No light model configured. Please set 'light_model' or add a 'light' category model"))?;
        let final_light_api_base = light_api_base.ok_or_else(|| anyhow::anyhow!("No light model API base URL configured"))?;
        let final_light_api_key = light_api_key.unwrap_or_default();

        // Embedding 配置：使用已解析的值，如果未配置则使用空字符串（Embedding 是可选的）
        let final_embedding_model_name = embedding_model.unwrap_or_default();
        let final_embedding_url = embedding_api_base.unwrap_or_default();
        let final_embedding_key = embedding_api_key.unwrap_or_default();
        
        let final_rerank_url = app_config.rerank_url.clone().unwrap_or_else(|| "".to_string());
        let final_rerank_model = app_config.rerank_model.clone().unwrap_or_else(|| "".to_string());
        let final_rerank_key = app_config.rerank_api_key.clone().unwrap_or_else(|| "".to_string());

        // 构建Python服务期望的简单配置格式
        let config_json = serde_json::json!({
            "main_model": final_main_model,
            "main_api_base": final_main_api_base,
            "main_api_key": final_main_api_key,
            "advanced_model": final_advanced_model,
            "advanced_api_base": final_advanced_api_base,
            "advanced_api_key": final_advanced_api_key,
            "vl_model": final_vl_model,
            "vl_api_base": final_vl_api_base,
            "vl_api_key": final_vl_api_key,
            "light_model": final_light_model,
            "light_api_base": final_light_api_base,
            "light_api_key": final_light_api_key,
            "embedding_model": final_embedding_model_name,
            "embedding_api_base": final_embedding_url,
            "embedding_api_key": final_embedding_key,
            "rerank_model": final_rerank_model,
            "rerank_api_base": final_rerank_url,
            "rerank_api_key": final_rerank_key
        });

        println!("📤 Sending LLM configuration to Python service...");
        println!("🔧 Final configuration:");
        println!("   Main: {} @ {}", final_main_model, final_main_api_base);
        println!("   Advanced: {} @ {}", final_advanced_model, final_advanced_api_base);
        println!("   VL: {} @ {}", final_vl_model, final_vl_api_base);
        println!("   Light: {} @ {}", final_light_model, final_light_api_base);
        println!("   Embedding: {} @ {}", final_embedding_model_name, final_embedding_url);
        println!("   Rerank: {} @ {}", final_rerank_model, final_rerank_url);
        
        // 使用公共方法发送HTTP请求
        let config_response: ConfigResponse = self.client.post_json("/config/update", &config_json).await.unwrap_or_else(|e| {
            println!("❌ Failed to send config update: {}", e);
            ConfigResponse {
                success: false,
                message: format!("Configuration update failed: {}", e),
                updated_at: chrono::Utc::now().to_rfc3339(),
            }
        });

        if config_response.success {
            println!("✅ Python service configuration updated successfully");
            Ok(config_response)
        } else {
            println!("⚠️ Python service configuration update failed: {}", config_response.message);
            Err(anyhow::anyhow!("Configuration update failed: {}", config_response.message))
        }
    }
}

/// 更新Python服务的LLM配置（全局函数）
pub async fn update_python_service_config(app_config: &AppConfig) -> Result<()> {
    if let Some(manager_lock) = GLOBAL_AGENT_MANAGER.get() {
        let manager = manager_lock.lock().await;
        match manager.update_python_config(app_config).await {
            Ok(_) => {
                println!("🎯 LLM configuration successfully sent to Python service");
                Ok(())
            }
            Err(e) => {
                println!("⚠️ Failed to update Python service configuration: {}", e);
                Err(e)
            }
        }
    } else {
        Err(anyhow::anyhow!("Agent manager not initialized"))
    }
}

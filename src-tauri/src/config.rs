use serde::{Deserialize, Serialize};
use anyhow::Result;
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ModelConfig {
    pub name: String,
    pub provider: String,
    pub base_url: String,
    pub api_key: Option<String>,
    #[serde(default)]
    pub category: Option<String>,
    #[serde(default)]
    pub supports_vision: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AppConfig {
    pub provider: String,
    pub base_url: String,
    pub api_key: Option<String>,
    pub model: Option<String>,
    #[serde(default)]
    pub models: Option<Vec<ModelConfig>>,
    #[serde(default)]
    pub streaming_enabled: Option<bool>,
    #[serde(default)]
    pub default_think: Option<bool>,
    #[serde(default)]
    pub max_context_messages: Option<u32>,
    #[serde(default)]
    pub temperature: Option<f64>,
    #[serde(default)]
    pub vl_model: Option<String>,
    #[serde(default)]
    pub light_model: Option<String>,
    #[serde(default)]
    pub advanced_model: Option<String>,
    #[serde(default)]
    pub language: Option<String>,
    #[serde(default)]
    pub mcp_servers: Option<Vec<serde_json::Value>>,
    #[serde(default)]
    pub mcp_server_infos: Option<std::collections::HashMap<String, serde_json::Value>>,
    #[serde(default)]
    pub mcp_max_retries: Option<u32>,
    #[serde(default)]
    pub mcp_reflection_enabled: Option<bool>,
    // embedding service configuration
    #[serde(default)]
    pub embedding_url: Option<String>,
    #[serde(default)]
    pub embedding_model: Option<String>,
    #[serde(default)]
    pub embedding_api_key: Option<String>,
    // legacy embedding model path (for local models)
    #[serde(default)]
    pub embedding_model_path: Option<String>,
    // rerank service configuration
    #[serde(default)]
    pub rerank_url: Option<String>,
    #[serde(default)]
    pub rerank_model: Option<String>,
    #[serde(default)]
    pub rerank_api_key: Option<String>,
    // python virtual environment path
    // python_venv_path removed - using HTTP service instead
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message { 
    pub role: String, 
    pub content: String,
    #[serde(default)]
    pub images: Option<Vec<ImageAttachment>>
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageAttachment {
    pub id: String,
    pub name: String,
    pub url: String,
    pub base64: String,
    #[serde(rename = "mimeType")]
    pub mime_type: String,
    pub size: u64,
}

/// 统一的配置加载函数，供所有地方使用
pub async fn load_app_config(app_handle: tauri::AppHandle) -> Result<AppConfig> {
    use crate::api::get_config_path;
    
    // 获取配置文件路径
    let config_file_path = get_config_path(app_handle).await
        .map_err(|e| anyhow::anyhow!("Failed to get config path: {}", e))?;
    
    let config_file = Path::new(&config_file_path);
    
    // 如果配置文件存在，读取配置
    if config_file.exists() {
        let config_content = std::fs::read_to_string(&config_file)
            .map_err(|e| anyhow::anyhow!("Failed to read config file: {}", e))?;
        
        let config: AppConfig = serde_json::from_str(&config_content)
            .map_err(|e| anyhow::anyhow!("Failed to parse config file: {}", e))?;
        
        println!("📋 Loaded config from file: provider={}, base_url={}", config.provider, config.base_url);
        
        // 打印 Python 环境配置
        if let Some(embedding_model_path) = &config.embedding_model_path {
            println!("🤖 Embedding model path: {}", embedding_model_path);
        }
        
        // 打印模型配置用于调试
        if let Some(models) = &config.models {
            println!("📋 Available models:");
            for model in models {
                println!("  - {}: {} ({})", model.name, model.base_url, model.category.as_deref().unwrap_or("unknown"));
            }
            if let Some(advanced_model) = &config.advanced_model {
                println!("📋 Advanced model: {}", advanced_model);
                if let Some(model_config) = models.iter().find(|m| m.name == *advanced_model) {
                    println!("📋 Advanced model config: {} -> {}", model_config.name, model_config.base_url);
                }
            }
        }
        
        Ok(config)
    } else {
        // 如果配置文件不存在，返回错误 - 不允许硬编码默认配置
        Err(anyhow::anyhow!(
            "配置文件不存在: {:?}\n请创建包含所有必要配置的settings.json文件\n主线零降级: 不允许使用默认配置",
            config_file
        ))
    }
}


use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tokio::time::{timeout, Duration};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatRequest {
    pub message: String,
    pub agent_type: String,
    pub stream: bool,
    pub context: Option<HashMap<String, serde_json::Value>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatResponse {
    pub message: String,
    pub agent_name: String,
    pub success: bool,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentInfo {
    pub name: String,
    #[serde(rename = "type")]
    pub agent_type: String,
    pub initialized: bool,
    pub config: Option<HashMap<String, serde_json::Value>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemAction {
    pub action: String,
    #[serde(flatten)]
    pub params: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemActionResponse {
    pub success: bool,
    pub result: Option<serde_json::Value>,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentExecuteRequest {
    pub app_name: String,
    pub window_title: Option<String>,
    pub prompt: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct AgentExecuteResponse {
    pub success: bool,
    pub result: Option<String>,
    pub reasoning: Option<String>,
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub intent_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthResponse {
    pub status: String,
    pub agent_initialized: bool,
    pub agent_ready: bool,
    pub framework: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelConfig {
    pub name: String,
    pub base_url: String,
    pub api_key: Option<String>,
    pub provider: String,
    pub category: String, // general, light, advanced, vl
    pub max_tokens: Option<i32>,
    pub temperature: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfigUpdateRequest {
    pub models: Option<Vec<ModelConfig>>,
    pub current_model: Option<String>,
    pub light_model: Option<String>,
    pub advanced_model: Option<String>,
    pub vl_model: Option<String>,
    pub provider: Option<String>,
    pub base_url: Option<String>,
    pub api_key: Option<String>,
    pub max_context_messages: Option<i32>,
    pub custom_settings: Option<HashMap<String, serde_json::Value>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfigResponse {
    pub success: bool,
    pub message: String,
    pub updated_at: String,
}

pub struct AgentHttpClient {
    client: Client,
    base_url: String,
    timeout_duration: Duration,
}

impl AgentHttpClient {
    pub fn new(base_url: String) -> Self {
        Self {
            client: Client::new(),
            base_url,
            timeout_duration: Duration::from_secs(300), // 5分钟，用于LLM推理
        }
    }

    #[allow(dead_code)]
    pub fn with_timeout(mut self, timeout_secs: u64) -> Self {
        self.timeout_duration = Duration::from_secs(timeout_secs);
        self
    }

    /// 检查服务健康状态
    pub async fn health_check(&self) -> Result<HealthResponse> {
        let url = format!("{}/health", self.base_url);
        
        let response = timeout(
            self.timeout_duration,
            self.client.get(&url).send()
        ).await??;

        if !response.status().is_success() {
            return Err(anyhow::anyhow!("Health check failed with status: {}", response.status()));
        }

        let health: HealthResponse = response.json().await?;
        Ok(health)
    }

    /// 发送关闭信号给Python服务
    pub async fn shutdown_service(&self) -> Result<()> {
        let url = format!("{}/shutdown", self.base_url);
        
        let response = timeout(
            Duration::from_secs(5), // 短超时，因为服务会立即关闭
            self.client.post(&url).send()
        ).await;

        match response {
            Ok(Ok(resp)) => {
                if resp.status().is_success() {
                    println!("✅ Shutdown signal sent successfully");
                } else {
                    println!("⚠️ Shutdown signal sent but got status: {}", resp.status());
                }
            }
            Ok(Err(e)) => {
                println!("⚠️ Network error sending shutdown signal: {}", e);
            }
            Err(_) => {
                println!("⚠️ Timeout sending shutdown signal (service may have already stopped)");
            }
        }
        
        Ok(())
    }

    /// 获取所有代理信息
    #[allow(dead_code)]
    pub async fn get_agents(&self) -> Result<Vec<AgentInfo>> {
        let url = format!("{}/agents", self.base_url);
        
        let response = timeout(
            self.timeout_duration,
            self.client.get(&url).send()
        ).await??;

        if !response.status().is_success() {
            return Err(anyhow::anyhow!("Get agents failed with status: {}", response.status()));
        }

        let agents: Vec<AgentInfo> = response.json().await?;
        Ok(agents)
    }

    /// 发送聊天消息
    pub async fn chat(&self, request: ChatRequest) -> Result<ChatResponse> {
        let url = format!("{}/chat", self.base_url);
        
        let response = timeout(
            self.timeout_duration,
            self.client
                .post(&url)
                .json(&request)
                .send()
        ).await??;

        if !response.status().is_success() {
            return Err(anyhow::anyhow!("Chat request failed with status: {}", response.status()));
        }

        let chat_response: ChatResponse = response.json().await?;
        Ok(chat_response)
    }

    /// 流式聊天
    pub async fn chat_stream(&self, request: ChatRequest) -> Result<reqwest::Response> {
        let url = format!("{}/chat/stream", self.base_url);
        
        let response = timeout(
            self.timeout_duration,
            self.client
                .post(&url)
                .json(&request)
                .send()
        ).await??;

        if !response.status().is_success() {
            return Err(anyhow::anyhow!("Stream chat request failed with status: {}", response.status()));
        }

        Ok(response)
    }

    /// 执行系统操作
    pub async fn system_action(&self, action: SystemAction) -> Result<SystemActionResponse> {
        let url = format!("{}/system/action", self.base_url);
        
        let response = timeout(
            self.timeout_duration,
            self.client
                .post(&url)
                .json(&action)
                .send()
        ).await??;

        if !response.status().is_success() {
            return Err(anyhow::anyhow!("System action failed with status: {}", response.status()));
        }

        let action_response: SystemActionResponse = response.json().await?;
        Ok(action_response)
    }

    /// 截图
    pub async fn take_screenshot(&self, save_path: Option<String>) -> Result<SystemActionResponse> {
        let mut params = HashMap::new();
        if let Some(path) = save_path {
            params.insert("save_path".to_string(), serde_json::Value::String(path));
        }

        let action = SystemAction {
            action: "take_screenshot".to_string(),
            params,
        };

        self.system_action(action).await
    }

    /// 输入文本
    pub async fn input_text(&self, text: String, target_app: Option<String>) -> Result<SystemActionResponse> {
        let mut params = HashMap::new();
        params.insert("text".to_string(), serde_json::Value::String(text));
        if let Some(app) = target_app {
            params.insert("target_app".to_string(), serde_json::Value::String(app));
        }

        let action = SystemAction {
            action: "input_text".to_string(),
            params,
        };

        self.system_action(action).await
    }

    /// 执行Agent任务
    pub async fn agent_execute(&self, request: AgentExecuteRequest) -> Result<AgentExecuteResponse> {
        let url = format!("{}/agent/execute", self.base_url);
        
        println!("🚀 Sending agent execute request to: {}", url);
        let prompt_preview: String = request.prompt.chars().take(50).collect();
        println!("📝 Request: app_name={}, prompt={}, session_id={:?}", request.app_name, prompt_preview, request.session_id);
        
        let response = timeout(
            self.timeout_duration,
            self.client
                .post(&url)
                .json(&request)
                .send()
        ).await??;

        let status = response.status();
        println!("📥 Received response with status: {}", status);
        
        if !status.is_success() {
            return Err(anyhow::anyhow!("Agent execute request failed with status: {}", status));
        }

            // 先获取原始响应文本用于调试
            let response_text = response.text().await?;
            let response_preview: String = response_text.chars().take(500).collect();
            println!("📄 Raw response (first 500 chars): {}", response_preview);
        
        // 尝试解析为JSON
        let agent_response: AgentExecuteResponse = serde_json::from_str(&response_text)
            .map_err(|e| {
                eprintln!("❌ Failed to parse agent response: {}", e);
                eprintln!("📄 Full response text: {}", response_text);
                anyhow::anyhow!("Failed to parse agent response: {}", e)
            })?;
        
        println!("✅ Parsed agent response - success: {}, result length: {}", 
            agent_response.success, 
            agent_response.result.as_ref().map(|s| s.len()).unwrap_or(0)
        );
            
            if let Some(ref result) = agent_response.result {
                let result_preview: String = result.chars().take(100).collect();
                println!("📤 Agent result (first 100 chars): {}", result_preview);
            }
        
        Ok(agent_response)
    }

    /// 获取活动窗口
    pub async fn get_active_window(&self) -> Result<SystemActionResponse> {
        let action = SystemAction {
            action: "get_active_window".to_string(),
            params: HashMap::new(),
        };

        self.system_action(action).await
    }

    /// 更新Python服务的LLM配置
    pub async fn update_config(&self, config_request: ConfigUpdateRequest) -> Result<ConfigResponse> {
        let url = format!("{}/config/update", self.base_url);
        
        let response = timeout(
            self.timeout_duration,
            self.client
                .post(&url)
                .json(&config_request)
                .send()
        ).await??;

        if !response.status().is_success() {
            return Err(anyhow::anyhow!("Config update failed with status: {}", response.status()));
        }

        let config_response: ConfigResponse = response.json().await?;
        Ok(config_response)
    }

    /// 发送通用的JSON POST请求
    pub async fn post_json<T: Serialize, R: for<'de> Deserialize<'de>>(&self, endpoint: &str, data: &T) -> Result<R> {
        let url = format!("{}{}", self.base_url, endpoint);
        
        let response = timeout(
            self.timeout_duration,
            self.client
                .post(&url)
                .json(data)
                .send()
        ).await??;

        if !response.status().is_success() {
            return Err(anyhow::anyhow!("POST request to {} failed with status: {}", endpoint, response.status()));
        }

        // 先获取响应文本用于调试
        let response_text = response.text().await?;
        println!("🔍 Response body: {}", response_text);
        
        // 尝试解析JSON
        match serde_json::from_str::<R>(&response_text) {
            Ok(result) => Ok(result),
            Err(e) => {
                println!("❌ JSON parsing error: {}", e);
                println!("📄 Raw response: {}", response_text);
                Err(anyhow::anyhow!("Failed to parse JSON response: {}", e))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_client_creation() {
        let client = AgentHttpClient::new("http://localhost:8765".to_string());
        assert_eq!(client.base_url, "http://localhost:8765");
    }

    #[tokio::test]
    async fn test_chat_request_serialization() {
        let request = ChatRequest {
            message: "Hello".to_string(),
            agent_type: "assistant".to_string(),
            stream: false,
            context: None,
        };

        let json = serde_json::to_string(&request).unwrap();
        assert!(json.contains("Hello"));
        assert!(json.contains("assistant"));
    }
}

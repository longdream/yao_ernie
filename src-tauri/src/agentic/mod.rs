// 保留旧模块用于向后兼容
pub mod agent_manager;
pub mod http_client;

// 导出旧 API 用于向后兼容
pub use agent_manager::{get_agent_manager, set_global_agent_manager, cleanup_agent_manager, initialize_agent_manager, update_python_service_config, AgentManager};

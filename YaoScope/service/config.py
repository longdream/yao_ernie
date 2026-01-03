"""
配置管理模块
"""
from pydantic import BaseModel
from typing import Optional


class LLMConfig(BaseModel):
    """LLM配置"""
    model_config = {"protected_namespaces": ()}
    
    model_name: str
    api_key: str
    api_base: str
    temperature: float = 0.7
    max_tokens: int = 8000


class ServiceConfig(BaseModel):
    """服务配置"""
    # 服务配置
    host: str = "127.0.0.1"
    port: int = 8765
    
    # LLM配置（通过/config/update动态设置）
    main_model: Optional[LLMConfig] = None
    advanced_model: Optional[LLMConfig] = None
    vl_model: Optional[LLMConfig] = None
    light_model: Optional[LLMConfig] = None
    embedding_model: Optional[LLMConfig] = None
    
    # PlanScope工作目录
    work_dir: str = "data/planscope"
    
    # 数据目录
    data_dir: str = "data"
    
    # 日志配置
    log_level: str = "INFO"
    log_dir: str = "logs"


# 全局配置实例
service_config = ServiceConfig()


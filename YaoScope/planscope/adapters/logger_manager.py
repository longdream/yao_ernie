"""
日志管理器适配器
从readscope提取的核心日志管理功能
"""
import logging
from typing import Dict, Any
from pathlib import Path


class LoggerManager:
    """
    日志管理器
    提供与readscope.core.LoggerManager兼容的接口
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化日志管理器
        
        Args:
            config: 日志配置
        """
        self.config = config
        self.loggers: Dict[str, logging.Logger] = {}
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志"""
        log_level = self.config.get("log_level", "INFO")
        log_file = self.config.get("file_path", "./logs/planscope.log")
        
        # 创建日志目录
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 不再配置根日志，避免重复打印
        # 每个logger会有自己的handlers
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        获取logger实例
        
        Args:
            name: logger名称
            
        Returns:
            Logger实例
        """
        if name not in self.loggers:
            logger = logging.getLogger(name)
            log_level = self.config.get("log_level", "INFO")
            logger.setLevel(getattr(logging, log_level))
            
            # 禁用传播，避免日志向上传播到根logger导致重复打印
            logger.propagate = False
            
            # 如果logger没有handlers，添加文件和控制台handler
            if not logger.handlers:
                log_file = self.config.get("file_path", "./logs/planscope.log")
                log_path = Path(log_file)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 文件handler
                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                file_handler.setLevel(logger.level)
                
                # 控制台handler
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logger.level)
                
                # 格式化
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                file_handler.setFormatter(formatter)
                console_handler.setFormatter(formatter)
                
                logger.addHandler(file_handler)
                logger.addHandler(console_handler)
            
            self.loggers[name] = logger
        
        return self.loggers[name]
    
    def log_performance_metrics(self, operation: str, duration: float, **kwargs):
        """记录性能指标"""
        logger = self.get_logger("performance")
        logger.info(f"[PERF] {operation}: {duration:.3f}s, extras: {kwargs}")
    
    def log_llm_call(self, model_name: str, prompt: str, response: str, duration: float):
        """记录LLM调用"""
        logger = self.get_logger("llm")
        logger.debug(f"[LLM] Model: {model_name}, Duration: {duration:.3f}s")
        logger.debug(f"  Prompt: {prompt[:100]}...")
        logger.debug(f"  Response: {response[:100]}...")


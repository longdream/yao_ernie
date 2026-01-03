"""
LangChain模型客户端适配器
使用LangChain Core + ChatOpenAI替代AgentScope
"""
import time
import json
from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import json_repair

from .config_manager import ConfigManager
from .logger_manager import LoggerManager


class LLMClientError(Exception):
    """LLM客户端错误"""
    pass


class LangChainModelClient:
    """
    LangChain模型客户端
    提供与AgentScopeModelClient完全兼容的接口
    支持多提供商（百度AIStudio、硅基流动等OpenAI兼容API）
    """
    
    def __init__(self, config_manager: ConfigManager, logger_manager: LoggerManager, 
                 embedding_config: Optional[Dict[str, Any]] = None):
        """
        初始化LangChain模型客户端
        
        Args:
            config_manager: 配置管理器
            logger_manager: 日志管理器
            embedding_config: 独立的embedding配置（可选）
        """
        self.config_manager = config_manager
        self.logger_manager = logger_manager
        self.logger = logger_manager.get_logger("langchain_client")
        self.embedding_config = embedding_config
        
        self.model = None
        self.model_config_name: str = ""
        self.model_name: str = ""
        
        self._initialize_langchain()
    
    def _initialize_langchain(self) -> None:
        """初始化LangChain模型"""
        try:
            # 获取LLM配置
            llm_config = self.config_manager.get_llm_config()
            
            self.model_name = llm_config.get("model_name", "")
            self.model_config_name = self.model_name
            
            # 创建ChatOpenAI实例（支持任何OpenAI兼容API）
            self.model = ChatOpenAI(
                model=llm_config["model_name"],
                api_key=llm_config["api_key"],
                base_url=llm_config.get("base_url"),  # 支持百度AIStudio等
                temperature=llm_config.get("temperature", 0.7),
                max_tokens=llm_config.get("max_tokens"),
                timeout=llm_config.get("timeout", 60.0),
                max_retries=llm_config.get("max_retries", 3)
            )
            
            self.logger.info(f"成功创建LangChain模型实例: {self.model_name}")
            self.logger.info(f"LangChain初始化成功，模式: {self.config_manager.get_runtime_mode()}")
            
        except Exception as e:
            error_msg = f"LangChain初始化失败: {str(e)}"
            self.logger.error(error_msg)
            raise LLMClientError(error_msg) from e
    
    async def call_model(self, 
                         prompt: str,
                         system_prompt: Optional[str] = None,
                         **kwargs) -> str:
        """
        调用模型生成响应
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            **kwargs: 其他生成参数
            
        Returns:
            模型响应内容
        """
        if not self.model:
            error_msg = "模型未初始化，无法进行模型调用"
            self.logger.error(error_msg)
            raise LLMClientError(error_msg)
        
        try:
            start_time = time.time()
            
            # 构建消息格式
            messages = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            messages.append(HumanMessage(content=prompt))
            
            # 调用LangChain模型（异步）
            response = await self.model.ainvoke(messages, **kwargs)
            
            # LangChain返回的AIMessage.content直接是字符串，比AgentScope更简单
            response_text = response.content
            
            duration = time.time() - start_time
            
            # 记录调用信息
            self.logger_manager.log_llm_call(
                model_name=self.model_config_name,
                prompt=prompt,
                response=response_text,
                duration=duration
            )
            
            return response_text
            
        except Exception as e:
            error_msg = f"LangChain模型调用失败: {str(e)}"
            self.logger.error(error_msg)
            raise LLMClientError(error_msg) from e
    
    async def call_model_with_json_response(self,
                                           prompt: str,
                                           system_prompt: Optional[str] = None,
                                           **kwargs) -> Dict[str, Any]:
        """
        调用模型并期望JSON格式响应
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            **kwargs: 其他生成参数
            
        Returns:
            解析后的JSON响应
        """
        self.logger.info(f"[JSON调用] 开始调用LLM，prompt长度: {len(prompt)}")
        self.logger.info(f"[JSON调用] Prompt前200字符: {prompt[:200]}")
        
        response_text = await self.call_model(prompt, system_prompt, **kwargs)
        
        self.logger.info(f"[JSON调用] LLM返回，响应长度: {len(response_text)}")
        self.logger.info(f"[JSON调用] 响应完整内容: {response_text}")
        
        try:
            # 尝试提取JSON内容
            # 先尝试找到完整的JSON对象
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            self.logger.info(f"[JSON提取] 原始响应长度: {len(response_text)} 字符")
            self.logger.info(f"[JSON提取] JSON起始位置: {json_start}, 结束位置: {json_end}")
            
            if json_start == -1:
                self.logger.error(f"[JSON提取] 未找到JSON起始符号")
                self.logger.error(f"[JSON提取] 原始响应: {response_text}")
                raise ValueError("响应中未找到JSON起始符号'{'")
            
            if json_end == 0:
                # 没有找到结束符号，可能JSON不完整
                self.logger.warning(f"[JSON提取] 未找到JSON结束符号，尝试修复")
                # 取从起始到末尾的所有内容
                json_str = response_text[json_start:]
                # 尝试添加缺失的结束符号
                if not json_str.rstrip().endswith('}'):
                    # 计算需要多少个}
                    open_braces = json_str.count('{') - json_str.count('}')
                    open_brackets = json_str.count('[') - json_str.count(']')
                    json_str = json_str.rstrip()
                    if open_brackets > 0:
                        json_str += ']' * open_brackets
                    if open_braces > 0:
                        json_str += '}' * open_braces
                    self.logger.info(f"[JSON修复] 添加了 {open_brackets} 个']'和 {open_braces} 个'}}'")
            else:
                json_str = response_text[json_start:json_end]
            
            self.logger.info(f"[JSON提取] 提取的JSON长度: {len(json_str)} 字符")
            self.logger.info(f"[JSON提取] JSON前500字符: {json_str[:500]}")
            
            # 使用json_repair修复可能不完整的JSON
            try:
                parsed_response = json_repair.loads(json_str)
                self.logger.info(f"[JSON解析] 成功解析JSON")
            except Exception as repair_error:
                self.logger.error(f"[JSON解析] json_repair.loads() 失败")
                self.logger.error(f"[JSON解析] 异常类型: {type(repair_error).__name__}")
                self.logger.error(f"[JSON解析] 异常信息: {str(repair_error)}")
                self.logger.error(f"[JSON解析] 提取的JSON字符串长度: {len(json_str)}")
                self.logger.error(f"[JSON解析] 提取的JSON字符串（前1000字符）: {json_str[:1000]}")
                self.logger.error(f"[JSON解析] 提取的JSON字符串（后500字符）: {json_str[-500:]}")
                self.logger.error(f"[JSON解析] 原始响应长度: {len(response_text)}")
                self.logger.error(f"[JSON解析] 原始响应（前1000字符）: {response_text[:1000]}")
                self.logger.error(f"[JSON解析] 原始响应（后500字符）: {response_text[-500:]}")
                
                # 尝试标准json解析
                try:
                    parsed_response = json.loads(json_str)
                    self.logger.info(f"[JSON解析] 使用标准json.loads()成功解析")
                    return parsed_response
                except json.JSONDecodeError as json_error:
                    self.logger.error(f"[JSON解析] 标准json.loads()也失败: {str(json_error)}")
                
                # 包装异常，确保错误信息清晰
                raise LLMClientError(f"JSON解析失败。原始响应长度: {len(response_text)}字符。提取的JSON长度: {len(json_str)}字符。json_repair错误: {type(repair_error).__name__}: {str(repair_error)}") from repair_error
            
            return parsed_response
            
        except LLMClientError:
            # 已经是LLMClientError，直接重新抛出
            raise
        except (json.JSONDecodeError, ValueError) as e:
            error_msg = f"JSON解析失败: {str(e)}"
            self.logger.error(error_msg)
            self.logger.error(f"原始响应（前2000字符）: {response_text[:2000]}")
            raise LLMClientError(error_msg) from e
        except Exception as e:
            # 捕获所有其他异常
            error_msg = f"JSON处理失败: {type(e).__name__}: {str(e)}"
            self.logger.error(error_msg)
            self.logger.error(f"原始响应（前2000字符）: {response_text[:2000]}")
            raise LLMClientError(error_msg) from e
    
    async def get_embedding(self, text: str):
        """
        获取文本的embedding向量
        保持与AgentScope完全相同的逻辑
        """
        try:
            # 优先使用传入的embedding_config
            if self.embedding_config:
                provider = self.embedding_config.get('provider', '')
                
                if provider in ['siliconflow', 'qwen', 'openai']:
                    return await self._get_http_embedding(text, self.embedding_config)
            
            # 使用OpenAI兼容的embedding接口
            llm_config = self.config_manager.get_llm_config()
            if llm_config.get('provider') in ['openai', 'qwen']:
                from openai import AsyncOpenAI
                
                try:
                    embedding_config = self.config_manager.get_embedding_config()
                    api_key = embedding_config.get('api_key', llm_config.get('api_key'))
                    base_url = embedding_config.get('base_url', llm_config.get('base_url'))
                    model_name = embedding_config.get('model_name', 'text-embedding-v2')
                except:
                    api_key = llm_config.get('api_key')
                    base_url = llm_config.get('base_url')
                    model_name = 'text-embedding-v2'
                
                client = AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url
                )
                
                response = await client.embeddings.create(
                    model=model_name,
                    input=text
                )
                
                return response.data[0].embedding
            
            return None
            
        except Exception as e:
            self.logger.error(f"获取embedding失败: {str(e)}")
            return None
    
    async def _get_http_embedding(self, text: str, config: Dict[str, Any]):
        """通过HTTP API获取embedding"""
        import httpx
        
        base_url = config.get('base_url', '')
        api_key = config.get('api_key', '')
        model_name = config.get('model_name', 'BAAI/bge-large-zh-v1.5')
        
        # embeddings endpoint
        if not base_url.endswith('/embeddings'):
            if base_url.endswith('/v1'):
                url = f"{base_url}/embeddings"
            else:
                url = f"{base_url}/v1/embeddings"
        else:
            url = base_url
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model_name,
            "input": text
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url, 
                    headers=headers, 
                    json=data, 
                    timeout=config.get('timeout', 30.0)
                )
                response.raise_for_status()
                result = response.json()
                
                if 'data' in result and len(result['data']) > 0:
                    return result['data'][0]['embedding']
                else:
                    raise ValueError(f"API返回格式错误: {result}")
                    
        except Exception as e:
            self.logger.error(f"Embedding API调用失败: {e}")
            raise LLMClientError(f"Embedding API调用失败: {e}") from e
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取当前模型信息"""
        runtime_mode = self.config_manager.get_runtime_mode()
        llm_config = self.config_manager.get_llm_config()
        
        return {
            "runtime_mode": runtime_mode,
            "config_name": self.model_config_name,
            "model_type": "openai_chat",
            "model_name": self.model_name,
        }
    
    async def validate_connection(self) -> bool:
        """验证模型连接是否正常"""
        try:
            test_response = await self.call_model(
                prompt="测试连接，请回复'连接正常'",
                system_prompt="你是一个测试助手，请简短回复。"
            )
            
            self.logger.info("模型连接验证成功")
            return True
            
        except Exception as e:
            self.logger.error(f"模型连接验证失败: {str(e)}")
            return False
    
    def create_model_instance(self):
        """为外部使用提供的模型实例创建方法"""
        return self.model
    
    def shutdown(self) -> None:
        """关闭模型客户端"""
        self.logger.info("LangChain模型客户端已关闭")


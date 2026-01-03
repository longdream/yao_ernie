"""
LLM分析工具类
提供统一的LLM调用接口，支持缓存和embedding相似度匹配
"""
import json
import hashlib
import asyncio
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import concurrent.futures
from threading import Lock

try:
    import nest_asyncio
    nest_asyncio.apply()
    HAS_NEST_ASYNCIO = True
except ImportError:
    HAS_NEST_ASYNCIO = False


class LLMAnalyzer:
    """
    LLM分析工具类
    
    提供带缓存的LLM调用、embedding相似度计算等功能
    """
    
    def __init__(self, model_client, embedding_client, logger_manager, cache_dir: str, storage_manager=None):
        """
        初始化LLM分析器
        
        Args:
            model_client: AgentScope模型客户端（用于文本生成）
            embedding_client: Embedding客户端（用于向量计算）
            logger_manager: 日志管理器
            cache_dir: 缓存目录（向后兼容，优先使用storage_manager）
            storage_manager: 存储管理器（可选，推荐使用）
        """
        self.model_client = model_client
        self.embedding_client = embedding_client
        self.logger_manager = logger_manager
        self.logger = logger_manager.get_logger("llm_analyzer")
        self.storage_manager = storage_manager
        
        # 缓存目录
        if storage_manager:
            self.cache_dir = storage_manager.get_path("llm_cache")
        else:
            self.cache_dir = Path(cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存
        self.memory_cache: Dict[str, Any] = {}
        
        # 缓存配置
        self.max_cache_size = 1000  # 最大缓存条目数
        self.cache_expiry_days = 30  # 缓存过期天数
        
        # 线程池执行器（用于隔离异步调用）
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="llm_analyzer")
        
        # 线程锁（保护缓存访问）
        self.embedding_lock = Lock()
        
        # Embedding缓存（用于相似度匹配）
        self.embedding_cache: Dict[str, np.ndarray] = {}
        self.embedding_cache_file = self.cache_dir / "embeddings.json"
        
        # 加载持久化的embedding缓存
        self._load_embedding_cache()
        
        # 清理过期缓存
        self._cleanup_old_cache()
        
        self.logger.info("LLMAnalyzer初始化完成")
    
    async def analyze_with_cache(self, prompt: str, cache_key: str, use_embedding_match: bool = False, similarity_threshold: float = 0.95) -> Dict[str, Any]:
        """
        带缓存的LLM调用
        
        Args:
            prompt: 提示词
            cache_key: 缓存键
            use_embedding_match: 是否使用embedding相似度匹配缓存
            similarity_threshold: 相似度阈值（仅当use_embedding_match=True时有效）
            
        Returns:
            LLM返回的JSON结果
        """
        # 1. 检查内存缓存（精确匹配）
        if cache_key in self.memory_cache:
            self.logger.debug(f"命中内存缓存: {cache_key}")
            return self.memory_cache[cache_key]
        
        # 2. 检查磁盘缓存（精确匹配）
        cached = self._load_from_disk(cache_key)
        if cached:
            self.logger.debug(f"命中磁盘缓存: {cache_key}")
            self.memory_cache[cache_key] = cached
            return cached
        
        # 3. 如果启用embedding匹配，尝试找到相似的缓存
        if use_embedding_match:
            similar_result = await self._find_similar_cached_result(prompt, similarity_threshold)
            if similar_result:
                self.logger.info(f"命中相似缓存（相似度>{similarity_threshold}）")
                # 保存到当前cache_key
                self.memory_cache[cache_key] = similar_result
                self._save_to_disk(cache_key, similar_result)
                return similar_result
        
        # 4. 调用LLM
        self.logger.info(f"调用LLM: {cache_key}")
        try:
            result = await self.model_client.call_model_with_json_response(prompt=prompt)
            
            # 5. 保存缓存
            self.memory_cache[cache_key] = result
            self._save_to_disk(cache_key, result)
            
            # 6. 如果启用embedding，保存prompt的embedding
            if use_embedding_match:
                await self._save_prompt_embedding(prompt, cache_key)
            
            return result
            
        except Exception as e:
            self.logger.error(f"LLM调用失败: {str(e)}")
            raise
    
    def analyze_with_cache_sync(self, prompt: str, cache_key: str, use_embedding_match: bool = False, similarity_threshold: float = 0.95) -> Dict[str, Any]:
        """
        同步版本的带缓存LLM调用
        
        Args:
            prompt: 提示词
            cache_key: 缓存键
            use_embedding_match: 是否使用embedding相似度匹配缓存
            similarity_threshold: 相似度阈值
            
        Returns:
            LLM返回的JSON结果
        """
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_running_loop()
            # 在事件循环中，如果有nest_asyncio则可以使用asyncio.run()
            if HAS_NEST_ASYNCIO:
                # nest_asyncio已应用，允许嵌套事件循环
                return asyncio.run(self.analyze_with_cache(prompt, cache_key, use_embedding_match, similarity_threshold))
            else:
                # 没有nest_asyncio，抛出异常
                raise RuntimeError("检测到运行中的事件循环，无法使用asyncio.run()。请安装nest_asyncio或在非事件循环环境中调用。")
        except RuntimeError as e:
            if "检测到运行中的事件循环" in str(e) or "no running event loop" not in str(e).lower():
                # 如果是我们的异常或其他RuntimeError，重新抛出
                if "no running event loop" not in str(e).lower():
                    raise
            # 没有运行中的事件循环，可以使用asyncio.run
            return asyncio.run(self.analyze_with_cache(prompt, cache_key, use_embedding_match, similarity_threshold))
    
    async def calculate_embedding_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的embedding相似度
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            余弦相似度（0-1）
        """
        try:
            # 获取embeddings
            emb1 = await self._get_embedding(text1)
            emb2 = await self._get_embedding(text2)
            
            # 计算余弦相似度
            similarity = self._cosine_similarity(emb1, emb2)
            
            return float(similarity)
            
        except Exception as e:
            self.logger.error(f"计算embedding相似度失败: {str(e)}")
            return 0.0
    
    def calculate_embedding_similarity_sync(self, text1: str, text2: str) -> float:
        """
        同步版本的embedding相似度计算（使用线程池隔离）
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            余弦相似度（0-1）
        """
        try:
            self.logger.debug(f"计算embedding相似度: '{text1[:30]}...' vs '{text2[:30]}...'")
            
            # 在独立线程中运行异步代码，避免事件循环冲突
            future = self.executor.submit(self._calc_similarity_in_thread, text1, text2)
            result = future.result(timeout=30)
            
            self.logger.info(f"Embedding相似度计算成功: {result:.3f}")
            return result
            
        except concurrent.futures.TimeoutError:
            self.logger.error("embedding相似度计算超时（30秒）")
            raise RuntimeError("embedding相似度计算超时（30秒）")
        except Exception as e:
            self.logger.error(f"embedding相似度计算失败: {e}", exc_info=True)
            raise  # 直接抛出异常，不使用降级方案
    
    def _calc_similarity_in_thread(self, text1: str, text2: str) -> float:
        """
        在独立线程中执行异步embedding计算
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            余弦相似度
        """
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                self.calculate_embedding_similarity(text1, text2)
            )
            return result
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    
    async def _get_embedding(self, text: str) -> np.ndarray:
        """
        获取文本的embedding向量（线程安全）
        
        Args:
            text: 文本
            
        Returns:
            embedding向量
        """
        # 生成缓存键
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        # 检查缓存（线程安全）
        with self.embedding_lock:
            if text_hash in self.embedding_cache:
                self.logger.debug(f"命中embedding缓存: {text[:30]}...")
                return self.embedding_cache[text_hash]
        
        # 调用embedding API
        try:
            self.logger.debug(f"调用embedding API: {text[:50]}...")
            embedding = await self.embedding_client.get_embedding(text)
            
            if embedding is None:
                self.logger.warning(f"embedding API返回None")
                return np.zeros(768)  # 默认维度
            
            # 转换为numpy数组
            if isinstance(embedding, list):
                embedding = np.array(embedding)
            elif not isinstance(embedding, np.ndarray):
                self.logger.warning(f"embedding类型错误: {type(embedding)}")
                return np.zeros(768)
            
            # 保存到缓存（线程安全）
            with self.embedding_lock:
                self.embedding_cache[text_hash] = embedding
                self._save_embedding_cache()
            
            self.logger.debug(f"embedding获取成功，维度: {embedding.shape}")
            return embedding
            
        except Exception as e:
            self.logger.error(f"获取embedding失败: {str(e)}", exc_info=True)
            # 返回零向量
            return np.zeros(768)  # 默认维度
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        计算余弦相似度
        
        Args:
            vec1: 向量1
            vec2: 向量2
            
        Returns:
            余弦相似度
        """
        # 归一化
        vec1_norm = vec1 / (np.linalg.norm(vec1) + 1e-10)
        vec2_norm = vec2 / (np.linalg.norm(vec2) + 1e-10)
        
        # 点积
        similarity = np.dot(vec1_norm, vec2_norm)
        
        return float(similarity)
    
    async def _find_similar_cached_result(self, prompt: str, threshold: float) -> Optional[Dict[str, Any]]:
        """
        查找相似的缓存结果
        
        Args:
            prompt: 当前提示词
            threshold: 相似度阈值
            
        Returns:
            相似的缓存结果（如果找到）
        """
        # 获取当前prompt的embedding
        current_emb = await self._get_embedding(prompt)
        
        # 遍历所有缓存的prompt
        best_similarity = 0.0
        best_cache_key = None
        
        for cached_prompt_hash, cached_emb in self.embedding_cache.items():
            similarity = self._cosine_similarity(current_emb, cached_emb)
            
            if similarity > best_similarity and similarity >= threshold:
                best_similarity = similarity
                best_cache_key = cached_prompt_hash
        
        # 如果找到相似的，加载其结果
        if best_cache_key:
            self.logger.info(f"找到相似缓存，相似度: {best_similarity:.3f}")
            return self._load_from_disk(best_cache_key)
        
        return None
    
    async def _save_prompt_embedding(self, prompt: str, cache_key: str) -> None:
        """
        保存prompt的embedding
        
        Args:
            prompt: 提示词
            cache_key: 缓存键
        """
        embedding = await self._get_embedding(prompt)
        # embedding已经在_get_embedding中保存到缓存了
    
    def _load_from_disk(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        从磁盘加载缓存
        
        Args:
            cache_key: 缓存键
            
        Returns:
            缓存的结果（如果存在）
        """
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"加载缓存失败 {cache_file}: {str(e)}")
            return None
    
    def _save_to_disk(self, cache_key: str, result: Dict[str, Any]) -> None:
        """
        保存缓存到磁盘
        
        Args:
            cache_key: 缓存键
            result: 结果
        """
        if self.storage_manager:
            # 使用StorageManager保存
            self.storage_manager.save_llm_cache(cache_key, result)
        else:
            # 向后兼容：直接保存，确保目录存在
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self.cache_dir / f"{cache_key}.json"
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self.logger.warning(f"保存缓存失败 {cache_file}: {str(e)}")
    
    def _load_embedding_cache(self) -> None:
        """加载embedding缓存"""
        if not self.embedding_cache_file.exists():
            return
        
        try:
            with open(self.embedding_cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 转换为numpy数组
            for key, value in data.items():
                self.embedding_cache[key] = np.array(value)
            
            self.logger.info(f"加载了 {len(self.embedding_cache)} 个embedding缓存")
            
        except Exception as e:
            self.logger.warning(f"加载embedding缓存失败: {str(e)}")
    
    def _save_embedding_cache(self) -> None:
        """保存embedding缓存"""
        try:
            # 转换为列表格式
            data = {key: value.tolist() for key, value in self.embedding_cache.items()}
            
            if self.storage_manager:
                # 使用StorageManager保存
                self.storage_manager.save_embedding_cache(data)
            else:
                # 向后兼容：直接保存，确保目录存在
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                with open(self.embedding_cache_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            self.logger.warning(f"保存embedding缓存失败: {str(e)}")
    
    def clear_cache(self) -> int:
        """
        清理所有缓存
        
        Returns:
            删除的文件数量
        """
        count = 0
        
        # 清理内存缓存
        self.memory_cache.clear()
        self.embedding_cache.clear()
        
        # 清理磁盘缓存
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except Exception as e:
                self.logger.warning(f"删除缓存文件失败 {cache_file}: {str(e)}")
        
        self.logger.info(f"清理了 {count} 个缓存文件")
        return count
    
    def _cleanup_old_cache(self) -> int:
        """
        清理过期的缓存文件（超过cache_expiry_days天）
        使用LRU策略，如果缓存数量超过max_cache_size，删除最旧的文件
        
        Returns:
            删除的文件数量
        """
        count = 0
        now = datetime.now()
        
        # 获取所有缓存文件及其修改时间
        cache_files = []
        for cache_file in self.cache_dir.glob("*.json"):
            if cache_file.name == "embeddings.json":
                continue  # 跳过embedding缓存文件
            try:
                mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
                cache_files.append((cache_file, mtime))
            except Exception as e:
                self.logger.warning(f"读取缓存文件时间失败: {cache_file}, {e}")
        
        # 按修改时间排序（最旧的在前）
        cache_files.sort(key=lambda x: x[1])
        
        # 1. 删除过期文件
        for cache_file, mtime in cache_files[:]:
            age_days = (now - mtime).days
            if age_days > self.cache_expiry_days:
                try:
                    cache_file.unlink()
                    count += 1
                    cache_files.remove((cache_file, mtime))
                    self.logger.debug(f"删除过期缓存: {cache_file.name} (年龄: {age_days}天)")
                except Exception as e:
                    self.logger.warning(f"删除过期缓存失败: {cache_file}, {e}")
        
        # 2. 如果缓存数量超过限制，使用LRU策略删除最旧的文件
        if len(cache_files) > self.max_cache_size:
            files_to_delete = cache_files[:len(cache_files) - self.max_cache_size]
            for cache_file, _ in files_to_delete:
                try:
                    cache_file.unlink()
                    count += 1
                    self.logger.debug(f"LRU删除缓存: {cache_file.name}")
                except Exception as e:
                    self.logger.warning(f"LRU删除缓存失败: {cache_file}, {e}")
        
        if count > 0:
            self.logger.info(f"清理过期/过量缓存完成，删除了{count}个文件")
        
        return count


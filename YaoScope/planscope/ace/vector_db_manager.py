"""
向量数据库管理器
使用ChromaDB进行高效的向量检索
"""
import json
import asyncio
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    print("[WARNING] ChromaDB未安装，向量数据库功能不可用")


class VectorDBManager:
    """
    向量数据库管理器
    
    使用ChromaDB存储和检索任务embedding，实现高效的语义搜索
    """
    
    COLLECTION_NAME = "task_embeddings"
    
    def __init__(self, persist_directory: str, embedding_client, logger_manager):
        """
        初始化向量数据库管理器
        
        Args:
            persist_directory: ChromaDB持久化目录
            embedding_client: Embedding客户端（用于计算向量）
            logger_manager: 日志管理器
        """
        self.persist_directory = Path(persist_directory)
        self.embedding_client = embedding_client
        self.logger_manager = logger_manager
        self.logger = logger_manager.get_logger("vector_db")
        
        # 检查ChromaDB是否安装
        if not HAS_CHROMADB:
            error_msg = "ChromaDB未安装，无法使用向量数据库功能。请运行: pip install chromadb"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        # 确保目录存在
        self.logger.info(f"正在初始化向量数据库: {self.persist_directory}")
        try:
            self.persist_directory.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"✓ 向量数据库目录已创建: {self.persist_directory}")
        except Exception as e:
            error_msg = f"无法创建向量数据库目录: {str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        
        # 初始化ChromaDB客户端
        try:
            self.logger.info("正在初始化ChromaDB客户端...")
            self.client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(
                    anonymized_telemetry=False,  # 禁用遥测
                    allow_reset=True
                )
            )
            self.logger.info("✓ ChromaDB客户端初始化成功")
            
            # 创建或获取collection
            self.logger.info(f"正在创建/获取collection: {self.COLLECTION_NAME}")
            self.collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={
                    "hnsw:space": "cosine",  # 使用余弦相似度
                    "hnsw:construction_ef": 200,  # 构建参数（提升精度）
                    "hnsw:M": 16  # 每个节点的连接数
                }
            )
            self.logger.info("✓ Collection创建/获取成功")
            
            # 验证collection可用（使用超时保护）
            self.logger.info("正在验证向量数据库...")
            count = self._safe_get_count()
            self.logger.info(f"✓ 向量数据库初始化成功: {count} 个任务")
            
        except Exception as e:
            error_msg = f"向量数据库初始化失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            # 清理已创建的对象
            self.client = None
            self.collection = None
            # 抛出错误，阻止PlanScope启动
            raise RuntimeError(error_msg) from e
    
    def is_available(self) -> bool:
        """检查向量数据库是否可用"""
        return self.client is not None and self.collection is not None
    
    def _safe_get_count(self, timeout: float = 3.0) -> int:
        """
        安全地获取collection的count，带超时保护
        
        Args:
            timeout: 超时时间（秒）
        
        Returns:
            任务数量
        
        Raises:
            TimeoutError: 如果获取超时
            RuntimeError: 如果获取失败
        """
        import concurrent.futures
        
        def get_count():
            return self.collection.count()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(get_count)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(f"获取向量数据库count超时（{timeout}秒）")
            except Exception as e:
                raise RuntimeError(f"获取向量数据库count失败: {str(e)}") from e
    
    async def get_task(self, flow_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定flow_id的任务
        
        Args:
            flow_id: Flow ID
            
        Returns:
            任务数据字典，如果不存在则返回None
        """
        if not self.is_available():
            return None
        
        try:
            # 使用ChromaDB的get方法（在线程池中执行避免阻塞）
            result = await asyncio.to_thread(
                self.collection.get,
                ids=[flow_id],
                include=["metadatas", "documents", "embeddings"]
            )
            
            # 检查是否找到
            if not result or not result['ids']:
                return None
            
            # 返回第一个结果
            return {
                'flow_id': result['ids'][0],
                'task_description': result['documents'][0] if result['documents'] else '',
                'metadata': result['metadatas'][0] if result['metadatas'] else {},
                'embedding': result['embeddings'][0] if result['embeddings'] else None
            }
            
        except Exception as e:
            self.logger.error(f"获取任务失败 ({flow_id}): {str(e)}")
            return None
    
    async def add_task(self,
                      flow_id: str,
                      task_description: str,
                      embedding: Optional[np.ndarray] = None,
                      metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        添加任务到向量数据库
        
        Args:
            flow_id: Flow ID（作为唯一标识）
            task_description: 任务描述
            embedding: Embedding向量（如果为None则自动计算）
            metadata: 元数据（success, created_at等）
            
        Returns:
            是否成功
        """
        if not self.is_available():
            return False
        
        try:
            # 如果没有提供embedding，计算它
            if embedding is None:
                if self.embedding_client:
                    embedding = await self.embedding_client.get_embedding(task_description)
                    if embedding is None:
                        self.logger.warning(f"无法计算embedding: {flow_id}")
                        return False
                else:
                    self.logger.error("Embedding客户端未初始化")
                    return False
            
            # 转换为列表（ChromaDB要求）
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()
            
            # 准备metadata
            meta = metadata or {}
            meta['flow_id'] = flow_id
            meta['task_description'] = task_description[:200]  # 限制长度
            meta['indexed_at'] = datetime.now().isoformat()
            
            # 添加到collection（在线程池中执行避免阻塞）
            await asyncio.to_thread(
                self.collection.add,
                ids=[flow_id],
                embeddings=[embedding],
                documents=[task_description],
                metadatas=[meta]
            )
            
            self.logger.debug(f"✓ 任务已添加到向量库: {flow_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"添加任务到向量库失败 ({flow_id}): {str(e)}", exc_info=True)
            return False
    
    async def search_similar_tasks(self,
                                   query_embedding: np.ndarray,
                                   top_k: int = 20,
                                   where: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        搜索相似任务
        
        Args:
            query_embedding: 查询向量
            top_k: 返回Top-K个结果
            where: 过滤条件（例如 {"success": True}）
            
        Returns:
            相似任务列表，每个包含：
            - id: flow_id
            - similarity: 相似度（0-1）
            - metadata: 元数据
            - document: 任务描述
        """
        if not self.is_available():
            return []
        
        try:
            # 转换为列表
            if isinstance(query_embedding, np.ndarray):
                query_embedding = query_embedding.tolist()
            
            # 执行向量搜索（使用asyncio.to_thread避免阻塞事件循环）
            # ChromaDB的query是同步阻塞调用，必须在线程池中执行
            self.logger.debug(f"开始向量搜索，top_k={top_k}")
            results = await asyncio.to_thread(
                self.collection.query,
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where,
                include=["metadatas", "documents", "distances"]
            )
            self.logger.debug(f"向量搜索完成，结果数: {len(results.get('ids', [[]])[0]) if results else 0}")
            
            # 解析结果
            similar_tasks = []
            if results and len(results['ids']) > 0:
                for i in range(len(results['ids'][0])):
                    task = {
                        'id': results['ids'][0][i],
                        'flow_id': results['ids'][0][i],
                        'similarity': 1.0 - results['distances'][0][i],  # ChromaDB返回距离，转为相似度
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'document': results['documents'][0][i] if results['documents'] else ''
                    }
                    similar_tasks.append(task)
            
            self.logger.info(f"✓ 向量搜索完成: 找到 {len(similar_tasks)} 个相似任务")
            return similar_tasks
            
        except Exception as e:
            self.logger.error(f"向量搜索失败: {str(e)}", exc_info=True)
            return []
    
    async def update_task_metadata(self,
                                  flow_id: str,
                                  metadata_updates: Dict[str, Any]) -> bool:
        """
        更新任务元数据
        
        Args:
            flow_id: Flow ID
            metadata_updates: 要更新的元数据（例如 {"success": True}）
            
        Returns:
            是否成功
        """
        if not self.is_available():
            return False
        
        try:
            # ChromaDB不支持部分更新，需要先获取再更新（在线程池中执行）
            result = await asyncio.to_thread(
                self.collection.get,
                ids=[flow_id],
                include=["metadatas", "documents", "embeddings"]
            )
            
            if not result or len(result['ids']) == 0:
                self.logger.warning(f"任务不存在于向量库: {flow_id}")
                return False
            
            # 合并metadata
            current_meta = result['metadatas'][0]
            current_meta.update(metadata_updates)
            current_meta['updated_at'] = datetime.now().isoformat()
            
            # 更新（在线程池中执行）
            await asyncio.to_thread(
                self.collection.update,
                ids=[flow_id],
                metadatas=[current_meta]
            )
            
            self.logger.debug(f"✓ 任务元数据已更新: {flow_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"更新任务元数据失败 ({flow_id}): {str(e)}", exc_info=True)
            return False
    
    async def delete_task(self, flow_id: str) -> bool:
        """
        从向量数据库删除任务
        
        Args:
            flow_id: Flow ID
            
        Returns:
            是否成功
        """
        if not self.is_available():
            return False
        
        try:
            # 在线程池中执行删除操作
            await asyncio.to_thread(
                self.collection.delete,
                ids=[flow_id]
            )
            self.logger.debug(f"✓ 任务已从向量库删除: {flow_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"删除任务失败 ({flow_id}): {str(e)}", exc_info=True)
            return False
    
    async def rebuild_index_from_tasks(self, task_history_dir: Path) -> Tuple[int, int]:
        """
        从JSON任务文件重建向量数据库索引
        
        Args:
            task_history_dir: 任务历史目录
            
        Returns:
            (成功数量, 失败数量)
        """
        if not self.is_available():
            self.logger.error("向量数据库不可用，无法重建索引")
            return (0, 0)
        
        self.logger.info("=" * 60)
        self.logger.info("开始重建向量数据库索引...")
        self.logger.info("=" * 60)
        
        success_count = 0
        fail_count = 0
        
        # 遍历所有任务文件
        task_files = list(Path(task_history_dir).glob("task_*.json"))
        total = len(task_files)
        
        self.logger.info(f"找到 {total} 个任务文件")
        
        for idx, task_file in enumerate(task_files, 1):
            try:
                # 加载任务数据
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = json.load(f)
                
                flow_id = task_data.get('flow_id', task_file.stem.replace('task_', ''))
                task_description = task_data.get('task_description', '')
                
                # 准备metadata
                metadata = {
                    'task_id': task_data.get('task_id', ''),
                    'success': task_data.get('success', False),
                    'created_at': task_data.get('created_at', ''),
                    'app_name': task_data.get('plan_json', {}).get('app_name', ''),
                    'steps_count': len(task_data.get('plan_json', {}).get('steps', [])),
                    'complexity_level': task_data.get('plan_json', {}).get('complexity_level', '')
                }
                
                # 添加到向量库
                result = await self.add_task(
                    flow_id=flow_id,
                    task_description=task_description,
                    metadata=metadata
                )
                
                if result:
                    success_count += 1
                else:
                    fail_count += 1
                
                # 进度日志
                if idx % 10 == 0 or idx == total:
                    self.logger.info(f"进度: {idx}/{total}, 成功: {success_count}, 失败: {fail_count}")
                
            except Exception as e:
                self.logger.error(f"处理任务文件失败 ({task_file.name}): {str(e)}")
                fail_count += 1
        
        self.logger.info("=" * 60)
        self.logger.info(f"✓ 索引重建完成: 成功 {success_count}, 失败 {fail_count}")
        self.logger.info("=" * 60)
        
        return (success_count, fail_count)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取向量数据库统计信息
        
        Returns:
            统计信息字典
        """
        if not self.is_available():
            return {
                'available': False,
                'total_tasks': 0,
                'persist_directory': str(self.persist_directory)
            }
        
        try:
            count = self._safe_get_count(timeout=2.0)
            return {
                'available': True,
                'total_tasks': count,
                'collection_name': self.COLLECTION_NAME,
                'persist_directory': str(self.persist_directory),
                'distance_metric': 'cosine'
            }
        except Exception as e:
            self.logger.warning(f"获取统计信息失败: {str(e)}")
            return {
                'available': False,
                'total_tasks': 0,
                'error': str(e)
            }
    
    def clear_all(self) -> bool:
        """
        清空向量数据库（慎用！）
        
        Returns:
            是否成功
        """
        if not self.is_available():
            return False
        
        try:
            # 删除并重新创建collection
            self.client.delete_collection(name=self.COLLECTION_NAME)
            self.collection = self.client.create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
            self.logger.warning("⚠️ 向量数据库已清空")
            return True
            
        except Exception as e:
            self.logger.error(f"清空向量数据库失败: {str(e)}", exc_info=True)
            return False


"""
ACE任务匹配器
计算任务相似度并复用历史任务的plan JSON
"""
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter
import difflib

from planscope.core.exceptions import TaskMatchingError


class TaskMatcher:
    """
    任务匹配器
    
    负责计算任务相似度，查找可复用的历史任务
    """
    
    def __init__(self, work_dir: str, logger_manager, llm_analyzer=None, storage_manager=None, vector_db_manager=None):
        """
        初始化任务匹配器
        
        Args:
            work_dir: 工作目录
            logger_manager: 日志管理器
            llm_analyzer: LLM分析器（可选，用于智能判断）
            storage_manager: 存储管理器（可选，优先使用）
            vector_db_manager: 向量数据库管理器（可选，用于高效检索）
        """
        self.work_dir = Path(work_dir)
        self.logger_manager = logger_manager
        self.logger = logger_manager.get_logger("task_matcher")
        self.storage_manager = storage_manager
        
        # LLM分析器
        self.llm_analyzer = llm_analyzer
        
        # 向量数据库管理器
        self.vector_db = vector_db_manager
        
        # 任务历史目录
        if storage_manager:
            self.task_history_dir = storage_manager.get_path("tasks")
        else:
            self.task_history_dir = self.work_dir / "task_history"
            self.task_history_dir.mkdir(parents=True, exist_ok=True)
    
    async def find_similar_tasks(self,
                          task_description: str,
                          threshold: float = 0.8,
                          max_candidates: int = 20) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        查找相似任务（使用向量数据库）
        
        通过向量近似搜索找到相似任务ID，然后从JSON文件加载详细数据
        
        Args:
            task_description: 任务描述
            threshold: 相似度阈值（0-1）
            max_candidates: 最大候选任务数（默认20）
            
        Returns:
            相似任务列表 [(task_id, similarity, task_data), ...]
        """
        self.logger.info(f"查找相似任务，阈值: {threshold}, Top-K: {max_candidates}")
        
        # 检查向量数据库是否可用
        if not self.vector_db or not self.vector_db.is_available():
            self.logger.error("向量数据库不可用！请先运行: python migrate_to_vector_db.py")
            return []
        
        # 使用向量数据库检索
        return await self._find_with_vector_db(task_description, threshold, max_candidates)
    
    async def _find_with_vector_db(self,
                            task_description: str,
                            threshold: float,
                            max_candidates: int) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        使用向量数据库检索相似任务
        
        流程：向量近似搜索 → 获取相似任务ID → 从JSON加载详细数据
        
        Returns:
            相似任务列表 [(task_id, similarity, task_data), ...]
        """
        self.logger.info("🔍 向量数据库检索中...")
        
        # 快速检查：数据库是否为空
        try:
            stats = self.vector_db.get_stats()
            if not stats.get('available', False):
                self.logger.warning("向量数据库不可用，跳过检索")
                return []
            
            if stats.get('total_tasks', 0) == 0:
                self.logger.info("✓ 向量数据库为空，跳过检索")
                return []
        except Exception as e:
            self.logger.warning(f"向量数据库检查失败: {str(e)}，跳过检索")
            return []
        
        # 1. 计算查询embedding（直接await，不使用run_coroutine_threadsafe）
        self.logger.info("📊 计算查询embedding...")
        query_embedding = await self.llm_analyzer._get_embedding(task_description)
        self.logger.info(f"✓ Embedding计算完成，维度: {len(query_embedding)}")
        
        # 2. 向量近似搜索（快速找到候选ID）
        self.logger.info("🔎 执行向量搜索...")
        results = await self.vector_db.search_similar_tasks(query_embedding, top_k=max_candidates)
        self.logger.info(f"✓ 向量搜索完成，找到 {len(results)} 个候选")
        
        # 3. 过滤阈值 + 从JSON加载详细数据
        similar_tasks = []
        for result in results:
            if result['similarity'] >= threshold:
                flow_id = result['flow_id']
                task_id = result['metadata'].get('task_id', f"task_{flow_id}")
                
                # 向量库只存ID和metadata，真实数据在JSON中
                task_data = self._load_task_json(flow_id)
                if task_data:
                    similar_tasks.append((task_id, result['similarity'], task_data))
                else:
                    self.logger.warning(f"向量库中有记录但JSON文件缺失: {flow_id}")
        
        self.logger.info(f"✓ 向量检索完成: 找到 {len(similar_tasks)} 个相似任务（阈值≥{threshold}）")
        return similar_tasks
    
    
    def _load_task_json(self, flow_id: str) -> Optional[Dict[str, Any]]:
        """
        加载任务JSON数据
        
        Args:
            flow_id: Flow ID
            
        Returns:
            任务数据，如果文件不存在返回None
        """
        task_file = self.task_history_dir / f"task_{flow_id}.json"
        
        if not task_file.exists():
            self.logger.warning(f"任务文件不存在: {task_file}")
            return None
        
        try:
            with open(task_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"加载任务文件失败 ({task_file}): {str(e)}")
            return None
    
    def calculate_task_similarity(self, task1: str, task2: str) -> float:
        """
        使用embedding计算任务相似度（增强日志）
        
        Args:
            task1: 任务描述1
            task2: 任务描述2
            
        Returns:
            相似度（0-1）
        """
        if not self.llm_analyzer:
            similarity = difflib.SequenceMatcher(None, task1.lower(), task2.lower()).ratio()
            self.logger.debug(f"使用文本匹配: {similarity:.3f}")
            return similarity
        
        try:
            self.logger.debug(f"计算embedding相似度: '{task1[:50]}...' vs '{task2[:50]}...'")
            # 使用embedding计算语义相似度
            similarity = self.llm_analyzer.calculate_embedding_similarity_sync(task1, task2)
            self.logger.info(f"Embedding相似度: {similarity:.3f}")
            return similarity
            
        except Exception as e:
            self.logger.error(f"embedding相似度计算失败: {str(e)}")
            raise  # 直接抛出异常，不使用降级方案
    
    def extract_keywords(self, text: str) -> List[str]:
        """
        提取关键词（简化版本，主要用于向后兼容）
        
        Args:
            text: 文本
            
        Returns:
            关键词列表
        """
        # 简单的分词（按空格和标点分割）
        words = re.findall(r'\w+', text.lower())
        
        # 过滤短词
        keywords = [w for w in words if len(w) > 1]
        
        return keywords[:10]  # 限制数量
    
    def save_task_mapping(self,
                         task_description: str,
                         plan_json: Dict[str, Any],
                         success: bool) -> str:
        """
        保存任务映射（同时保存到JSON文件和向量数据库）
        
        Args:
            task_description: 任务描述
            plan_json: 工作流JSON
            success: 是否执行成功
            
        Returns:
            任务ID
        """
        try:
            # 生成任务ID
            flow_id = plan_json.get("flow_id", "unknown")
            task_id = f"task_{flow_id}"
            
            # 构建任务数据
            task_data = {
                "task_id": task_id,
                "flow_id": flow_id,
                "task_description": task_description,
                "plan_json": plan_json,
                "success": success,
                "created_at": plan_json.get("created_at", ""),
                "keywords": self.extract_keywords(task_description)
            }
            
            # 保存到JSON文件
            if self.storage_manager:
                self.storage_manager.save_task(flow_id, task_data)
            else:
                self.task_history_dir.mkdir(parents=True, exist_ok=True)
                task_file = self.task_history_dir / f"{task_id}.json"
                with open(task_file, 'w', encoding='utf-8') as f:
                    json.dump(task_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"✓ 任务映射已保存到JSON: {task_id}")
            
            # 同步到向量数据库
            if self.vector_db and self.vector_db.is_available():
                try:
                    import asyncio
                    
                    # 准备metadata
                    metadata = {
                        'task_id': task_id,
                        'success': success,
                        'created_at': plan_json.get("created_at", ""),
                        'app_name': plan_json.get("app_name", ""),
                        'steps_count': len(plan_json.get("steps", [])),
                        'complexity_level': plan_json.get("complexity_level", "")
                    }
                    
                    # 异步添加到向量库
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(
                            self.vector_db.add_task(flow_id, task_description, None, metadata)
                        )
                    else:
                        loop.run_until_complete(
                            self.vector_db.add_task(flow_id, task_description, None, metadata)
                        )
                    
                    self.logger.debug(f"✓ 任务已同步到向量库: {task_id}")
                    
                except Exception as e:
                    self.logger.warning(f"同步到向量库失败（不影响主流程）: {str(e)}")
            
            return task_id
            
        except Exception as e:
            self.logger.error(f"保存任务映射失败: {str(e)}")
            raise TaskMatchingError(f"保存任务映射失败: {str(e)}")
    
    def load_successful_plan(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        加载成功的plan
        
        Args:
            task_id: 任务ID
            
        Returns:
            plan JSON（如果找到且成功）
        """
        try:
            task_file = self.task_history_dir / f"{task_id}.json"
            
            if not task_file.exists():
                return None
            
            with open(task_file, 'r', encoding='utf-8') as f:
                task_data = json.load(f)
            
            # 只返回成功的plan
            if task_data.get("success", False):
                return task_data.get("plan_json")
            
            return None
            
        except Exception as e:
            self.logger.error(f"加载plan失败: {str(e)}")
            return None
    
    def get_task_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取任务历史
        
        Args:
            limit: 返回数量限制
            
        Returns:
            任务历史列表
        """
        try:
            # 获取所有任务文件（匹配task_flow_*.json格式）
            import os
            self.logger.info(f"[DEBUG] get_task_history called")
            self.logger.info(f"[DEBUG] Current working directory: {os.getcwd()}")
            self.logger.info(f"[DEBUG] task_history_dir (relative): {self.task_history_dir}")
            self.logger.info(f"[DEBUG] task_history_dir (absolute): {self.task_history_dir.absolute()}")
            self.logger.info(f"[DEBUG] task_history_dir exists: {self.task_history_dir.exists()}")
            self.logger.info(f"[DEBUG] Searching for pattern: task_flow_*.json")
            
            task_files = sorted(
                self.task_history_dir.glob("task_flow_*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            self.logger.info(f"[DEBUG] Found {len(task_files)} task files")
            if len(task_files) > 0:
                self.logger.info(f"[DEBUG] First 3 files: {[f.name for f in task_files[:3]]}")
            
            # 加载任务
            tasks = []
            for task_file in task_files[:limit]:
                try:
                    with open(task_file, 'r', encoding='utf-8') as f:
                        task_data = json.load(f)
                    
                    # 提取关键字段到顶层，方便前端使用
                    if "plan_json" in task_data:
                        plan_json = task_data["plan_json"]
                        # 提取original_query到顶层
                        if "original_query" in plan_json:
                            task_data["original_query"] = plan_json["original_query"]
                        # 提取steps数量
                        if "steps" in plan_json:
                            task_data["steps_count"] = len(plan_json["steps"])
                        # 从task_description中提取app_name（如果存在"目标应用:"）
                        if "task_description" in task_data:
                            desc = task_data["task_description"]
                            if "目标应用:" in desc:
                                # 提取"目标应用: XXX"中的XXX
                                import re
                                match = re.search(r'目标应用:\s*([^\n(]+)', desc)
                                if match:
                                    task_data["app_name"] = match.group(1).strip()
                    
                    tasks.append(task_data)
                except Exception as e:
                    self.logger.warning(f"加载任务文件失败 {task_file}: {str(e)}")
            
            self.logger.info(f"[DEBUG] Returning {len(tasks)} tasks")
            return tasks
            
        except Exception as e:
            self.logger.error(f"获取任务历史失败: {str(e)}")
            return []
    
    async def get_best_match(self, task_description: str, threshold: float = 0.8) -> Optional[Tuple[str, float, Dict[str, Any]]]:
        """
        获取最佳匹配任务
        
        Args:
            task_description: 任务描述
            threshold: 相似度阈值
            
        Returns:
            最佳匹配 (task_id, similarity, task_data) 或 None
        """
        similar_tasks = await self.find_similar_tasks(task_description, threshold)
        
        if similar_tasks:
            # 返回相似度最高的成功任务
            for task_id, similarity, task_data in similar_tasks:
                if task_data.get("success", False):
                    return (task_id, similarity, task_data)
        
        return None
    
    def clear_history(self) -> int:
        """
        清理任务历史
        
        Returns:
            删除的文件数量
        """
        count = 0
        for task_file in self.task_history_dir.glob("task_*.json"):
            try:
                task_file.unlink()
                count += 1
            except Exception as e:
                self.logger.warning(f"删除任务文件失败 {task_file}: {str(e)}")
        
        self.logger.info(f"清理了 {count} 个任务历史文件")
        return count
    
    def find_exact_match_plan(self, task_description: str) -> Optional[Dict[str, Any]]:
        """
        查找完全匹配的任务plan，用于快速复用
        使用normalize_task_description确保匹配准确性
        
        Args:
            task_description: 任务描述
            
        Returns:
            匹配的plan JSON，如果未找到返回None
        """
        try:
            # 标准化任务描述
            if self.storage_manager:
                normalized = self.storage_manager.normalize_task_description(task_description)
            else:
                # 向后兼容：简单标准化
                import re
                normalized = re.sub(r'\s+', ' ', task_description.strip()).lower()
            
            # 遍历所有任务，找到标准化后完全匹配的
            for task_file in self.task_history_dir.glob("task_*.json"):
                try:
                    # 从文件名提取flow_id
                    flow_id = task_file.stem.replace("task_", "")
                    
                    # 加载任务数据
                    if self.storage_manager:
                        task_data = self.storage_manager.load_task(flow_id)
                    else:
                        # 向后兼容：直接读取
                        with open(task_file, 'r', encoding='utf-8') as f:
                            task_data = json.load(f)
                    
                    # 检查任务是否成功且有plan
                    if task_data and task_data.get("success") and "plan_json" in task_data:
                        saved_desc = task_data.get("task_description", "")
                        
                        # 标准化保存的任务描述
                        if self.storage_manager:
                            saved_normalized = self.storage_manager.normalize_task_description(saved_desc)
                        else:
                            import re
                            saved_normalized = re.sub(r'\s+', ' ', saved_desc.strip()).lower()
                        
                        # 完全匹配
                        if saved_normalized == normalized:
                            self.logger.info(f"找到完全匹配的任务: {flow_id}")
                            
                            # 优先从plans目录读取最新的plan（用户可能已编辑）
                            # 如果plans目录中没有，则使用task_history中的原始plan
                            if self.storage_manager:
                                plans_dir = self.storage_manager.get_path("plans")
                                plan_file = plans_dir / f"{flow_id}.json"
                                if plan_file.exists():
                                    try:
                                        with open(plan_file, 'r', encoding='utf-8') as f:
                                            latest_plan = json.load(f)
                                        self.logger.info(f"✓ 使用plans目录中的最新plan: {flow_id}")
                                        return latest_plan
                                    except Exception as e:
                                        self.logger.warning(f"读取plans目录中的plan失败，使用task_history中的原始plan: {e}")
                            
                            # Fallback: 使用task_history中的原始plan
                            return task_data.get("plan_json")
                
                except Exception as e:
                    self.logger.warning(f"读取任务文件失败 {task_file}: {str(e)}")
                    continue
            
            self.logger.debug(f"未找到完全匹配的任务")
            return None
            
        except Exception as e:
            self.logger.error(f"查找精确匹配plan失败: {str(e)}")
            return None


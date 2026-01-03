"""
ACE上下文管理器
管理上下文条目的加载、保存、检索和评分
"""
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import Counter

from planscope.ace.context_entry import ContextEntry, ContextEntryType
from planscope.core.exceptions import ACEContextError


class ContextManager:
    """
    上下文管理器
    
    负责管理ACE上下文条目的生命周期
    """
    
    def __init__(self, context_dir: str, llm_analyzer=None, storage_manager=None):
        """
        初始化上下文管理器
        
        Args:
            context_dir: 上下文存储目录（向后兼容，优先使用storage_manager）
            llm_analyzer: LLM分析器（可选，用于智能判断）
            storage_manager: 存储管理器（可选，推荐使用）
        """
        self.storage_manager = storage_manager
        
        # 如果有storage_manager，使用它的路径；否则使用传入的context_dir
        if storage_manager:
            self.context_dir = storage_manager.get_path("contexts")
        else:
            self.context_dir = Path(context_dir)
            self.context_dir.mkdir(parents=True, exist_ok=True)
        
        # LLM分析器
        self.llm_analyzer = llm_analyzer
        
        # Logger（从llm_analyzer获取，如果有的话）
        if llm_analyzer and hasattr(llm_analyzer, 'logger'):
            self.logger = llm_analyzer.logger
        else:
            # 创建一个简单的logger
            import logging
            self.logger = logging.getLogger("ace.context_manager")
        
        # 缓存：{task_type: [ContextEntry]}
        self._cache: Dict[str, List[ContextEntry]] = {}
    
    def load_context(self, task_type: str) -> List[ContextEntry]:
        """
        加载指定类型的上下文
        
        Args:
            task_type: 任务类型
            
        Returns:
            上下文条目列表
        """
        # 检查缓存
        if task_type in self._cache:
            return self._cache[task_type]
        
        # 从文件加载（通过StorageManager）
        try:
            if self.storage_manager:
                data = self.storage_manager.load_context(task_type)
            else:
                # 向后兼容：直接读取文件
                context_file = self.context_dir / f"{task_type}.json"
                if not context_file.exists():
                    self._cache[task_type] = []
                    return []
                with open(context_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            
            if not data:
                self._cache[task_type] = []
                return []
            
            entries = [ContextEntry.from_dict(entry_data) for entry_data in data]
            self._cache[task_type] = entries
            return entries
            
        except Exception as e:
            raise ACEContextError(f"加载上下文失败: {str(e)}")
    
    def save_context(self, task_type: str, entries: List[ContextEntry]) -> None:
        """
        保存上下文
        
        Args:
            task_type: 任务类型
            entries: 上下文条目列表
        """
        try:
            if self.storage_manager:
                # 通过StorageManager保存
                self.storage_manager.save_context(task_type, entries)
            else:
                # 向后兼容：直接写文件
                context_file = self.context_dir / f"{task_type}.json"
                data = [entry.to_dict() for entry in entries]
                with open(context_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 更新缓存
            self._cache[task_type] = entries
            
        except Exception as e:
            raise ACEContextError(f"保存上下文失败: {str(e)}")
    
    def add_entry(self, task_type: str, entry: ContextEntry) -> None:
        """
        添加条目
        
        Args:
            task_type: 任务类型
            entry: 上下文条目
        """
        entries = self.load_context(task_type)
        entries.append(entry)
        self.save_context(task_type, entries)
    
    def update_entry(self, entry_id: str, updates: Dict[str, Any], task_type: Optional[str] = None) -> bool:
        """
        更新条目
        
        Args:
            entry_id: 条目ID
            updates: 更新的字段
            task_type: 任务类型（如果为None则搜索所有类型）
            
        Returns:
            是否更新成功
        """
        # 如果指定了task_type，只在该类型中查找
        if task_type:
            task_types = [task_type]
        else:
            # 搜索所有类型
            task_types = [f.stem for f in self.context_dir.glob("*.json")]
        
        for tt in task_types:
            entries = self.load_context(tt)
            for entry in entries:
                if entry.entry_id == entry_id:
                    # 更新字段
                    for key, value in updates.items():
                        if hasattr(entry, key):
                            setattr(entry, key, value)
                        elif key in entry.metadata:
                            entry.metadata[key] = value
                    
                    self.save_context(tt, entries)
                    return True
        
        return False
    
    def delete_entry(self, entry_id: str, task_type: Optional[str] = None) -> bool:
        """
        删除条目
        
        Args:
            entry_id: 条目ID
            task_type: 任务类型（如果为None则搜索所有类型）
            
        Returns:
            是否删除成功
        """
        # 如果指定了task_type，只在该类型中查找
        if task_type:
            task_types = [task_type]
        else:
            # 搜索所有类型
            task_types = [f.stem for f in self.context_dir.glob("*.json")]
        
        for tt in task_types:
            entries = self.load_context(tt)
            for i, entry in enumerate(entries):
                if entry.entry_id == entry_id:
                    entries.pop(i)
                    self.save_context(tt, entries)
                    return True
        
        return False
    
    async def retrieve_relevant_entries_async(self,
                                             task_description: str,
                                             task_type: Optional[str] = None,
                                             top_k: int = 5) -> List[ContextEntry]:
        """
        检索相关上下文条目（异步版本）
        
        Args:
            task_description: 任务描述
            task_type: 任务类型（如果为None则自动识别）
            top_k: 返回前K个最相关的条目
            
        Returns:
            相关的上下文条目列表
        """
        try:
            # 识别任务类型（异步）
            if task_type is None:
                task_type = await self.identify_task_type_async(task_description)
            
            # 加载上下文
            entries = self.load_context(task_type)
            
            if not entries:
                return []
            
            # 提取关键词（异步）
            keywords = await self._extract_keywords_async(task_description)
            
            # 计算相关性得分（结合相似度和评分权重）
            scored_entries = []
            for entry in entries:
                try:
                    # 基础相似度得分（异步）
                    similarity_score = await self._calculate_relevance_async(entry, keywords, task_description)
                    
                    # 计算评分权重
                    # score_weight = (useful_count - harmful_count) / (useful_count + harmful_count + 1)
                    # 范围: [-1, 1]，归一化到 [0, 1]
                    useful_count = entry.metadata.get("useful_count", 0)
                    harmful_count = entry.metadata.get("harmful_count", 0)
                    total_feedback = useful_count + harmful_count
                    if total_feedback > 0:
                        score_weight = (useful_count - harmful_count) / (total_feedback + 1)
                        score_weight = (score_weight + 1) / 2  # 归一化到 [0, 1]
                    else:
                        score_weight = 0.5  # 无反馈时，中性权重
                    
                    # 综合得分：相似度70% + 评分权重30%
                    final_score = similarity_score * 0.7 + score_weight * 0.3
                    
                    scored_entries.append((entry, final_score))
                except Exception as e:
                    # 单个条目相关性计算失败，记录日志但继续处理其他条目
                    self.logger.warning(f"计算条目 {entry.entry_id} 相关性失败: {e}")
                    continue
            
            # 排序并返回top_k
            scored_entries.sort(key=lambda x: x[1], reverse=True)
            return [entry for entry, score in scored_entries[:top_k]]
            
        except Exception as e:
            # 整个检索过程失败，记录错误并抛出异常
            self.logger.error(f"检索上下文失败: {e}", exc_info=True)
            raise RuntimeError(f"上下文检索失败: {e}") from e
    
    def load_memory_as_context(self, task_type: str) -> List[ContextEntry]:
        """
        从Memory QA记录中加载上下文
        只加载标记为'correct'的记录
        
        Args:
            task_type: 任务类型
            
        Returns:
            上下文条目列表
        """
        from pathlib import Path
        import json
        
        memory_dir = Path("service/data/memories/qa_records")
        if not memory_dir.exists():
            return []
        
        entries = []
        for qa_file in memory_dir.glob("qa_*.json"):
            try:
                with open(qa_file, 'r', encoding='utf-8') as f:
                    qa_record = json.load(f)
                
                # 只使用标记为correct的记录
                if qa_record.get("status") != "correct":
                    continue
                
                # 转换为ContextEntry
                entry = ContextEntry(
                    entry_type=ContextEntryType.TOOL_USAGE,
                    task_type=task_type,  # 使用传入的task_type
                    tool_name=qa_record.get("tool_name", "general_llm_processor"),
                    successful=True,
                    optimized_prompt=qa_record.get("prompt"),
                    timestamp=qa_record.get("created_at"),
                    source="user_memory"
                )
                entries.append(entry)
            except Exception as e:
                self.logger.warning(f"加载Memory记录失败 {qa_file}: {e}")
                continue
        
        self.logger.info(f"从Memory加载了 {len(entries)} 个标记为correct的记录")
        return entries
    
    def retrieve_relevant_entries(self,
                                 task_description: str,
                                 task_type: Optional[str] = None,
                                 top_k: int = 5) -> List[ContextEntry]:
        """
        检索相关上下文条目
        
        Args:
            task_description: 任务描述
            task_type: 任务类型（如果为None则自动识别）
            top_k: 返回前K个最相关的条目
            
        Returns:
            相关的上下文条目列表
        """
        try:
            # 识别任务类型
            if task_type is None:
                task_type = self.identify_task_type(task_description)
            
            # 加载上下文
            entries = self.load_context(task_type)
            
            if not entries:
                return []
            
            # 提取关键词
            keywords = self._extract_keywords(task_description)
            
            # 计算相关性得分（结合相似度和评分权重）
            scored_entries = []
            for entry in entries:
                try:
                    # 基础相似度得分
                    similarity_score = self._calculate_relevance(entry, keywords, task_description)
                    
                    # 计算评分权重
                    # score_weight = (useful_count - harmful_count) / (useful_count + harmful_count + 1)
                    # 范围: [-1, 1]，归一化到 [0, 1]
                    # 修复：从metadata中获取useful_count和harmful_count
                    useful_count = entry.metadata.get('useful_count', 0)
                    harmful_count = entry.metadata.get('harmful_count', 0)
                    total_feedback = useful_count + harmful_count
                    if total_feedback > 0:
                        score_weight = (useful_count - harmful_count) / (total_feedback + 1)
                        score_weight = (score_weight + 1) / 2  # 归一化到 [0, 1]
                    else:
                        score_weight = 0.5  # 无反馈时，中性权重
                    
                    # 综合得分：相似度70% + 评分权重30%
                    final_score = similarity_score * 0.7 + score_weight * 0.3
                    
                    scored_entries.append((entry, final_score))
                except Exception as e:
                    # 单个条目相关性计算失败，记录日志但继续处理其他条目
                    self.logger.warning(f"计算条目 {entry.entry_id} 相关性失败: {e}")
                    continue
            
            # 排序并返回top_k
            scored_entries.sort(key=lambda x: x[1], reverse=True)
            return [entry for entry, score in scored_entries[:top_k]]
            
        except Exception as e:
            # 整个检索过程失败，记录错误并返回空列表
            # 不使用降级方案，直接抛出异常让上层处理
            self.logger.error(f"检索上下文失败: {e}", exc_info=True)
            raise RuntimeError(f"上下文检索失败: {e}") from e
    
    def identify_task_type(self, task_description: str) -> str:
        """
        使用LLM识别任务类型（同步版本）
        
        Args:
            task_description: 任务描述
            
        Returns:
            任务类型字符串（格式：primary_category-sub_category）
        """
        if not self.llm_analyzer:
            raise RuntimeError("LLMAnalyzer未初始化，无法识别任务类型")
        
        prompt = f'''分析以下任务并识别其类型。

任务描述：{task_description}

请返回JSON格式：
{{
  "primary_category": "主类别",
  "sub_category": "子类别",
  "confidence": 0.95,
  "reasoning": "分类原因"
}}

【任务类型定义】：

**1. chat_analysis（聊天分析）**
- sub_category选项：
  - wechat_extraction: 微信聊天记录提取
  - qq_extraction: QQ聊天记录提取
  - general_chat: 其他聊天工具分析

**2. text_generation（文本生成）**
- sub_category选项：
  - continuation: 续写/接续写作（在原文基础上继续创作）
  - rewrite: 改写/润色（修改原文表达）
  - summarize: 摘要/总结
  - expansion: 扩展/详细化
  - translation: 翻译

**3. document_analysis（文档分析）**
- sub_category选项：
  - pdf_extraction: PDF文档提取
  - image_ocr: 图像文字识别
  - table_extraction: 表格提取
  - general_doc: 通用文档分析

**4. image_processing（图像处理）**
- sub_category选项：
  - content_extraction: 图像内容提取
  - screenshot_analysis: 截图分析
  - visual_qa: 图像问答

**5. automation（自动化操作）**
- sub_category选项：
  - ui_automation: 界面自动化
  - workflow_automation: 工作流自动化

**6. general（通用任务）**
- sub_category: other

【识别要点】：
- 根据任务的**核心意图**而非关键词进行分类
- "续写"、"接着写"、"继续写" → text_generation/continuation
- "微信"、"QQ"、"聊天记录" → chat_analysis/wechat_extraction或qq_extraction
- "提取图片文字"、"识别图片内容" → image_processing/content_extraction
- confidence表示分类的置信度（0-1之间）

只返回JSON，不要其他文字。'''
        
        # 使用标准化的任务描述生成缓存key，避免相同任务产生不同缓存
        if self.storage_manager:
            normalized = self.storage_manager.normalize_task_description(task_description)
        else:
            # 向后兼容：简单标准化
            normalized = re.sub(r'\s+', ' ', task_description.strip()).lower()
        cache_key = f"task_type_{hash(normalized)}"
        
        result = self.llm_analyzer.analyze_with_cache_sync(
            prompt=prompt,
            cache_key=cache_key,
            use_embedding_match=True,
            similarity_threshold=0.95
        )
        
        # 将字典转换为可哈希的字符串key
        if isinstance(result, dict):
            primary = result.get("primary_category", "general")
            sub = result.get("sub_category", "")
            return f"{primary}-{sub}" if sub else primary
        else:
            return "general"
    
    async def identify_task_type_async(self, task_description: str) -> str:
        """
        使用LLM识别任务类型（异步版本）
        
        Args:
            task_description: 任务描述
            
        Returns:
            任务类型字符串（格式：primary_category-sub_category）
        """
        if not self.llm_analyzer:
            raise RuntimeError("LLMAnalyzer未初始化，无法识别任务类型")
        
        prompt = f'''分析以下任务并识别其类型。

任务描述：{task_description}

请返回JSON格式：
{{
  "primary_category": "主类别",
  "sub_category": "子类别",
  "confidence": 0.95,
  "reasoning": "分类原因"
}}

【任务类型定义】：

**1. chat_analysis（聊天分析）**
- sub_category选项：
  - wechat_extraction: 微信聊天记录提取
  - qq_extraction: QQ聊天记录提取
  - general_chat: 其他聊天工具分析

**2. text_generation（文本生成）**
- sub_category选项：
  - continuation: 续写/接续写作（在原文基础上继续创作）
  - rewrite: 改写/润色（修改原文表达）
  - summarize: 摘要/总结
  - expansion: 扩展/详细化
  - translation: 翻译

**3. document_analysis（文档分析）**
- sub_category选项：
  - pdf_extraction: PDF文档提取
  - image_ocr: 图像文字识别
  - table_extraction: 表格提取
  - general_doc: 通用文档分析

**4. image_processing（图像处理）**
- sub_category选项：
  - content_extraction: 图像内容提取
  - screenshot_analysis: 截图分析
  - visual_qa: 图像问答

**5. automation（自动化操作）**
- sub_category选项：
  - ui_automation: 界面自动化
  - workflow_automation: 工作流自动化

**6. general（通用任务）**
- sub_category: other

【识别要点】：
- 根据任务的**核心意图**而非关键词进行分类
- "续写"、"接着写"、"继续写" → text_generation/continuation
- "微信"、"QQ"、"聊天记录" → chat_analysis/wechat_extraction或qq_extraction
- "提取图片文字"、"识别图片内容" → image_processing/content_extraction
- confidence表示分类的置信度（0-1之间）

只返回JSON，不要其他文字。'''
        
        # 使用标准化的任务描述生成缓存key，避免相同任务产生不同缓存
        if self.storage_manager:
            normalized = self.storage_manager.normalize_task_description(task_description)
        else:
            # 向后兼容：简单标准化
            normalized = re.sub(r'\s+', ' ', task_description.strip()).lower()
        cache_key = f"task_type_{hash(normalized)}"
        
        result = await self.llm_analyzer.analyze_with_cache(
            prompt=prompt,
            cache_key=cache_key,
            use_embedding_match=True,
            similarity_threshold=0.95
        )
        
        # 将字典转换为可哈希的字符串key
        if isinstance(result, dict):
            primary = result.get("primary_category", "general")
            sub = result.get("sub_category", "")
            return f"{primary}-{sub}" if sub else primary
        else:
            return "general"
    
    async def _extract_keywords_async(self, text: str) -> List[str]:
        """
        使用LLM提取关键词（异步版本）
        
        Args:
            text: 文本
            
        Returns:
            关键词列表
        """
        if not self.llm_analyzer:
            raise RuntimeError("LLMAnalyzer未初始化，无法提取关键词")
        
        prompt = f'''从以下文本中提取5-10个最重要的关键词。

文本：{text}

返回JSON格式：
{{
  "keywords": ["关键词1", "关键词2", ...],
  "reasoning": "提取原因"
}}

只返回JSON。'''
        
        cache_key = f"keywords_{hash(text)}"
        
        result = await self.llm_analyzer.analyze_with_cache(
            prompt=prompt,
            cache_key=cache_key,
            use_embedding_match=False  # 关键词提取不使用embedding匹配
        )
        
        return result.get("keywords", [])
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        使用LLM提取关键词
        
        Args:
            text: 文本
            
        Returns:
            关键词列表
        """
        if not self.llm_analyzer:
            raise RuntimeError("LLMAnalyzer未初始化，无法提取关键词")
        
        prompt = f'''从以下文本中提取5-10个最重要的关键词。

文本：{text}

返回JSON格式：
{{
  "keywords": ["关键词1", "关键词2", ...],
  "reasoning": "提取原因"
}}

只返回JSON。'''
        
        cache_key = f"keywords_{hash(text)}"
        
        result = self.llm_analyzer.analyze_with_cache_sync(
            prompt=prompt,
            cache_key=cache_key,
            use_embedding_match=False  # 关键词提取不使用embedding匹配
        )
        
        return result.get("keywords", [])
    
    async def _calculate_relevance_async(self,
                                        entry: ContextEntry,
                                        keywords: List[str],
                                        task_description: str) -> float:
        """
        使用embedding计算语义相关性（异步版本）
        
        Args:
            entry: 上下文条目
            keywords: 任务关键词
            task_description: 任务描述
            
        Returns:
            相关性得分
        """
        if not self.llm_analyzer:
            raise RuntimeError("LLMAnalyzer未初始化，无法计算相关性")
        
        # 使用embedding计算语义相似度（异步）
        entry_text = entry.content[:500]  # 限制长度
        similarity = await self.llm_analyzer.calculate_embedding_similarity(
            task_description,
            entry_text
        )
        
        # 结合条目评分进行调整
        entry_score = entry.metadata.get("score", 0)
        # 归一化到0-0.2的范围
        score_bonus = max(0, min(0.2, (entry_score + 5) / 50))
        
        # 最终得分 = embedding相似度(0-1) + 评分奖励(0-0.2)
        final_score = similarity + score_bonus
        
        return min(1.0, final_score)  # 确保不超过1.0
    
    def _calculate_relevance(self,
                            entry: ContextEntry,
                            keywords: List[str],
                            task_description: str) -> float:
        """
        使用embedding计算语义相关性
        
        Args:
            entry: 上下文条目
            keywords: 任务关键词
            task_description: 任务描述
            
        Returns:
            相关性得分
        """
        if not self.llm_analyzer:
            raise RuntimeError("LLMAnalyzer未初始化，无法计算相关性")
        
        # 使用embedding计算语义相似度
        entry_text = entry.content[:500]  # 限制长度
        similarity = self.llm_analyzer.calculate_embedding_similarity_sync(
            task_description,
            entry_text
        )
        
        # 结合条目评分进行调整
        entry_score = entry.metadata.get("score", 0)
        # 归一化到0-0.2的范围
        score_bonus = max(0, min(0.2, (entry_score + 5) / 50))
        
        # 最终得分 = embedding相似度(0-1) + 评分奖励(0-0.2)
        final_score = similarity + score_bonus
        
        return min(1.0, final_score)  # 确保不超过1.0
    
    def cleanup_low_score_entries(self, threshold: int = -3) -> int:
        """
        清理低分条目
        
        Args:
            threshold: 评分阈值（低于此值的条目将被删除）
            
        Returns:
            删除的条目数量
        """
        deleted_count = 0
        
        # 遍历所有任务类型
        for context_file in self.context_dir.glob("*.json"):
            task_type = context_file.stem
            entries = self.load_context(task_type)
            
            # 过滤低分条目
            filtered_entries = [
                entry for entry in entries
                if entry.metadata.get("score", 0) >= threshold
            ]
            
            deleted_count += len(entries) - len(filtered_entries)
            
            # 保存
            if len(filtered_entries) < len(entries):
                self.save_context(task_type, filtered_entries)
        
        return deleted_count
    
    def get_all_entries(self, task_type: Optional[str] = None) -> List[ContextEntry]:
        """
        获取所有条目
        
        Args:
            task_type: 任务类型（如果为None则返回所有类型）
            
        Returns:
            条目列表
        """
        if task_type:
            return self.load_context(task_type)
        
        # 返回所有类型的条目
        all_entries = []
        for context_file in self.context_dir.glob("*.json"):
            tt = context_file.stem
            entries = self.load_context(tt)
            all_entries.extend(entries)
        
        return all_entries
    
    def get_entry_by_id(self, entry_id: str) -> Optional[ContextEntry]:
        """
        根据ID获取条目
        
        Args:
            entry_id: 条目ID
            
        Returns:
            条目（如果找到）
        """
        all_entries = self.get_all_entries()
        for entry in all_entries:
            if entry.entry_id == entry_id:
                return entry
        return None
    
    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()


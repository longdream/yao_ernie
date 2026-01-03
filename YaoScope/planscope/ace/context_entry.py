"""
ACE上下文条目数据结构
定义上下文条目的类型、内容和元数据
"""
import uuid
import time
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime


class ContextEntryType(Enum):
    """上下文条目类型"""
    STRATEGY = "strategy"              # 成功的流程策略
    KNOWLEDGE = "knowledge"            # 领域知识
    ERROR_PATTERN = "error_pattern"    # 错误的流程模式（流程失败）
    TOOL_USAGE = "tool_usage"          # 工具最佳实践（工具失败）


class ContextEntry:
    """
    上下文条目
    
    表示一个可复用的经验、策略或知识
    """
    
    def __init__(self,
                 entry_id: Optional[str] = None,
                 entry_type: ContextEntryType = ContextEntryType.STRATEGY,
                 content: str = "",
                 metadata: Optional[Dict[str, Any]] = None,
                 examples: Optional[List[Dict[str, Any]]] = None):
        """
        初始化上下文条目
        
        Args:
            entry_id: 条目唯一标识符（如果为None则自动生成）
            entry_type: 条目类型
            content: 条目内容（策略描述、知识等）
            metadata: 元数据
            examples: 示例列表
        """
        self.entry_id = entry_id or str(uuid.uuid4())
        self.entry_type = entry_type
        self.content = content
        
        # 初始化元数据
        if metadata is None:
            self.metadata = {
                "created_at": datetime.now().isoformat(),
                "last_used": datetime.now().isoformat(),
                # 评分机制：用于ACE学习和优化
                # useful_count: 条目被标记为有用的次数
                # harmful_count: 条目被标记为有害的次数
                # 在检索时，评分权重会影响条目的排序
                # score_weight = (useful_count - harmful_count) / (useful_count + harmful_count + 1)
                # final_score = similarity * 0.7 + score_weight * 0.3
                "useful_count": 0,
                "harmful_count": 0,
                "score": 0,
                "related_tools": [],
                "related_tasks": [],
                "source": "auto"  # auto 或 user
            }
        else:
            self.metadata = metadata
        
        # 初始化示例
        self.examples = examples or []
    
    def to_dict(self) -> Dict[str, Any]:
        """
        序列化为字典
        
        Returns:
            字典表示
        """
        return {
            "entry_id": self.entry_id,
            "type": self.entry_type.value,
            "content": self.content,
            "metadata": self.metadata,
            "examples": self.examples
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContextEntry':
        """
        从字典反序列化
        
        Args:
            data: 字典数据
            
        Returns:
            ContextEntry实例
        """
        entry_type = ContextEntryType(data.get("type", "strategy"))
        return cls(
            entry_id=data.get("entry_id"),
            entry_type=entry_type,
            content=data.get("content", ""),
            metadata=data.get("metadata", {}),
            examples=data.get("examples", [])
        )
    
    def update_score(self, is_useful: bool) -> None:
        """
        更新评分
        
        Args:
            is_useful: 是否有用（True为有用，False为有害）
        """
        if is_useful:
            self.metadata["useful_count"] += 1
        else:
            self.metadata["harmful_count"] += 1
        
        self.calculate_score()
    
    def calculate_score(self) -> int:
        """
        计算综合评分
        
        Returns:
            评分（有用次数 - 有害次数）
        """
        score = self.metadata["useful_count"] - self.metadata["harmful_count"]
        self.metadata["score"] = score
        return score
    
    def add_example(self, task: str, result: str, reasoning: str) -> None:
        """
        添加示例
        
        Args:
            task: 任务描述
            result: 结果（success/failure）
            reasoning: 原因分析
        """
        example = {
            "task": task,
            "result": result,
            "reasoning": reasoning,
            "timestamp": datetime.now().isoformat()
        }
        self.examples.append(example)
    
    def update_last_used(self) -> None:
        """更新最后使用时间"""
        self.metadata["last_used"] = datetime.now().isoformat()
    
    def add_related_tool(self, tool_name: str) -> None:
        """
        添加相关工具
        
        Args:
            tool_name: 工具名称
        """
        if tool_name not in self.metadata["related_tools"]:
            self.metadata["related_tools"].append(tool_name)
    
    def add_related_task(self, task_type: str) -> None:
        """
        添加相关任务类型
        
        Args:
            task_type: 任务类型
        """
        if task_type not in self.metadata["related_tasks"]:
            self.metadata["related_tasks"].append(task_type)
    
    @property
    def useful_count(self) -> int:
        """
        获取有用次数
        
        Returns:
            有用次数
        """
        return self.metadata.get("useful_count", 0)
    
    @property
    def harmful_count(self) -> int:
        """
        获取有害次数
        
        Returns:
            有害次数
        """
        return self.metadata.get("harmful_count", 0)
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"ContextEntry(id={self.entry_id[:8]}, type={self.entry_type.value}, score={self.metadata['score']})"


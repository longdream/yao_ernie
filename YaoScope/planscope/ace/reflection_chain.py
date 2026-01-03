"""
ACE反思链记录系统
记录完整的思考、分析、优化过程，便于调试和改进

职责说明：
- ReflectionChain：记录LLM输入输出和思考过程，用于调试和可视化（完整版）
- ExecutionTrace：记录执行结果和工具调用，用于ACEReflector分析失败原因和成功模式（完整版）

两者职责不同，都需要保持完整，互不冗余：
- ReflectionChain服务于开发者调试和可视化展示
- ExecutionTrace服务于ACE自动分析和学习

注意：ReflectionChain不再直接操作文件，文件操作由StorageManager统一管理
"""
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field


@dataclass
class ReflectionChainEntry:
    """反思链条目"""
    entry_id: str
    timestamp: str
    stage: str  # plan_generation, tool_execution, analysis, reflection, optimization
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    model_info: Dict[str, Any] = field(default_factory=dict)
    analysis: str = ""
    next_action: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class ReflectionChain:
    """
    ACE反思链
    
    记录完整的思考过程：
    1. Plan生成：输入prompt、输出plan
    2. 工具执行：输入参数、输出结果
    3. 质量分析：问题识别、根因分析
    4. 反思优化：优化方案、新prompt
    """
    
    def __init__(self, task_description: str, task_name: str = "default", chain_id: Optional[str] = None):
        """
        初始化反思链
        
        Args:
            task_description: 任务描述
            task_name: 任务名称
            chain_id: 链标识（可选，默认自动生成）
        """
        self.chain_id = chain_id or self._generate_chain_id()
        self.task_description = task_description
        self.task_name = task_name
        self.created_at = datetime.now().isoformat()
        self.entries: List[ReflectionChainEntry] = []
        self._entry_counter = 0
    
    def _generate_chain_id(self) -> str:
        """生成链标识"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"chain_{timestamp}_{uuid.uuid4().hex[:8]}"
    
    def _generate_entry_id(self) -> str:
        """生成条目标识"""
        self._entry_counter += 1
        return f"entry_{self._entry_counter:03d}"
    
    def add_entry(self,
                  stage: str,
                  input_data: Optional[Dict[str, Any]] = None,
                  output_data: Optional[Dict[str, Any]] = None,
                  model_info: Optional[Dict[str, Any]] = None,
                  analysis: str = "",
                  next_action: str = "") -> ReflectionChainEntry:
        """
        添加反思链条目
        
        Args:
            stage: 阶段名称
            input_data: 输入数据
            output_data: 输出数据
            model_info: 模型信息
            analysis: 分析结果
            next_action: 下一步动作
            
        Returns:
            创建的条目
        """
        entry = ReflectionChainEntry(
            entry_id=self._generate_entry_id(),
            timestamp=datetime.now().isoformat(),
            stage=stage,
            input_data=input_data or {},
            output_data=output_data or {},
            model_info=model_info or {},
            analysis=analysis,
            next_action=next_action
        )
        
        self.entries.append(entry)
        return entry
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "chain_id": self.chain_id,
            "task_description": self.task_description,
            "task_name": self.task_name,
            "created_at": self.created_at,
            "entries": [entry.to_dict() for entry in self.entries]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReflectionChain':
        """
        从字典数据重建对象
        
        Args:
            data: 反思链数据字典
            
        Returns:
            反思链对象
        """
        chain = cls(
            task_description=data["task_description"],
            task_name=data.get("task_name", "default"),
            chain_id=data["chain_id"]
        )
        chain.created_at = data["created_at"]
        
        # 重建条目
        for entry_data in data["entries"]:
            entry = ReflectionChainEntry(**entry_data)
            chain.entries.append(entry)
            # 更新计数器
            if entry.entry_id.startswith("entry_"):
                try:
                    num = int(entry.entry_id.split("_")[1])
                    chain._entry_counter = max(chain._entry_counter, num)
                except (ValueError, IndexError):
                    # entry_id格式不标准，跳过计数器更新
                    pass
        
        return chain
    
    def get_entries_by_stage(self, stage: str) -> List[ReflectionChainEntry]:
        """获取指定阶段的所有条目"""
        return [entry for entry in self.entries if entry.stage == stage]
    
    def get_last_entry(self, stage: Optional[str] = None) -> Optional[ReflectionChainEntry]:
        """获取最后一个条目（可选择指定阶段）"""
        if stage:
            entries = self.get_entries_by_stage(stage)
            return entries[-1] if entries else None
        return self.entries[-1] if self.entries else None
    
    def __repr__(self) -> str:
        return f"ReflectionChain(chain_id={self.chain_id}, entries={len(self.entries)})"


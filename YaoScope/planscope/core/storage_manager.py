"""
存储管理器 - 基于生命周期的四层架构
统一文件读写接口，各组件不再直接操作文件
"""
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional


class StorageManager:
    """
    存储管理器 - 四层架构
    
    - persistent/: 持久化数据（需备份，ACE学习）
    - cache/: 缓存数据（可重建，加速运行）
    - runtime/: 运行时数据（每次执行产生）
    - config/: 配置文件（静态配置）
    """
    
    def __init__(self, work_dir: str):
        """
        初始化存储管理器
        
        Args:
            work_dir: 工作目录
        """
        self.work_dir = Path(work_dir).absolute()  # 确保使用绝对路径
        self.work_dir.mkdir(parents=True, exist_ok=True)
        print(f"[StorageManager] work_dir: {self.work_dir}")
        
        # 四层架构目录定义
        self.dirs = {
            # 持久化层
            "persistent": self.work_dir / "persistent",
            "ace_knowledge": self.work_dir / "persistent" / "ace_knowledge",
            "contexts": self.work_dir / "persistent" / "ace_knowledge" / "contexts",
            "reflections": self.work_dir / "persistent" / "ace_knowledge" / "reflections",
            "traces": self.work_dir / "persistent" / "ace_knowledge" / "traces",
            "plans": self.work_dir / "persistent" / "plans",
            "tasks": self.work_dir / "persistent" / "tasks",
            
            # 缓存层
            "cache": self.work_dir / "cache",
            "llm_cache": self.work_dir / "cache" / "llm",
            "prompts": self.work_dir / "cache" / "prompts",
            "tools_cache": self.work_dir / "cache" / "tools",
            
            # 运行时层
            "runtime": self.work_dir / "runtime",
            "current": self.work_dir / "runtime" / "current",
            "runtime_outputs": self.work_dir / "runtime" / "current" / "outputs",
            "logs": Path("service/logs"),  # 集中日志到service/logs
            
            # 配置层
            "config": self.work_dir / "config",
            "tools": self.work_dir / "config" / "tools",
        }
        
        # 不再预创建所有目录，改为按需创建
    
    def get_path(self, key: str) -> Path:
        """
        获取目录路径
        
        Args:
            key: 目录键名
            
        Returns:
            目录路径
            
        Raises:
            ValueError: 未知的目录键
        """
        if key not in self.dirs:
            raise ValueError(f"未知的目录键: {key}")
        return self.dirs[key]
    
    # ==================== 持久化层方法 ====================
    
    def get_plan_file(self, flow_id: str) -> Path:
        """获取工作流文件路径"""
        return self.dirs["plans"] / f"{flow_id}.json"
    
    def get_task_file(self, flow_id: str) -> Path:
        """获取任务历史文件路径"""
        return self.dirs["tasks"] / f"task_{flow_id}.json"
    
    def get_context_file(self, task_type: str) -> Path:
        """获取上下文文件路径"""
        return self.dirs["contexts"] / f"{task_type}.json"
    
    def get_reflection_file(self, chain_id: str) -> Path:
        """获取持久化反思链文件路径"""
        return self.dirs["reflections"] / f"{chain_id}.json"
    
    # ==================== 缓存层方法 ====================
    
    def get_prompt_cache_dir(self, flow_id: str) -> Path:
        """获取Prompt缓存目录"""
        cache_dir = self.dirs["prompts"] / flow_id
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir
    
    def get_tool_config_dir(self, task_name: str) -> Path:
        """获取工具配置目录"""
        tool_dir = self.dirs["tools_cache"] / task_name
        tool_dir.mkdir(parents=True, exist_ok=True)
        return tool_dir
    
    # ==================== 运行时层方法 ====================
    
    def get_current_plan_file(self) -> Path:
        """获取当前执行的plan副本路径"""
        return self.dirs["current"] / "plan.json"
    
    def get_current_reflection_file(self, chain_id: str) -> Path:
        """获取当前执行的反思链路径"""
        return self.dirs["current"] / f"{chain_id}.json"
    
    def get_tool_output_file(self, tool_name: str, flow_id: str) -> Path:
        """获取工具输出文件路径"""
        return self.dirs["runtime_outputs"] / f"{tool_name}_{flow_id}.json"
    
    def cleanup_runtime(self) -> int:
        """
        清理运行时数据
        
        Returns:
            删除的文件数量
        """
        count = 0
        if self.dirs["current"].exists():
            for file in self.dirs["current"].glob("*"):
                if file.is_file():
                    file.unlink()
                    count += 1
        return count
    
    # ==================== 辅助方法 ====================
    
    def ensure_dir(self, path: Path) -> Path:
        """
        确保目录存在（按需创建）
        
        Args:
            path: 目录路径
            
        Returns:
            目录路径
        """
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def file_exists(self, file_path: Path) -> bool:
        """
        检查文件是否存在
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否存在
        """
        return file_path.exists()
    
    def list_files(self, directory: Path, pattern: str = "*.json") -> List[Path]:
        """
        列出目录下的文件
        
        Args:
            directory: 目录路径
            pattern: 文件模式（默认*.json）
            
        Returns:
            文件路径列表
        """
        if not directory.exists():
            return []
        return sorted(directory.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    
    def normalize_task_description(self, text: str) -> str:
        """
        标准化任务描述，用于生成稳定的缓存key
        
        Args:
            text: 任务描述
            
        Returns:
            标准化后的文本
        """
        # 去除多余空格
        text = re.sub(r'\s+', ' ', text.strip())
        # 去除路径中的具体文件名，保留扩展名
        text = re.sub(r'[A-Za-z]:\\[^\\]+\\', '', text)
        # 统一小写
        return text.lower()
    
    # ==================== 通用JSON读写 ====================
    
    def save_json(self, file_path: Path, data: Any) -> Path:
        """
        保存JSON文件（通用方法）
        
        Args:
            file_path: 文件路径
            data: 数据
            
        Returns:
            保存的文件路径
        """
        self.ensure_dir(file_path.parent)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return file_path
    
    def load_json(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        加载JSON文件（通用方法）
        
        Args:
            file_path: 文件路径
            
        Returns:
            数据（如果文件存在）
        """
        if not file_path.exists():
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    # ==================== 反思链 ====================
    
    def save_reflection_chain(self, chain) -> Path:
        """
        保存反思链（只保存到persistent）
        
        Args:
            chain: ReflectionChain对象
            
        Returns:
            保存的文件路径
        """
        file_path = self.get_reflection_file(chain.chain_id)
        return self.save_json(file_path, chain.to_dict())
    
    def load_reflection_chain(self, chain_id: str) -> Optional[Dict[str, Any]]:
        """
        加载反思链
        
        Args:
            chain_id: 反思链ID
            
        Returns:
            反思链数据
        """
        file_path = self.get_reflection_file(chain_id)
        return self.load_json(file_path)
    
    # ==================== 上下文 ====================
    
    def save_context(self, task_type: str, entries: List) -> Path:
        """
        保存上下文条目
        
        Args:
            task_type: 任务类型
            entries: 上下文条目列表（ContextEntry对象）
            
        Returns:
            保存的文件路径
        """
        file_path = self.get_context_file(task_type)
        data = [entry.to_dict() for entry in entries]
        return self.save_json(file_path, data)
    
    def load_context(self, task_type: str) -> Optional[List[Dict[str, Any]]]:
        """
        加载上下文条目
        
        Args:
            task_type: 任务类型
            
        Returns:
            上下文条目列表（dict格式）
        """
        file_path = self.get_context_file(task_type)
        return self.load_json(file_path)
    
    # ==================== 任务 ====================
    
    def save_task(self, flow_id: str, task_data: Dict[str, Any]) -> Path:
        """
        保存任务数据
        
        Args:
            flow_id: 工作流ID
            task_data: 任务数据
            
        Returns:
            保存的文件路径
        """
        file_path = self.get_task_file(flow_id)
        return self.save_json(file_path, task_data)
    
    def load_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        加载任务数据
        
        Args:
            task_id: 任务ID（可以是task_xxx或xxx）
            
        Returns:
            任务数据
        """
        # 兼容task_前缀
        if not task_id.startswith("task_"):
            task_id = f"task_{task_id}"
        file_path = self.dirs["tasks"] / f"{task_id}.json"
        return self.load_json(file_path)
    
    def load_all_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        加载所有任务历史
        
        Args:
            limit: 返回数量限制
            
        Returns:
            任务列表
        """
        task_files = self.list_files(self.dirs["tasks"], "task_*.json")
        tasks = []
        for task_file in task_files[:limit]:
            data = self.load_json(task_file)
            if data:
                tasks.append(data)
        return tasks
    
    # ==================== 执行轨迹 ====================
    
    def save_trace(self, trace_id: str, trace_data: Dict[str, Any]) -> Path:
        """
        保存执行轨迹
        
        Args:
            trace_id: 轨迹ID
            trace_data: 轨迹数据
            
        Returns:
            保存的文件路径
        """
        file_path = self.dirs["traces"] / f"trace_{trace_id}.json"
        return self.save_json(file_path, trace_data)
    
    def load_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """
        加载执行轨迹
        
        Args:
            trace_id: 轨迹ID
            
        Returns:
            轨迹数据
        """
        file_path = self.dirs["traces"] / f"trace_{trace_id}.json"
        return self.load_json(file_path)
    
    def load_recent_traces(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        加载最近的执行轨迹
        
        Args:
            limit: 返回数量限制
            
        Returns:
            轨迹列表
        """
        trace_files = self.list_files(self.dirs["traces"], "trace_*.json")
        traces = []
        for trace_file in trace_files[:limit]:
            data = self.load_json(trace_file)
            if data:
                traces.append(data)
        return traces
    
    # ==================== 工具元数据 ====================
    
    def save_tool_metadata(self, tool_name: str, metadata: Dict[str, Any]) -> Path:
        """
        保存工具元数据缓存
        
        Args:
            tool_name: 工具名称
            metadata: 元数据
            
        Returns:
            保存的文件路径
        """
        # 工具元数据保存到tools_cache目录
        file_path = self.dirs["tools_cache"] / f"{tool_name}_metadata.json"
        return self.save_json(file_path, metadata)
    
    def load_tool_metadata(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        加载工具元数据缓存
        
        Args:
            tool_name: 工具名称
            
        Returns:
            元数据
        """
        file_path = self.dirs["tools_cache"] / f"{tool_name}_metadata.json"
        return self.load_json(file_path)
    
    def load_all_tool_metadata(self) -> Dict[str, Dict[str, Any]]:
        """
        加载所有工具元数据
        
        Returns:
            工具名称 -> 元数据的字典
        """
        metadata_files = self.list_files(self.dirs["tools_cache"], "*_metadata.json")
        all_metadata = {}
        for file_path in metadata_files:
            tool_name = file_path.stem.replace("_metadata", "")
            data = self.load_json(file_path)
            if data:
                all_metadata[tool_name] = data
        return all_metadata
    
    # ==================== LLM缓存 ====================
    
    def save_llm_cache(self, cache_key: str, data: Dict[str, Any]) -> Path:
        """
        保存LLM缓存
        
        Args:
            cache_key: 缓存键
            data: 缓存数据
            
        Returns:
            保存的文件路径
        """
        file_path = self.dirs["llm_cache"] / f"{cache_key}.json"
        return self.save_json(file_path, data)
    
    def load_llm_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        加载LLM缓存
        
        Args:
            cache_key: 缓存键
            
        Returns:
            缓存数据
        """
        file_path = self.dirs["llm_cache"] / f"{cache_key}.json"
        return self.load_json(file_path)
    
    def save_embedding_cache(self, cache_data: Dict[str, Any]) -> Path:
        """
        保存embedding缓存
        
        Args:
            cache_data: embedding缓存数据
            
        Returns:
            保存的文件路径
        """
        file_path = self.dirs["llm_cache"] / "embeddings.json"
        return self.save_json(file_path, cache_data)
    
    def load_embedding_cache(self) -> Optional[Dict[str, Any]]:
        """
        加载embedding缓存
        
        Returns:
            embedding缓存数据
        """
        file_path = self.dirs["llm_cache"] / "embeddings.json"
        return self.load_json(file_path)
    
    # ==================== Prompt缓存 ====================
    
    def save_prompt_cache(self, flow_id: str, prompts_data: Dict[str, Any]) -> Path:
        """
        保存Prompt缓存
        
        Args:
            flow_id: 工作流ID
            prompts_data: prompt数据
            
        Returns:
            保存的文件路径
        """
        cache_dir = self.get_prompt_cache_dir(flow_id)
        file_path = cache_dir / "tool_prompts.json"
        return self.save_json(file_path, prompts_data)
    
    def load_prompt_cache(self, flow_id: str) -> Optional[Dict[str, Any]]:
        """
        加载Prompt缓存
        
        Args:
            flow_id: 工作流ID
            
        Returns:
            prompt数据
        """
        cache_dir = self.dirs["prompts"] / flow_id
        file_path = cache_dir / "tool_prompts.json"
        return self.load_json(file_path)
    
    # ==================== 工具输出 ====================
    
    def save_tool_output(self, tool_name: str, flow_id: str, output: Dict[str, Any]) -> Path:
        """
        保存工具输出
        
        Args:
            tool_name: 工具名称
            flow_id: 工作流ID
            output: 输出数据
            
        Returns:
            保存的文件路径
        """
        file_path = self.get_tool_output_file(tool_name, flow_id)
        return self.save_json(file_path, output)

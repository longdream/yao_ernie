"""
Plan级Prompt缓存管理器
负责保存和加载每个plan生成的prompt，避免重复生成
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any


class PromptCacheManager:
    """
    Plan级Prompt缓存管理器
    
    功能：
    1. 将LLM生成的prompt保存到plan对应的文件夹
    2. 加载缓存的prompt，避免重复生成
    3. 记录使用统计（usage_count、last_used等）
    
    目录结构：
    {work_dir}/plan_prompts/{flow_id}/
        ├── tool_prompts.json   # 工具prompt缓存
        ├── metadata.json       # 任务元数据
        └── usage_stats.json    # 使用统计
    """
    
    def __init__(self, work_dir: str, flow_id: Optional[str] = None, storage_manager=None):
        """
        初始化Prompt缓存管理器
        
        Args:
            work_dir: 工作目录
            flow_id: Plan的flow_id（如flow_1234567_abcd），如果为None则不创建目录
            storage_manager: 存储管理器（可选，优先使用）
        """
        self.work_dir = Path(work_dir)
        self.flow_id = flow_id
        
        # 使用storage_manager或默认路径
        if storage_manager:
            self.cache_base_dir = storage_manager.get_path("prompts")
        else:
            # Fallback: 与StorageManager的定义保持一致
            self.cache_base_dir = self.work_dir / "cache" / "prompts"
        
        if flow_id:
            self.plan_cache_dir = self.cache_base_dir / flow_id
            self.plan_cache_dir.mkdir(parents=True, exist_ok=True)
            
            self.prompts_file = self.plan_cache_dir / "tool_prompts.json"
            self.metadata_file = self.plan_cache_dir / "metadata.json"
            self.usage_stats_file = self.plan_cache_dir / "usage_stats.json"
        else:
            self.plan_cache_dir = None
            self.prompts_file = None
            self.metadata_file = None
            self.usage_stats_file = None
    
    def set_flow_id(self, flow_id: str):
        """
        设置flow_id并初始化目录
        
        Args:
            flow_id: Plan的flow_id
        """
        self.flow_id = flow_id
        self.plan_cache_dir = self.cache_base_dir / flow_id
        self.plan_cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.prompts_file = self.plan_cache_dir / "tool_prompts.json"
        self.metadata_file = self.plan_cache_dir / "metadata.json"
        self.usage_stats_file = self.plan_cache_dir / "usage_stats.json"
    
    def get_cached_prompt(self, tool_name: str) -> Optional[str]:
        """
        获取缓存的prompt
        
        Args:
            tool_name: 工具名称
            
        Returns:
            缓存的prompt，如果不存在返回None
        """
        if not self.prompts_file or not self.prompts_file.exists():
            return None
        
        try:
            with open(self.prompts_file, 'r', encoding='utf-8') as f:
                prompts_data = json.load(f)
            
            if tool_name in prompts_data:
                prompt_info = prompts_data[tool_name]
                # 更新最后使用时间
                prompt_info["last_used"] = datetime.now().isoformat()
                prompt_info["usage_count"] = prompt_info.get("usage_count", 0) + 1
                
                # 保存更新
                with open(self.prompts_file, 'w', encoding='utf-8') as f:
                    json.dump(prompts_data, f, ensure_ascii=False, indent=2)
                
                return prompt_info["prompt"]
            
            return None
            
        except Exception as e:
            # 缓存读取失败，返回None（不影响正常流程）
            return None
    
    def save_prompt(self, tool_name: str, prompt: str, generator: str = "llm", 
                   quality_score: float = 0.0, optimized_by_ace: bool = False):
        """
        保存生成的prompt
        
        Args:
            tool_name: 工具名称
            prompt: 生成的prompt内容
            generator: 生成器类型（llm/ace/manual）
            quality_score: 质量评分（0-1）
            optimized_by_ace: 是否被ACE优化过
        """
        if not self.prompts_file:
            return
        
        # 加载现有数据
        prompts_data = {}
        if self.prompts_file.exists():
            try:
                with open(self.prompts_file, 'r', encoding='utf-8') as f:
                    prompts_data = json.load(f)
            except:
                prompts_data = {}
        
        # 添加或更新prompt
        prompt_info = {
            "prompt": prompt,
            "generated_at": datetime.now().isoformat(),
            "generator": generator,
            "quality_score": quality_score,
            "usage_count": 1,
            "last_used": datetime.now().isoformat(),
            "optimized_by_ace": optimized_by_ace
        }
        
        if optimized_by_ace:
            prompt_info["ace_optimization_date"] = datetime.now().isoformat()
        
        prompts_data[tool_name] = prompt_info
        
        # 保存到文件
        with open(self.prompts_file, 'w', encoding='utf-8') as f:
            json.dump(prompts_data, f, ensure_ascii=False, indent=2)
    
    def update_usage_stats(self, tool_name: str, success: bool, execution_time: float = 0.0):
        """
        更新使用统计
        
        Args:
            tool_name: 工具名称
            success: 是否成功
            execution_time: 执行时间（秒）
        """
        if not self.usage_stats_file:
            return
        
        # 加载现有统计
        stats_data = {}
        if self.usage_stats_file.exists():
            try:
                with open(self.usage_stats_file, 'r', encoding='utf-8') as f:
                    stats_data = json.load(f)
            except:
                stats_data = {}
        
        # 更新统计
        if tool_name not in stats_data:
            stats_data[tool_name] = {
                "total_uses": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_execution_time": 0.0,
                "last_used": None
            }
        
        tool_stats = stats_data[tool_name]
        tool_stats["total_uses"] += 1
        if success:
            tool_stats["success_count"] += 1
        else:
            tool_stats["failure_count"] += 1
        tool_stats["total_execution_time"] += execution_time
        tool_stats["last_used"] = datetime.now().isoformat()
        
        # 保存统计
        with open(self.usage_stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats_data, f, ensure_ascii=False, indent=2)
    
    def get_all_prompts(self) -> Dict[str, str]:
        """
        获取所有缓存的prompts
        
        Returns:
            工具名 -> prompt内容的映射
        """
        if not self.prompts_file or not self.prompts_file.exists():
            return {}
        
        try:
            with open(self.prompts_file, 'r', encoding='utf-8') as f:
                prompts_data = json.load(f)
            
            return {
                tool_name: info["prompt"]
                for tool_name, info in prompts_data.items()
            }
        except:
            return {}
    
    def save_metadata(self, metadata: Dict[str, Any]):
        """
        保存任务元数据
        
        Args:
            metadata: 元数据字典
        """
        if not self.metadata_file:
            return
        
        metadata["updated_at"] = datetime.now().isoformat()
        
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        获取任务元数据
        
        Returns:
            元数据字典
        """
        if not self.metadata_file or not self.metadata_file.exists():
            return {}
        
        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def cleanup_old_caches(self, days: int = 30) -> int:
        """
        清理超过指定天数未使用的缓存
        
        Args:
            days: 天数阈值
            
        Returns:
            清理的缓存数量
        """
        if not self.cache_base_dir.exists():
            return 0
        
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=days)
        
        cleaned_count = 0
        for plan_dir in self.cache_base_dir.iterdir():
            if not plan_dir.is_dir():
                continue
            
            usage_stats_file = plan_dir / "usage_stats.json"
            if not usage_stats_file.exists():
                continue
            
            try:
                with open(usage_stats_file, 'r', encoding='utf-8') as f:
                    stats_data = json.load(f)
                
                # 检查所有工具的最后使用时间
                all_old = True
                for tool_stats in stats_data.values():
                    last_used_str = tool_stats.get("last_used")
                    if last_used_str:
                        last_used = datetime.fromisoformat(last_used_str)
                        if last_used > cutoff_date:
                            all_old = False
                            break
                
                # 如果所有工具都超过阈值，删除整个目录
                if all_old:
                    import shutil
                    shutil.rmtree(plan_dir)
                    cleaned_count += 1
                    
            except:
                continue
        
        return cleaned_count
    
    def update_tool_prompt(self, tool_name: str, new_prompt: str):
        """
        更新工具的Prompt缓存
        
        Args:
            tool_name: 工具名称
            new_prompt: 新的Prompt
        """
        if not self.prompts_file:
            return
        
        # 加载现有缓存
        prompts = {}
        if self.prompts_file.exists():
            with open(self.prompts_file, 'r', encoding='utf-8') as f:
                prompts = json.load(f)
        
        # 更新
        prompts[tool_name] = {
            "prompt": new_prompt,
            "updated_at": datetime.now().isoformat(),
            "source": "manual_edit"
        }
        
        # 保存
        with open(self.prompts_file, 'w', encoding='utf-8') as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)


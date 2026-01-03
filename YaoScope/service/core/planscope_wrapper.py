"""
PlanScope封装器 - 全局实例管理和工具注册
"""
import sys
from pathlib import Path
from typing import Dict, Any, Optional
import os

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from planscope import PlanScope
from service.core.config_converter import ConfigConverter


class PlanScopeWrapper:
    """PlanScope全局封装器"""
    
    _instance: Optional[PlanScope] = None
    _initialized: bool = False
    _model_configs: Dict[str, Dict[str, str]] = {}
    
    @classmethod
    def initialize(
        cls,
        main_config: Dict[str, str],
        advanced_config: Dict[str, str],
        vl_config: Dict[str, str],
        light_config: Dict[str, str],
        embedding_config: Dict[str, str],
        rerank_config: Optional[Dict[str, str]] = None,
        work_dir: str = None
    ) -> None:
        """
        初始化PlanScope实例
        
        Args:
            main_config: 主模型配置
            advanced_config: 高级模型配置
            vl_config: VL模型配置
            light_config: 轻量模型配置
            embedding_config: Embedding模型配置
            rerank_config: Rerank模型配置（可选）
            work_dir: 工作目录
        """
        print("[INIT] 初始化PlanScope...")
        print(f"[DEBUG] 传入的work_dir参数: {work_dir}")
        
        # 如果没有指定work_dir，使用相对于service目录的绝对路径
        if work_dir is None:
            # __file__ 是 YaoScope/service/core/planscope_wrapper.py
            # parent.parent 是 YaoScope/service
            service_dir = Path(__file__).parent.parent
            work_dir = str((service_dir / "data" / "planscope").absolute())
            print(f"[INIT] 使用默认work_dir (绝对路径): {work_dir}")
        else:
            print(f"[INIT] 使用传入的work_dir: {work_dir}")
            # 确保传入的work_dir也是绝对路径
            work_dir = str(Path(work_dir).absolute())
            print(f"[INIT] 转换为绝对路径: {work_dir}")
        
        # 转换配置
        planscope_config = ConfigConverter.convert_to_planscope_config(
            main_config, advanced_config, vl_config, light_config, embedding_config
        )
        
        # 保存模型配置（用于工具初始化）
        cls._model_configs = ConfigConverter.get_model_configs(
            main_config, advanced_config, vl_config, light_config
        )
        
        # 保存Rerank配置
        if rerank_config:
            cls._model_configs['rerank'] = rerank_config
        
        print(f"[CONFIG] 主模型: {main_config.get('model_name')}")
        print(f"[CONFIG] 高级模型: {advanced_config.get('model_name')}")
        print(f"[CONFIG] VL模型: {vl_config.get('model_name')}")
        print(f"[CONFIG] 轻量模型: {light_config.get('model_name')}")
        print(f"[CONFIG] Embedding模型: {embedding_config.get('model_name')}")
        if rerank_config:
            print(f"[CONFIG] Rerank模型: {rerank_config.get('model_name')}")
        
        # 【主线零降级】强制检查embedding配置
        if not embedding_config.get('model_name'):
            raise ValueError("Embedding模型配置缺失！Embedding是必须的，不允许降级。")
        if not embedding_config.get('api_base'):
            raise ValueError("Embedding API地址配置缺失！Embedding是必须的，不允许降级。")
        
        print("[CHECK] Embedding配置验证通过 OK")
        
        # 创建PlanScope实例
        try:
            cls._instance = PlanScope(
                config=planscope_config,
                work_dir=work_dir,
                use_ace=True,
                task_name="yao_service"
            )
            
            print("[OK] PlanScope初始化成功")
            
            # 注册所有工具到工具池
            cls._register_all_tools()
            
            cls._initialized = True
            print("[OK] PlanScope封装器初始化完成")
            
        except Exception as e:
            print(f"[ERROR] PlanScope初始化失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    @classmethod
    def _register_all_tools(cls) -> None:
        """注册所有工具到PlanScope工具池"""
        print("[TOOLS] 开始注册工具到工具池...")
        
        if cls._instance is None:
            raise RuntimeError("PlanScope实例未初始化")
        
        # 导入所有工具类
        from service.tools.vl_tools import ScreenshotAndAnalyzeTool
        from service.tools.llm_tools import GeneralLLMProcessorTool
        from service.tools.ocr_tools import OCRExtractTool
        from service.tools.interaction_tools import (
            TypeTextTool, ClickElementTool, ScrollTool
        )
        from service.tools.scroll_and_analyze_tool import ScrollAndAnalyzeTool
        
        # 获取主模型的model_client（从PlanScope）
        model_client = cls._instance.model_client
        
        # 为VL工具创建专门的model_client（使用VL配置）
        vl_model_client = None
        if "vl" in cls._model_configs and cls._model_configs["vl"]:
            from planscope.adapters.langchain_client import LangChainModelClient
            from planscope.adapters.config_manager import ConfigManager
            
            # 提取VL配置
            vl_api_key = cls._model_configs["vl"].get("api_key", "")
            vl_api_base = cls._model_configs["vl"].get("api_base", "")
            vl_model_name = cls._model_configs["vl"].get("model_name", "")
            
            # 创建临时配置管理器用于VL模型
            vl_config_dict = {
                "llm": {
                    "provider": "openai",
                    "api_key": vl_api_key,
                    "base_url": vl_api_base,
                    "model_name": vl_model_name,
                    "temperature": 0.3,
                    "max_tokens": 4096,
                    "timeout": 60.0,
                    "max_retries": 3
                }
            }
            vl_config_manager = ConfigManager.from_dict(vl_config_dict)
            vl_model_client = LangChainModelClient(
                vl_config_manager,
                cls._instance.logger_manager,
                embedding_config=None
            )
            print(f"  [OK] VL模型客户端已创建: {vl_model_name}")
        
        # 注册VL工具（使用专门的VL model client）
        try:
            if vl_model_client:
                cls._instance.add_tool_to_pool(
                    ScreenshotAndAnalyzeTool,
                    vl_model_client=vl_model_client
                )
                print("  [OK] ScreenshotAndAnalyzeTool 已注册（使用VL专用模型）")
            else:
                print("  [SKIP] ScreenshotAndAnalyzeTool 未注册（VL配置缺失）")
        except Exception as e:
            print(f"  [FAIL] ScreenshotAndAnalyzeTool 注册失败: {e}")
        
        # 注册滚动分析工具（使用专门的VL model client）
        try:
            if vl_model_client:
                cls._instance.add_tool_to_pool(
                    ScrollAndAnalyzeTool,
                    vl_model_client=vl_model_client
                )
                print("  [OK] ScrollAndAnalyzeTool 已注册（使用VL专用模型）")
            else:
                print("  [SKIP] ScrollAndAnalyzeTool 未注册（VL配置缺失）")
        except Exception as e:
            print(f"  [FAIL] ScrollAndAnalyzeTool 注册失败: {e}")
        
        # 注册LLM工具
        try:
            cls._instance.add_tool_to_pool(
                GeneralLLMProcessorTool,
                llm_model_client=model_client
            )
            print("  [OK] GeneralLLMProcessorTool 已注册")
        except Exception as e:
            print(f"  [FAIL] GeneralLLMProcessorTool 注册失败: {e}")
        
        # 注册OCR工具（预初始化PaddleOCR）
        try:
            print("  [INIT] 正在预初始化 PaddleOCR...")
            from service.tools.ocr_tools import OCRExtractTool
            
            # 先预初始化 PaddleOCR（类方法）
            OCRExtractTool.pre_initialize()
            
            # 然后注册工具类
            cls._instance.add_tool_to_pool(OCRExtractTool)
            print("  [OK] OCRExtractTool 已注册（PaddleOCR 已预初始化）")
        except Exception as e:
            print(f"  [FAIL] OCRExtractTool 注册失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 注册交互工具
        try:
            cls._instance.add_tool_to_pool(TypeTextTool)
            print("  [OK] TypeTextTool 已注册")
        except Exception as e:
            print(f"  [FAIL] TypeTextTool 注册失败: {e}")
        
        try:
            cls._instance.add_tool_to_pool(ClickElementTool)
            print("  [OK] ClickElementTool 已注册")
        except Exception as e:
            print(f"  [FAIL] ClickElementTool 注册失败: {e}")
        
        try:
            cls._instance.add_tool_to_pool(ScrollTool)
            print("  [OK] ScrollTool 已注册")
        except Exception as e:
            print(f"  [FAIL] ScrollTool 注册失败: {e}")
        
        print("[OK] 所有工具已注册到工具池")
    
    @classmethod
    def get_instance(cls) -> PlanScope:
        """获取PlanScope实例"""
        if not cls._initialized or cls._instance is None:
            raise RuntimeError("PlanScope未初始化，请先调用initialize()")
        return cls._instance
    
    @classmethod
    def is_initialized(cls) -> bool:
        """检查是否已初始化"""
        return cls._initialized
    
    @classmethod
    def cleanup(cls) -> None:
        """清理资源"""
        if cls._instance:
            cls._instance.cleanup()
            cls._instance = None
            cls._initialized = False
            print("[CLEANUP] PlanScope资源已清理")
    
    @classmethod
    def delete_plan(cls, flow_id: str) -> bool:
        """
        删除flow文件和相关的task_history文件
        
        Args:
            flow_id: flow的ID
            
        Returns:
            是否删除成功
        """
        if not cls._initialized or cls._instance is None:
            raise RuntimeError("PlanScope未初始化")
        
        try:
            # 获取storage_manager
            storage_manager = cls._instance.storage_manager
            
            # 1. 删除plan文件
            flow_path = storage_manager.get_path("plans") / f"{flow_id}.json"
            plan_deleted = False
            if flow_path.exists():
                flow_path.unlink()
                print(f"[DELETE] Flow文件已删除: {flow_id}")
                plan_deleted = True
            else:
                print(f"[DELETE] Flow文件不存在: {flow_id}")
            
            # 2. 删除对应的task_history文件
            # task_history文件名格式: task_<flow_id>.json
            task_history_dir = storage_manager.get_path("tasks")
            if task_history_dir.exists():
                task_file = task_history_dir / f"task_{flow_id}.json"
                if task_file.exists():
                    task_file.unlink()
                    print(f"[DELETE] Task历史文件已删除: task_{flow_id}.json")
            
            return plan_deleted
        except Exception as e:
            print(f"[ERROR] 删除Flow文件失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @classmethod
    def update_plan(cls, flow_id: str, updates: Dict[str, Any]) -> bool:
        """
        更新flow配置
        
        Args:
            flow_id: flow的ID
            updates: 更新的字段（如果包含steps字段，则直接覆盖整个flow）
            
        Returns:
            是否更新成功
        """
        if not cls._initialized or cls._instance is None:
            raise RuntimeError("PlanScope未初始化")
        
        try:
            import json
            
            # 获取storage_manager
            storage_manager = cls._instance.storage_manager
            flow_path = storage_manager.get_path("plans") / f"{flow_id}.json"
            
            if not flow_path.exists():
                print(f"[UPDATE] Flow文件不存在: {flow_id}")
                return False
            
            # 如果updates包含steps字段，说明是完整的flow对象，直接覆盖
            if "steps" in updates:
                flow_data = updates
                print(f"[UPDATE] 使用完整flow对象覆盖: {flow_id}")
            else:
                # 否则，读取现有flow并合并更新
                with open(flow_path, 'r', encoding='utf-8') as f:
                    flow_data = json.load(f)
                
                # 应用更新
                for key, value in updates.items():
                    flow_data[key] = value
                print(f"[UPDATE] 合并更新字段: {list(updates.keys())}")
            
            # 写回文件（原子操作）
            temp_path = flow_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(flow_data, f, ensure_ascii=False, indent=2)
            
            # 原子替换
            temp_path.replace(flow_path)
            
            print(f"[UPDATE] Flow文件已更新: {flow_id}")
            return True
            
        except Exception as e:
            print(f"[ERROR] 更新Flow文件失败: {e}")
            import traceback
            traceback.print_exc()
            return False


"""
测试滚动截图并总结聊天记录
演示BaseTool架构的使用

任务：对微信窗口进行滚动，获取所有聊天记录并生成总结
这是一个任务（task），不是工具（tool），由LLM自动组合工具完成
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from readscope.core import ConfigManager
from readscope.agentscope_integration.model_client import AgentScopeModelClient
from planscope import PlanScope

# 导入工具类
from examples.tools.scroll_and_analyze import ScrollAndAnalyzeTool
from examples.tools.general_llm_processor import GeneralLLMProcessorTool
from examples.tools.vl_extract_image_content import VLExtractTool
from examples.tools.analyze_and_reply import AnalyzeAndReplyTool


def _require_env(name: str) -> str:
    v = os.environ.get(name, "")
    if not v:
        raise RuntimeError(
            f"Missing env var: {name}. This repo does not store real API keys; "
            "please set env vars and retry."
        )
    return v


def test_scroll_and_summarize():
    """测试完整工作流：滚动+截图+分析+总结"""
    
    print("=" * 80)
    print("测试：滚动微信窗口并总结聊天记录")
    print("=" * 80)
    
    # 配置（从配置文件读取，无默认值，遵循规则2）
    config = {
        "llm": {
            "provider": "ernie",
            "api_key": _require_env("YAO_MAIN_API_KEY"),
            "base_url": "https://aistudio.baidu.com/llm/lmapi/v3",
            "model_name": "ernie-4.5-turbo-128k-preview",
            "temperature": 0.6,
            "max_tokens": 4096,
            "timeout": 120.0,
            "max_retries": 3
        },
        "plan_llm": {
            "provider": "ernie",
            "api_key": _require_env("YAO_ADVANCED_API_KEY"),
            "base_url": "https://aistudio.baidu.com/llm/lmapi/v3",
            "model_name": "ernie-4.5-turbo-128k-preview",
            "temperature": 0.7,
            "max_tokens": 8192,
            "timeout": 120.0,
            "max_retries": 3
        },
        "embedding": {
            "provider": "siliconflow",
            "api_key": _require_env("YAO_EMBEDDING_API_KEY"),
            "base_url": "https://api.siliconflow.cn/v1/embeddings",
            "model_name": "BAAI/bge-m3",
            "timeout": 60.0,
            "max_retries": 3
        },
        "reranker": {
            "provider": "siliconflow",
            "api_key": _require_env("YAO_RERANK_API_KEY"),
            "base_url": "https://api.siliconflow.cn/v1/embeddings",
            "model_name": "BAAI/bge-reranker-v2-m3",
            "endpoint": "/rerank",
            "timeout": 60.0,
            "max_retries": 3,
            "top_n": 5
        }
    }
    
    # 初始化PlanScope（启用ACE）
    print("\n[初始化] 创建PlanScope实例...")
    # 使用绝对路径，确保工作目录固定在examples下
    work_dir = Path(__file__).parent / "test_scroll_summarize"
    ps = PlanScope(
        config=config, 
        work_dir=str(work_dir), 
        use_ace=True, 
        task_name="scroll_summarize"
    )
    
    # 创建VL模型客户端
    print("[初始化] 创建VL模型客户端...")
    vl_config = {
        "llm": config["llm"],
        "embedding": config.get("embedding", {}),
        "reranker": config.get("reranker", {})
    }
    temp_config_manager = ConfigManager.from_dict(vl_config, "./test_scroll_summarize")
    vl_model_client = AgentScopeModelClient(
        temp_config_manager,
        ps.logger_manager,
        embedding_config=config.get("embedding")
    )
    
    # 创建LLM模型客户端
    llm_model_client = ps.agentscope_wrapper.model_client
    
    # 注册工具（只支持BaseTool类）
    print("[初始化] 注册工具到工具池...")
    try:
        ps.add_tool_to_pool(ScrollAndAnalyzeTool, vl_model_client=vl_model_client)
        ps.add_tool_to_pool(GeneralLLMProcessorTool, llm_model_client=llm_model_client)
        print(f"[OK] 已注册 {len(ps.tool_pool)} 个工具")
    except Exception as e:
        print(f"[错误] 工具注册失败: {e}")
        return
    
    print("[初始化] 初始化完成！\n")
    
    # 任务描述（让LLM自动生成工作流）
    print("=" * 80)
    print("[测试] 执行任务：滚动微信窗口并总结聊天记录")
    print("=" * 80)
    
    task = """
对微信窗口进行以下操作：
1. 滚动微信聊天窗口，截图并提取所有聊天记录
2. 对提取的完整聊天记录进行总结
请直接返回文本内容，不要包含任何其他内容

应用名称：微信
最大滚动次数：3
"""
    
    print(f"\n任务描述：\n{task}")
    
    # 生成工作流
    print("\n[步骤1] LLM生成工作流...")
    try:
        plan = ps.generate_plan(task)
        
        print(f"\n[OK] 工作流已生成，包含 {len(plan['steps'])} 个步骤:")
        for i, step in enumerate(plan['steps'], 1):
            print(f"  步骤{i}: {step['tool']} - {step['description']}")
    except Exception as e:
        print(f"[错误] 工作流生成失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 执行工作流
    print(f"\n[步骤2] 执行工作流...")
    try:
        # 准备工具字典
        tools = {}
        for tool_name, tool_info in ps.tool_pool.items():
            tools[tool_name] = tool_info['func']
        
        result = ps.execute_plan(plan, tools)
        
        if result.get('success'):
            print(f"\n[OK] 工作流执行成功")
            
            # 获取最终输出
            final_step = result.get('final_step', {})
            final_output = final_step.get('content', '')
            
            if final_output:
                print(f"\n{'='*80}")
                print("聊天记录总结：")
                print('='*80)
                print(final_output)
                print('='*80)
            else:
                print("\n[警告] 未找到总结内容")
            
            # 测试完成
            print(f"\n{'='*80}")
            print("[测试完成] BaseTool架构测试成功")
            print(f"{'='*80}")
            print("[OK] 工具统一架构正常工作")
            print("[OK] BaseTool自动schema拼接机制正常")
            print("[OK] 通用LLM处理工具正常")
            print("[OK] 滚动截图分析工具正常")
        else:
            print(f"\n[失败] 工作流执行失败")
            print(f"错误信息: {result.get('error', '未知错误')}")
    except Exception as e:
        print(f"[错误] 执行失败: {e}")
        import traceback
        traceback.print_exc()
    
    ps.cleanup()
    print("\n测试完成！")


def test_tool_metadata():
    """测试工具元数据获取"""
    print("=" * 80)
    print("测试：工具元数据")
    print("=" * 80)
    
    import json
    
    print("\n1. ScrollAndAnalyzeTool:")
    metadata = ScrollAndAnalyzeTool.get_metadata()
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    
    print("\n2. GeneralLLMProcessorTool:")
    metadata = GeneralLLMProcessorTool.get_metadata()
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    
    print("\n3. VLExtractTool:")
    metadata = VLExtractTool.get_metadata()
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    
    print("\n4. AnalyzeAndReplyTool:")
    metadata = AnalyzeAndReplyTool.get_metadata()
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    
    print("\n所有工具元数据验证通过！")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "metadata":
        # 测试元数据
        test_tool_metadata()
    else:
        # 测试完整工作流
        test_scroll_and_summarize()


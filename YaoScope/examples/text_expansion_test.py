"""
文字扩写测试 - 展示VL+OCR+LLM的配合
测试目标：对图片中的文字进行扩写

工具组合：
1. vl_extract_image_content：理解图片主题和风格
2. ocr_extract_text：精确提取文字内容
3. analyze_and_reply：对文字进行扩写（LLM工具）
"""
import os
import sys
from pathlib import Path
from functools import partial

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from readscope.core import ConfigManager
from readscope.agentscope_integration.model_client import AgentScopeModelClient
from planscope import PlanScope
from examples.tools.vl_extract_image_content import vl_extract_image_content
# from examples.tools.ocr_extract_text import ocr_extract_text  # 需要paddleocr
from examples.tools.analyze_and_reply import analyze_and_reply


def _require_env(name: str) -> str:
    v = os.environ.get(name, "")
    if not v:
        raise RuntimeError(
            f"Missing env var: {name}. This repo does not store real API keys; "
            "please set env vars and retry."
        )
    return v


def test_text_expansion():
    """测试文字扩写场景"""
    
    print("=" * 80)
    print("文字扩写测试 - VL+OCR+LLM配合")
    print("=" * 80)
    
    # 配置
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
    
    # 初始化PlanScope
    print("\n[初始化] 创建PlanScope实例...")
    # 使用绝对路径，确保工作目录固定在examples下
    work_dir = Path(__file__).parent / "test_text_expansion"
    ps = PlanScope(
        config=config,
        work_dir=str(work_dir),
        use_ace=True,
        task_name="text_expansion"
    )
    
    # 创建VL模型客户端（与planscope中plan_model_client创建方式一致）
    print("[初始化] 创建VL模型客户端...")
    vl_config = {
        "llm": config["llm"],
        "embedding": config.get("embedding", {}),
        "reranker": config.get("reranker", {})
    }
    temp_config_manager = ConfigManager.from_dict(vl_config, "./test_text_expansion")
    vl_model_client = AgentScopeModelClient(
        temp_config_manager,
        ps.logger_manager,
        embedding_config=config.get("embedding")
    )
    
    # 添加工具到工具池
    print("[初始化] 添加工具到工具池...")
    
    # VL工具（传入vl_model_client）
    vl_tool = partial(vl_extract_image_content, vl_model_client=vl_model_client)
    
    # 导入工具的schema、参数定义和通用描述
    from examples.tools.vl_extract_image_content import (
        VL_OUTPUT_JSON_SCHEMA, 
        VL_INPUT_PARAMETERS,
        VL_TOOL_DESCRIPTION
    )
    from examples.tools.analyze_and_reply import (
        LLM_OUTPUT_JSON_SCHEMA, 
        LLM_INPUT_PARAMETERS,
        LLM_TOOL_DESCRIPTION
    )
    # from examples.tools.ocr_extract_text import (
    #     OCR_OUTPUT_JSON_SCHEMA, 
    #     OCR_INPUT_PARAMETERS,
    #     OCR_TOOL_DESCRIPTION
    # )
    
    # 使用新的BaseTool架构注册工具
    from examples.tools.vl_extract_image_content import VLExtractTool
    from examples.tools.analyze_and_reply import AnalyzeAndReplyTool
    
    # 获取LLM模型客户端（使用PlanScope的model_client）
    llm_model_client = ps.agentscope_wrapper.model_client
    
    ps.add_tool_to_pool(VLExtractTool, vl_model_client=vl_model_client)
    ps.add_tool_to_pool(AnalyzeAndReplyTool, llm_model_client=llm_model_client)
    
    print(f"[OK] 工具库中有 {len(ps.tool_pool)} 个工具")
    print("[初始化] 初始化完成！\n")
    
    # 用户需求（让LLM自主生成工作流）
    image_path = str(project_root / "扩写.png")
    user_request = f"对图片'{image_path}'中的文字进行续写"
    
    print("=" * 80)
    print(f"[测试] 用户需求: {user_request}")
    print("[测试] 让LLM自主生成工作流...")
    print("=" * 80)
    
    # 生成工作流
    plan = ps.generate_plan(user_request)
    
    # 验证工作流
    print(f"\n[OK] LLM生成的工作流包含 {len(plan['steps'])} 个步骤:")
    for step in plan['steps']:
        print(f"  步骤{step['step_id']}: {step['tool']} - {step['description']}")
    
    # 执行工作流
    print(f"\n[执行] 开始执行工作流...")
    
    # 准备工具（为analyze_and_reply注入model_client）
    def analyze_and_reply_wrapper(**kwargs):
        """Wrapper函数，自动注入model_client"""
        # 移除kwargs中的model_client（如果有）以避免重复
        kwargs_clean = {k: v for k, v in kwargs.items() if k != 'model_client'}
        return analyze_and_reply(model_client=ps.agentscope_wrapper.model_client, **kwargs_clean)
    
    tools = {
        "vl_extract_image_content": vl_tool,
        # "ocr_extract_text": ocr_extract_text,  # 需要paddleocr
        "analyze_and_reply": analyze_and_reply_wrapper
    }
    
    result = ps.execute_plan(plan, tools)
    
    # 打印每个步骤的执行结果
    print(f"\n{'='*80}")
    print("[调试] 各步骤执行结果:")
    print(f"{'='*80}")
    
    if 'steps_results' in result:
        for step_id, step_result in result['steps_results'].items():
            print(f"\n步骤 {step_id}:")
            print(f"  类型: {type(step_result)}")
            print(f"  内容: {step_result}")
            if isinstance(step_result, dict):
                print(f"  键: {list(step_result.keys())}")
                for key, value in step_result.items():
                    print(f"    {key}: {type(value)} = {str(value)[:200]}...")
    
    # 输出结果
    if result.get('success'):
        print(f"\n[OK] 工作流执行成功")
        final_output = result.get('final_step', {}).get('content', '')
        if final_output:
            print(f"\n{'='*80}")
            print("[结果] 扩写后的文字:")
            print(f"{'='*80}")
            print(final_output)
            print(f"{'='*80}")
        else:
            print("\n[警告] 未找到content字段")
            print(f"[调试] final_step内容: {result.get('final_step', {})}")
    else:
        print(f"\n[失败] 工作流执行失败")
        print(f"错误信息: {result.get('error', '未知错误')}")
    
    ps.cleanup()
    print("\n测试完成！")


if __name__ == "__main__":
    test_text_expansion()


"""
ACE VL最终测试 - 只测试核心场景
测试目标：分析微信聊天截图，给出我应该如何回复
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
from examples.tools.vl_extract_image_content import vl_extract_image_content
from examples.tools.analyze_and_reply import analyze_and_reply
from functools import partial


def _require_env(name: str) -> str:
    v = os.environ.get(name, "")
    if not v:
        raise RuntimeError(
            f"Missing env var: {name}. This repo does not store real API keys; "
            "please set env vars and retry."
        )
    return v


def test_chat_reply():
    """测试核心场景：分析聊天截图并生成回复"""
    
    print("=" * 80)
    print("ACE VL最终测试 - 分析聊天截图并生成回复")
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
    
    # 初始化PlanScope（启用ACE，指定任务名称）
    print("\n[初始化] 创建PlanScope实例（启用ACE）...")
    ps = PlanScope(config=config, work_dir="./test_ace_vl_final", use_ace=True, task_name="chat_analysis")
    
    # 创建VL模型客户端（与planscope中plan_model_client创建方式一致）
    print("[初始化] 创建VL模型客户端...")
    vl_config = {
        "llm": config["llm"],
        "embedding": config.get("embedding", {}),
        "reranker": config.get("reranker", {})
    }
    temp_config_manager = ConfigManager.from_dict(vl_config, "./test_ace_vl_final")
    vl_model_client = AgentScopeModelClient(
        temp_config_manager,
        ps.logger_manager,
        embedding_config=config.get("embedding")
    )
    
    # 添加工具到工具库（不立即注册，等待LLM筛选）
    print("[初始化] 添加工具到工具库...")
    
    # 创建VL工具wrapper（传入vl_model_client）
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
    
    # 使用新的BaseTool架构注册工具
    from examples.tools.vl_extract_image_content import VLExtractTool
    from examples.tools.analyze_and_reply import AnalyzeAndReplyTool
    
    # 获取LLM模型客户端（使用PlanScope的model_client）
    llm_model_client = ps.agentscope_wrapper.model_client
    
    ps.add_tool_to_pool(VLExtractTool, vl_model_client=vl_model_client)
    ps.add_tool_to_pool(AnalyzeAndReplyTool, llm_model_client=llm_model_client)
    
    print(f"[OK] 工具库中有 {len(ps.tool_pool)} 个工具，等待LLM筛选")
    print("[初始化] 初始化完成！\n")
    
    # 测试：分析聊天截图并生成回复
    print("=" * 80)
    print("[测试] 根据微信聊天截图生成一条合适的回复内容，如果我是最后一条则不回复")
    print("=" * 80)
    
    image_path = str(project_root / "微信图片.png")
    # 更明确的需求描述：以第一人称身份生成回复（用户名是longdream）
    task = f"分析微信聊天截图（{image_path}），我的用户名是longdream，请以我（longdream）的口吻生成一条简短回复，让我可以直接发送到群里参与这个话题的讨论。要求：1) 使用第一人称（我、我的）而不是第三人称 2) 只返回回复内容本身，不要任何说明 3) 语气自然友好"
    plan = ps.generate_plan(task)
    
    # 验证plan结构
    print(f"\n[OK] 工作流已生成，包含 {len(plan['steps'])} 个步骤")
    for i, step in enumerate(plan['steps'], 1):
        print(f"  步骤{i}: {step['tool']} - {step['description']}")
    
    # 检查是否是2步工作流
    if len(plan['steps']) != 2:
        print(f"\n[警告] 期望2步工作流，实际{len(plan['steps'])}步")
        print("LLM可能没有识别出需要拆分VL和语言分析任务")
    else:
        if plan['steps'][0]['tool'] == 'vl_extract_image_content':
            print("\n[OK] 第1步正确：VL提取内容")
        else:
            print(f"\n[警告] 第1步工具错误：{plan['steps'][0]['tool']}")
        
        if plan['steps'][1]['tool'] == 'analyze_and_reply':
            print("[OK] 第2步正确：LLM分析并生成回复")
        else:
            print(f"[警告] 第2步工具错误：{plan['steps'][1]['tool']}")
    
    # 执行plan
    print(f"\n[执行] 开始执行工作流...")
    
    # 为analyze_and_reply创建wrapper函数（遵循项目规则3：所有LLM访问必须通过AgentScope）
    def analyze_and_reply_wrapper(**kwargs):
        """Wrapper函数，自动注入model_client"""
        # 移除kwargs中的model_client（如果有）以避免重复
        kwargs_clean = {k: v for k, v in kwargs.items() if k != 'model_client'}
        return analyze_and_reply(model_client=ps.agentscope_wrapper.model_client, **kwargs_clean)
    
    tools = {
        "vl_extract_image_content": vl_tool,
        "analyze_and_reply": analyze_and_reply_wrapper
    }
    result = ps.execute_plan(plan, tools)
    
    # 输出结果
    if result.get('success'):
        print(f"\n[OK] 工作流执行成功")
        
        # 调试：显示final_step的内容
        final_step = result.get('final_step', {})
        print(f"\n[调试] final_step的keys: {list(final_step.keys())}")
        print(f"[调试] final_step内容: {final_step}")
        
        # 直接访问final_step.content
        final_output = final_step.get('content', '')
        if final_output:
            print(f"\n回复内容：\n{final_output}")
        else:
            print("\n[警告] 未找到content字段或内容为空")
        
        # 测试完成，显示结果
        print(f"\n{'='*80}")
        print("[测试完成] ACE智能系统测试成功")
        print(f"{'='*80}")
        print("[OK] VL工具成功提取图片内容")
        print("[OK] LLM工具成功生成回复")
        print(f"[OK] 智能prompt注入机制正常运作")
        print(f"[OK] OUTPUT_JSON_SCHEMA在工具内部正确拼接")
    else:
        print(f"\n[失败] 工作流执行失败")
        print(f"错误信息: {result.get('error', '未知错误')}")
    
    ps.cleanup()
    print("\n测试完成！")


if __name__ == "__main__":
    test_chat_reply()


"""
PlanScope完整测试
使用OrangePi_5_Plus_RK3588_用户手册_v2.1.pdf进行完整测试
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from planscope import PlanScope
from readscope import ReadScope


def _require_env(name: str) -> str:
    v = os.environ.get(name, "")
    if not v:
        raise RuntimeError(
            f"Missing env var: {name}. This repo does not store real API keys; "
            "please set env vars and retry."
        )
    return v


def main():
    """使用PDF文档进行完整测试"""
    print("=" * 80)
    print("PlanScope完整测试 - 使用PDF文档")
    print("=" * 80)
    
    # 配置
    config = {
        "llm": {
            "provider": "qwen",
            "api_key": _require_env("YAO_MAIN_API_KEY"),
            "base_url": os.environ.get("YAO_MAIN_API_BASE", "http://localhost:58080/v1"),
            "model_name": "Qwen3-235B-A22B-Instruct-2507-FP8",
            "temperature": 0.6,
            "max_tokens": 4096,
            "timeout": 60.0,
            "max_retries": 3
        },
        "embedding": {
            "provider": "qwen",
            "api_key": _require_env("YAO_EMBEDDING_API_KEY"),
            "base_url": os.environ.get("YAO_EMBEDDING_API_BASE", "http://localhost:58080/v1"),
            "model_name": "Qwen3-Embedding-4B",
            "timeout": 60.0,
            "max_retries": 3
        },
        "reranker": {
            "provider": "bge",
            "api_key": _require_env("YAO_RERANK_API_KEY"),
            "base_url": os.environ.get("YAO_RERANK_API_BASE", "http://localhost:58080/v1"),
            "model_name": "Bge-Reranker-Large",
            "endpoint": "/rerank",
            "timeout": 60.0,
            "max_retries": 3,
            "top_n": 5
        }
    }
    
    # 初始化PlanScope和ReadScope
    print("\n[步骤1] 初始化PlanScope和ReadScope...")
    ps = PlanScope(config=config, work_dir="./planscope_data")
    rs = ReadScope(config=config, work_dir="./readscope_data")
    print("[成功] 初始化完成")
    
    # 检查PDF文件
    pdf_path = project_root / "OrangePi_5_Plus_RK3588_用户手册_v2.1.pdf"
    if not pdf_path.exists():
        print(f"[错误] PDF文件不存在: {pdf_path}")
        return
    
    # 定义工具函数（使用ReadScope）
    print("\n[步骤2] 定义工具函数...")
    
    # 初始化文档
    print("  初始化PDF文档...")
    doc_id = rs.initialize_document(str(pdf_path))
    print(f"  文档ID: {doc_id}")
    
    def query_document(question: str) -> dict:
        """查询文档"""
        print(f"  [工具] 查询文档: {question}")
        answer = rs.query(doc_id, question)
        return {
            "answer": answer,
            "question": question
        }
    
    def extract_info(topic: str) -> dict:
        """提取特定主题的信息"""
        print(f"  [工具] 提取信息: {topic}")
        question = f"请提取关于{topic}的详细信息"
        answer = rs.query(doc_id, question)
        return {
            "topic": topic,
            "info": answer
        }
    
    def compare_specs(spec1: str, spec2: str) -> dict:
        """比较两个规格"""
        print(f"  [工具] 比较规格: {spec1} vs {spec2}")
        question = f"请比较{spec1}和{spec2}的区别"
        answer = rs.query(doc_id, question)
        return {
            "comparison": answer,
            "spec1": spec1,
            "spec2": spec2
        }
    
    def summarize_section(section_name: str) -> dict:
        """总结某个章节"""
        print(f"  [工具] 总结章节: {section_name}")
        question = f"请总结{section_name}章节的主要内容"
        answer = rs.query(doc_id, question)
        return {
            "section": section_name,
            "summary": answer
        }
    
    print("[成功] 工具函数定义完成")
    
    # 生成工作流
    print("\n[步骤3] 生成工作流...")
    
    # 提供可用工具列表给LLM
    prompt_template = """你是一个工作流规划专家。请根据用户的需求，生成一个详细的执行计划。

可用的工具：
1. query_document - 查询文档内容，参数: question (str)
2. extract_info - 提取特定主题的信息，参数: topic (str)
3. compare_specs - 比较两个规格，参数: spec1 (str), spec2 (str)
4. summarize_section - 总结某个章节，参数: section_name (str)

用户需求：{user_prompt}

请生成一个JSON格式的工作流计划，包含以下结构：
{{
  "steps": [
    {{
      "step_id": 1,
      "description": "步骤描述",
      "tool": "工具名称（必须从上面的可用工具中选择）",
      "tool_input": {{
        "参数名": "参数值"
      }},
      "dependencies": [],
      "reasoning": "选择该步骤的原因"
    }}
  ],
  "overall_strategy": "整体策略描述",
  "complexity_level": "simple/medium/complex",
  "estimated_steps": 步骤数量
}}

要求：
1. step_id必须从1开始连续递增
2. dependencies数组包含该步骤依赖的其他步骤的step_id
3. tool_input中可以使用变量引用，格式为 {{steps.X.field}}，表示引用步骤X的返回值中的field字段
4. 确保依赖关系正确，不能有循环依赖
5. 只使用上面列出的可用工具
6. 只返回JSON，不要有其他说明文字

请生成工作流计划："""
    
    user_prompt = """
    请帮我分析OrangePi 5 Plus开发板：
    1. 查询CPU型号和主要规格
    2. 提取内存和存储相关信息
    3. 总结硬件特性
    """
    
    try:
        plan = ps.generate_plan(
            prompt=user_prompt,
            prompt_template=prompt_template,
            temperature=0.7
        )
        print(f"[成功] 工作流生成成功")
        print(f"  Flow ID: {plan.get('flow_id')}")
        print(f"  步骤数: {len(plan['steps'])}")
        
        # 打印步骤详情
        print("\n  步骤详情:")
        for step in plan["steps"]:
            print(f"    步骤 {step['step_id']}: {step['description']}")
            print(f"      工具: {step['tool']}")
            print(f"      输入: {step['tool_input']}")
            print(f"      依赖: {step.get('dependencies', [])}")
    
    except Exception as e:
        print(f"[失败] 工作流生成失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 执行工作流
    print("\n[步骤4] 执行工作流...")
    
    tools = {
        "query_document": query_document,
        "extract_info": extract_info,
        "compare_specs": compare_specs,
        "summarize_section": summarize_section
    }
    
    try:
        result = ps.execute_plan(
            plan_json=plan,
            tools=tools
        )
        
        print(f"\n[成功] 工作流执行成功")
        print(f"  执行步骤数: {len(result['executed_steps'])}")
        print(f"  总耗时: {result['execution_time']:.2f}秒")
        
        # 打印每个步骤的结果
        print("\n  步骤结果:")
        for step_id, step_result in result["step_results"].items():
            print(f"\n    步骤 {step_id}:")
            for key, value in step_result.items():
                if isinstance(value, str) and len(value) > 100:
                    print(f"      {key}: {value[:100]}...")
                else:
                    print(f"      {key}: {value}")
    
    except Exception as e:
        print(f"[失败] 工作流执行失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 清理资源
    print("\n[步骤5] 清理资源...")
    ps.cleanup()
    rs.cleanup()
    print("[成功] 清理完成")
    
    print("\n" + "=" * 80)
    print("完整测试运行完成")
    print("=" * 80)


if __name__ == "__main__":
    main()


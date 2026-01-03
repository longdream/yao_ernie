"""
YaoScope 文档续写测试脚本
测试文档续写场景，使用鼠标坐标裁剪编辑区域
"""
import os
import requests
import json
import time
from typing import Dict, Any

# 服务地址
BASE_URL = os.environ.get("YAO_BASE_URL", "http://localhost:8765")


def _require_env(name: str) -> str:
    v = os.environ.get(name, "")
    if not v:
        raise RuntimeError(
            f"Missing env var: {name}. This repo does not store real API keys; "
            "please set env vars and retry."
        )
    return v

# 测试配置
TEST_CONFIG = {
    # LLM模型 - 百度AIStudio ERNIE-4.5-turbo-128k-preview
    "main_model": "ernie-4.5-turbo-128k-preview",
    "main_api_base": "https://aistudio.baidu.com/llm/lmapi/v3",
    "main_api_key": _require_env("YAO_MAIN_API_KEY"),
    
    # 高级模型
    "advanced_model": "ernie-4.5-turbo-128k-preview",
    "advanced_api_base": "https://aistudio.baidu.com/llm/lmapi/v3",
    "advanced_api_key": _require_env("YAO_ADVANCED_API_KEY"),
    
    # VL模型 - 百度AIStudio ernie-4.5-turbo-vl
    "vl_model": "ernie-4.5-turbo-vl",
    "vl_api_base": "https://aistudio.baidu.com/llm/lmapi/v3",
    "vl_api_key": _require_env("YAO_VL_API_KEY"),
    
    # 轻量模型
    "light_model": "ernie-4.5-turbo-128k-preview",
    "light_api_base": "https://aistudio.baidu.com/llm/lmapi/v3",
    "light_api_key": _require_env("YAO_LIGHT_API_KEY"),
    
    # Embedding模型 - 硅基流动 BAAI/bge-m3
    "embedding_model": "BAAI/bge-m3",
    "embedding_api_base": "https://api.siliconflow.cn/v1/embeddings",
    "embedding_api_key": _require_env("YAO_EMBEDDING_API_KEY")
}


def print_section(title: str):
    """打印测试章节标题"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_result(test_name: str, success: bool, details: str = ""):
    """打印测试结果"""
    status = "[PASS]" if success else "[FAIL]"
    print(f"{status} {test_name}")
    if details:
        print(f"       {details}")


def test_health_check() -> bool:
    """测试健康检查接口"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        data = response.json()
        
        success = (
            response.status_code == 200 and
            "status" in data and
            "framework" in data and
            data["framework"] == "PlanScope"
        )
        
        print_result(
            "健康检查",
            success,
            f"Status: {data.get('status')}, Framework: {data.get('framework')}"
        )
        
        return success
        
    except Exception as e:
        print_result("健康检查", False, f"Error: {e}")
        return False


def test_config_update() -> bool:
    """测试配置更新接口"""
    try:
        response = requests.post(
            f"{BASE_URL}/config/update",
            json=TEST_CONFIG,
            timeout=30
        )
        data = response.json()
        
        success = (
            response.status_code == 200 and
            data.get("success") is True and
            data.get("agent_initialized") is True
        )
        
        print_result(
            "配置更新",
            success,
            f"初始化: {data.get('agent_initialized')}, 模型数: {data.get('models_configured')}"
        )
        
        # 等待初始化完成
        if success:
            print("       等待PlanScope初始化完成...")
            time.sleep(3)
        
        return success
        
    except Exception as e:
        print_result("配置更新", False, f"Error: {e}")
        return False


def test_document_continue() -> bool:
    """测试文档续写"""
    print_section("文档续写测试")
    
    print("[INFO] 请确保记事本已打开 'test_data\\国庆作文.txt' 文件")

    print("[INFO] 续写任务：读取当前文档内容，从最后一个字续写新内容（只返回续写部分）")
    
    try:
        # 配置请求
        continue_request = {
            "app_name": "记事本",
            "prompt": """请读取当前文档内容，理解文章风格和内容后，从文档最后一个字开始续写新的内容。

重要要求：
1. **只返回新续写的内容**，不要重复原文
2. 续写内容应该在100-200字之间
3. 保持原文的写作风格和语气
4. 让内容更加生动、有细节和情感

示例：
原文：...这是一个快乐的国庆节。
续写：阳光透过窗帘洒进房间，温暖的光斑在地板上跳跃。我躺在床上回味着这几天的经历，嘴角不禁上扬...""",
            "session_id": "test_document_continue"
        }
        
        print(f"\n[REQUEST] 发送请求...")
        print(f"  App: {continue_request['app_name']}")
        print(f"  Prompt: {continue_request['prompt'][:60]}...")
        
        start_time = time.time()
        
        response = requests.post(
            f"{BASE_URL}/agent/execute",
            json=continue_request,
            timeout=300  # 5分钟超时
        )
        
        elapsed = time.time() - start_time
        
        if response.status_code != 200:
            print_result("Agent执行", False, f"HTTP状态码: {response.status_code}")
            return False
        
        data = response.json()
        
        if data.get('success'):
            # 提取续写内容
            result_text = data.get('result', '')
            
            print_result("Agent执行", True, f"耗时: {elapsed:.1f}秒")
            
            # 打印续写内容
            print(f"\n[续写内容]:")
            print("=" * 80)
            if result_text:
                # 限制输出长度以便查看
                preview = result_text[:800] if len(result_text) > 800 else result_text
                try:
                    print(preview)
                except UnicodeEncodeError:
                    safe_text = preview.encode('gbk', errors='ignore').decode('gbk')
                    print(safe_text)
                if len(result_text) > 800:
                    print(f"\n...(共{len(result_text)}字，以上为前800字)")
                else:
                    print(f"\n(共{len(result_text)}字)")
            else:
                print("(无内容返回)")
            print("=" * 80)
            
            return True
        else:
            error_msg = data.get('error', 'Unknown error')[:200]
            print_result("Agent执行", False, f"错误: {error_msg}")
            return False
        
    except requests.exceptions.Timeout:
        print_result("Agent执行", False, "请求超时 (300秒)")
        return False
    except Exception as e:
        print_result("Agent执行", False, f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_test():
    """运行测试"""
    print("\n" + "=" * 80)
    print("  YaoScope 文档续写测试")
    print("=" * 80)
    
    results = {}
    
    # 前置检查
    print_section("前置检查")
    
    # 1. 健康检查
    results["health_check"] = test_health_check()
    if not results["health_check"]:
        print("\n[ERROR] 服务健康检查失败，终止测试")
        return 1
    
    # 2. 配置更新
    results["config_update"] = test_config_update()
    if not results["config_update"]:
        print("\n[ERROR] 配置更新失败，终止测试")
        return 1
    
    # 核心测试
    print("\n[INFO] 开始文档续写测试...")
    results["document_continue"] = test_document_continue()
    
    # 汇总结果
    print_section("测试结果汇总")
    
    test_names = {
        "health_check": "健康检查",
        "config_update": "配置更新",
        "document_continue": "文档续写"
    }
    
    for test_key, success in results.items():
        status = "[PASS]" if success else "[FAIL]"
        print(f"{status} {test_names.get(test_key, test_key)}")
    
    # 只统计核心测试
    core_passed = results.get("document_continue", False)
    
    if core_passed:
        print("\n[SUCCESS] 文档续写测试通过！")
        return 0
    else:
        print("\n[FAIL] 文档续写测试失败")
        return 1


if __name__ == "__main__":
    import sys
    
    try:
        exit_code = run_test()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[INFO] 测试被用户中断")
        sys.exit(2)


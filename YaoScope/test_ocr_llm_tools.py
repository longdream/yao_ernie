"""
OCR+LLM 工具测试脚本（开源安全版）

说明：
- 本脚本不会在仓库内存放任何真实密钥。
- 运行前请通过环境变量提供模型配置与 API Key。

示例（PowerShell）：
  $env:YAO_MAIN_MODEL="Qwen/Qwen2.5-72B-Instruct"
  $env:YAO_MAIN_API_BASE="https://api.siliconflow.cn/v1"
  $env:YAO_MAIN_API_KEY="sk-..."
  $env:YAO_ADVANCED_MODEL="Qwen/Qwen2.5-72B-Instruct"
  $env:YAO_ADVANCED_API_BASE="https://api.siliconflow.cn/v1"
  $env:YAO_ADVANCED_API_KEY="sk-..."
  $env:YAO_VL_MODEL="ernie-4.5-turbo-vl-32k"
  $env:YAO_VL_API_BASE="https://qianfan.baidubce.com/v2"
  $env:YAO_VL_API_KEY="..."
  $env:YAO_LIGHT_MODEL="Qwen/Qwen2.5-7B-Instruct"
  $env:YAO_LIGHT_API_BASE="https://api.siliconflow.cn/v1"
  $env:YAO_LIGHT_API_KEY="sk-..."
  $env:YAO_EMBEDDING_MODEL="BAAI/bge-m3"
  $env:YAO_EMBEDDING_API_BASE="https://api.siliconflow.cn/v1"
  $env:YAO_EMBEDDING_API_KEY="sk-..."
  $env:YAO_RERANK_MODEL="BAAI/bge-reranker-v2-m3"
  $env:YAO_RERANK_API_BASE="https://api.siliconflow.cn/v1"
  $env:YAO_RERANK_API_KEY="sk-..."
  python YaoScope/test_ocr_llm_tools.py
"""

from __future__ import annotations

import os
import time
from typing import Dict, List

import requests


BASE_URL = os.environ.get("YAO_BASE_URL", "http://127.0.0.1:8765")


def _require_env(keys: List[str]) -> Dict[str, str]:
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Missing required env vars: {joined}. "
            "This script does not store keys in repo; please set env vars and retry."
        )
    return {k: os.environ[k] for k in keys}


def build_test_config() -> Dict[str, str]:
    required = [
        "YAO_MAIN_MODEL",
        "YAO_MAIN_API_BASE",
        "YAO_MAIN_API_KEY",
        "YAO_ADVANCED_MODEL",
        "YAO_ADVANCED_API_BASE",
        "YAO_ADVANCED_API_KEY",
        "YAO_VL_MODEL",
        "YAO_VL_API_BASE",
        "YAO_VL_API_KEY",
        "YAO_LIGHT_MODEL",
        "YAO_LIGHT_API_BASE",
        "YAO_LIGHT_API_KEY",
        "YAO_EMBEDDING_MODEL",
        "YAO_EMBEDDING_API_BASE",
        "YAO_EMBEDDING_API_KEY",
        "YAO_RERANK_MODEL",
        "YAO_RERANK_API_BASE",
        "YAO_RERANK_API_KEY",
    ]
    env = _require_env(required)
    return {
        "main_model": env["YAO_MAIN_MODEL"],
        "main_api_base": env["YAO_MAIN_API_BASE"],
        "main_api_key": env["YAO_MAIN_API_KEY"],
        "advanced_model": env["YAO_ADVANCED_MODEL"],
        "advanced_api_base": env["YAO_ADVANCED_API_BASE"],
        "advanced_api_key": env["YAO_ADVANCED_API_KEY"],
        "vl_model": env["YAO_VL_MODEL"],
        "vl_api_base": env["YAO_VL_API_BASE"],
        "vl_api_key": env["YAO_VL_API_KEY"],
        "light_model": env["YAO_LIGHT_MODEL"],
        "light_api_base": env["YAO_LIGHT_API_BASE"],
        "light_api_key": env["YAO_LIGHT_API_KEY"],
        "embedding_model": env["YAO_EMBEDDING_MODEL"],
        "embedding_api_base": env["YAO_EMBEDDING_API_BASE"],
        "embedding_api_key": env["YAO_EMBEDDING_API_KEY"],
        "rerank_model": env["YAO_RERANK_MODEL"],
        "rerank_api_base": env["YAO_RERANK_API_BASE"],
        "rerank_api_key": env["YAO_RERANK_API_KEY"],
    }


def send_config(config: Dict[str, str]) -> None:
    resp = requests.post(f"{BASE_URL}/config/update", json=config, timeout=60)
    resp.raise_for_status()


def test_screenshot_via_agent() -> None:
    resp = requests.post(
        f"{BASE_URL}/agent/execute",
        json={
            "prompt": "截图当前 Chrome 窗口并描述里面的内容，使用智能裁剪功能",
            "app_name": "chrome",
        },
        timeout=600,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"/agent/execute failed: {data.get('error')}")


def test_ocr_via_flow() -> None:
    resp = requests.post(
        f"{BASE_URL}/flows/generate",
        json={"task_description": "截图当前屏幕并识别文字", "app_name": "chrome"},
        timeout=120,
    )
    resp.raise_for_status()


def main() -> None:
    config = build_test_config()
    print("[1/3] Sending config...")
    send_config(config)
    print("[2/3] Waiting for init...")
    time.sleep(5)
    print("[3/3] Running tests...")
    test_screenshot_via_agent()
    test_ocr_via_flow()
    print("OK")


if __name__ == "__main__":
    main()



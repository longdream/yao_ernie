# PlanScope - 基于AgentScope的工作流引擎

PlanScope是一个智能工作流引擎，通过LLM自动生成执行计划，支持依赖解析、变量传递和自动执行。

## 特点

- **自动生成**：通过LLM根据需求生成工作流JSON
- **依赖解析**：自动分析依赖关系，拓扑排序执行
- **变量替换**：支持步骤间的数据传递 `{steps.X.field}`
- **工具注册**：装饰器模式注册工具函数
- **流程持久化**：保存和加载工作流JSON

## 快速开始

### 安装

```bash
# 安装依赖
pip install -r requirements.txt
```

### 基本使用

```python
from planscope import PlanScope

# 1. 初始化
ps = PlanScope(config={
    "llm": {...},
    "embedding": {...},
    "reranker": {...}
}, work_dir="./planscope_data")

# 2. 生成工作流
plan = ps.generate_plan(
    prompt="请帮我分析文档并生成摘要",
    temperature=0.7
)

# 3. 定义工具函数
def read_doc(file_path: str) -> dict:
    return {"content": "..."}

def summarize(content: str) -> dict:
    return {"summary": "..."}

# 4. 执行工作流
result = ps.execute_plan(
    plan_json=plan,
    tools={
        "read_doc": read_doc,
        "summarize": summarize
    }
)

print(result["step_results"])
```

## 工作流JSON格式

```json
{
  "steps": [
    {
      "step_id": 1,
      "description": "读取文档",
      "tool": "read_doc",
      "tool_input": {
        "file_path": "document.pdf"
      },
      "dependencies": []
    },
    {
      "step_id": 2,
      "description": "生成摘要",
      "tool": "summarize",
      "tool_input": {
        "content": "{steps.1.content}"
      },
      "dependencies": [1]
    }
  ],
  "overall_strategy": "读取文档后生成摘要",
  "complexity_level": "simple"
}
```

## 变量引用

在`tool_input`中使用`{steps.X.field}`引用前面步骤的返回值：

- `{steps.1.content}` - 引用步骤1返回的content字段
- `{steps.2.result.data}` - 引用步骤2返回的result.data嵌套字段
- `{steps.1.items[0]}` - 引用步骤1返回的items数组的第一个元素

## 工具注册最佳实践

### 提供详细的工具描述

为了让LLM生成更合理的工作流，强烈建议在注册工具时提供详细的元数据：

```python
@ps.register_tool("my_tool", metadata={
    "capabilities": ["能做什么1", "能做什么2"],
    "limitations": ["不能做什么1", "不能做什么2"],
    "best_practices": ["最佳实践1", "最佳实践2"],
    "use_cases": ["适用场景1", "适用场景2"],
    "output_format": "输出格式说明",
    "error_handling": "错误处理建议"
})
def my_tool(arg1: str) -> dict:
    """工具功能描述"""
    return {...}
```

### 为什么工具描述很重要

1. **帮助LLM理解工具能力边界** - 避免过度依赖或误用工具
2. **提高规划质量** - LLM能根据局限性设计更合理的步骤
3. **减少执行失败** - 明确的最佳实践减少错误使用
4. **支持ACE学习** - 详细描述帮助ACE更好地分析失败原因

### 示例：VL模型工具注册

```python
@ps.register_tool("analyze_wechat_image", metadata={
    "capabilities": [
        "识别微信聊天截图中的文字内容",
        "理解简单的对话上下文",
        "生成符合语境的回复建议"
    ],
    "limitations": [
        "位置坐标识别不准确，无法精确定位UI元素",
        "复杂语言理解能力有限，不适合长篇对话",
        "小型模型，推理能力有限",
        "返回的JSON格式可能不规范，需要容错处理"
    ],
    "best_practices": [
        "适用于简单的单轮或双轮聊天分析",
        "建议对返回结果进行JSON格式验证",
        "不要依赖精确的位置信息",
        "适合快速理解聊天大意，不适合精细分析"
    ],
    "use_cases": [
        "快速了解聊天内容",
        "生成简单的回复建议",
        "聊天内容摘要提取"
    ],
    "output_format": "JSON格式，包含chat_content、suggested_reply、reasoning三个字段",
    "error_handling": "可能抛出JSONDecodeError，需要捕获并提供降级方案"
})
def analyze_wechat_image(image_path: str) -> dict:
    """使用VL模型分析微信聊天截图"""
    return analyze_image(image_path)
```

### 简单注册（不推荐用于生产环境）

如果只是快速测试，可以使用简单注册：

```python
@ps.register_tool("my_tool")
def my_function(arg1: str, arg2: int) -> dict:
    return {"result": arg1 * arg2}
```

但这样LLM无法了解工具的能力边界，可能导致规划不合理。

## 示例

查看`examples/`目录：
- `planscope_usage.py` - 基本使用示例
- `planscope_simple_test.py` - 核心功能测试
- `planscope_pdf_test.py` - PDF文档分析示例

## API文档

### PlanScope类

#### `__init__(config, work_dir)`
初始化PlanScope实例

#### `generate_plan(prompt, prompt_template=None, **kwargs)`
生成工作流计划

#### `execute_plan(plan_json, tools)`
执行工作流

#### `execute_plan_from_file(file_path, tools)`
从文件加载并执行工作流

#### `load_plan(flow_id)`
加载已保存的工作流

#### `register_tool(name)`
装饰器：注册工具函数

#### `add_tool(name, func)`
手动注册工具函数

## 架构

```
planscope/
├── planscope.py           # 主类
├── core/
│   ├── plan_generator.py  # 流程生成器
│   ├── plan_parser.py     # 流程解析器
│   ├── plan_executor.py   # 流程执行器
│   └── exceptions.py      # 异常定义
├── tools/
│   ├── tool_registry.py   # 工具注册中心
│   └── variable_resolver.py # 变量解析器
└── utils/
    └── json_validator.py  # JSON验证器
```

## 错误处理

- 任何步骤失败会立即停止整个流程
- 抛出`PlanExecutionError`异常，包含失败步骤信息
- 支持工具未注册、变量解析失败等错误检测

## 许可证

MIT License


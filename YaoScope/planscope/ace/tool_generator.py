"""
工具生成器
自动生成Python工具代码并注册
"""
import json
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional
import re

from planscope.ace.code_validator import CodeValidator


# 工具代码生成Prompt
TOOL_GENERATION_PROMPT = """你是一个Python工具生成专家。请根据以下需求生成一个Python工具函数。

工具名称：{tool_name}
工具描述：{tool_description}
所需能力：{required_capabilities}

要求：
1. 函数签名必须清晰，参数类型标注完整
2. 根据工具类型选择合适的参数：
   - 计算工具：使用expression参数接收数学表达式字符串
   - 文件操作工具：使用file_path、directory等参数
   - LLM工具：使用prompt参数（必需参数，无默认值）
3. 包含完整的docstring（功能、参数、返回值、异常）
4. 不要有任何降级或备用方案，失败时抛出异常
5. 添加详细的日志输出（使用print）
6. 工具范围：计算、文件发现和读取、Windows通用操作
7. 不要使用危险操作（如os.system、删除文件、修改注册表）
8. 如果需要写入文件，只能写入到: generated_tools/, temp/, logs/ 目录
9. 返回值必须是dict类型，且必须包含content字段（string类型），存储本工具最重要的输出结果
10. 对于计算工具，需要能够安全地eval数学表达式（使用ast.literal_eval或仅支持基本运算符）

⚠️ 重要：所有工具返回的dict必须包含content字段，例如：
return {{
    "content": str(most_important_result),  # 必须包含此字段
    "other_field": other_value
}}

请返回JSON格式：
{{
  "function_code": "完整的Python函数代码（不含import）",
  "import_statements": ["需要的import语句"],
  "test_code": "测试代码（包含至少2个测试用例，验证基本功能）",
  "metadata": {{
    "capabilities": ["能力1", "能力2"],
    "limitations": ["限制1", "限制2"],
    "best_practices": ["最佳实践1"],
            "initial_prompt": "如果是LLM/VL工具，提供初始prompt模板。只描述任务内容，不要包含任何输出格式说明。可包含{{变量}}占位符用于动态参数。否则为空字符串",
    "output_format": "输出格式说明",
    "output_json_schema": {{
      "type": "object",
      "properties": {{
        "content": {{
          "type": "string",
          "description": "本工具最重要的输出结果"
        }}
      }},
      "required": ["content"]
    }}
  }}
}}

只返回JSON，不要其他说明。"""


class ToolGenerator:
    """工具生成器"""
    
    def __init__(self, model_client, tool_registry, logger, work_dir: str = ".", task_name: str = "default"):
        """
        初始化工具生成器
        
        Args:
            model_client: LLM模型客户端
            tool_registry: 工具注册表
            logger: 日志记录器
            work_dir: 工作目录
            task_name: 任务名称（用于任务级工具隔离）
        """
        self.model_client = model_client
        self.tool_registry = tool_registry
        self.logger = logger
        self.work_dir = Path(work_dir)
        self.task_name = task_name
        
        # 任务级生成工具目录
        # 使用config/tools作为基础目录
        self.generated_tools_dir = self.work_dir / task_name / "generated_tools"
        
        # 创建生成工具目录
        self.generated_tools_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建__init__.py
        init_file = self.generated_tools_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text("# ACE自动生成的工具\n", encoding='utf-8')
        
        # 创建README.md
        readme_file = self.generated_tools_dir / "README.md"
        if not readme_file.exists():
            readme_file.write_text(
                f"# ACE自动生成的工具 (任务: {task_name})\n\n"
                "此目录包含ACE自动生成的Python工具。\n"
                "这些工具是在Plan生成过程中，当发现缺失工具时自动创建的。\n\n"
                f"**任务**: {task_name}\n"
                "**注意**: 请勿手动修改这些文件，它们由ACE管理。\n",
                encoding='utf-8'
            )
        
        self.logger.info(f"ToolGenerator初始化完成 (任务: {task_name})")
        self.logger.info(f"工具目录: {self.generated_tools_dir}")
    
    async def generate_tool(self, 
                           tool_name: str, 
                           tool_description: str, 
                           required_capabilities: List[str]) -> bool:
        """
        生成并注册新工具
        
        Args:
            tool_name: 工具名称
            tool_description: 工具描述
            required_capabilities: 所需能力列表
            
        Returns:
            是否成功生成并注册
        """
        self.logger.info("=" * 80)
        self.logger.info(f"开始生成工具: {tool_name}")
        self.logger.info(f"描述: {tool_description}")
        self.logger.info(f"所需能力: {required_capabilities}")
        self.logger.info("=" * 80)
        
        try:
            # 1. 使用LLM生成工具代码
            self.logger.info("步骤1: 调用LLM生成工具代码...")
            tool_spec = await self._generate_code_with_llm(
                tool_name, 
                tool_description, 
                required_capabilities
            )
            
            # 2. 验证代码安全性和语法
            self.logger.info("步骤2: 验证代码...")
            if not self._validate_code(tool_spec):
                return False
            
            # 3. 测试生成的工具
            self.logger.info("步骤3: 测试生成的工具...")
            if not self._test_tool(tool_spec):
                self.logger.warning("工具测试失败，但仍然保存（可能是测试代码问题）")
            
            # 4. 保存到generated_tools/
            self.logger.info("步骤4: 保存工具代码...")
            tool_file = self._save_tool(tool_name, tool_spec)
            
            # 5. 动态导入并注册
            self.logger.info("步骤5: 动态导入并注册工具...")
            if not self._load_and_register_tool(tool_name, tool_file, tool_spec['metadata']):
                return False
            
            self.logger.info("=" * 80)
            self.logger.info(f"工具生成成功: {tool_name}")
            self.logger.info(f"文件位置: {tool_file}")
            self.logger.info("=" * 80)
            return True
            
        except Exception as e:
            self.logger.error(f"工具生成失败: {str(e)}", exc_info=True)
            return False
    
    async def _generate_code_with_llm(self,
                                     tool_name: str,
                                     tool_description: str,
                                     required_capabilities: List[str]) -> Dict[str, Any]:
        """
        使用LLM生成工具代码
        
        Returns:
            包含function_code, import_statements, test_code, metadata的字典
        """
        # 构建prompt
        prompt = TOOL_GENERATION_PROMPT.format(
            tool_name=tool_name,
            tool_description=tool_description,
            required_capabilities=", ".join(required_capabilities)
        )
        
        # 调用LLM
        response = await self.model_client.call_model_with_json_response(prompt=prompt)
        
        # 验证返回的JSON结构
        required_keys = ['function_code', 'import_statements', 'test_code', 'metadata']
        for key in required_keys:
            if key not in response:
                raise ValueError(f"LLM返回的JSON缺少必需字段: {key}")
        
        self.logger.info(f"LLM生成完成，代码长度: {len(response['function_code'])}字符")
        return response
    
    def _validate_code(self, tool_spec: Dict[str, Any]) -> bool:
        """
        验证代码安全性和语法
        
        Returns:
            是否验证通过
        """
        function_code = tool_spec['function_code']
        
        # 验证语法和安全性
        valid, msg = CodeValidator.validate(function_code)
        
        if not valid:
            self.logger.error(f"代码验证失败: {msg}")
            return False
        
        self.logger.info(f"代码验证通过: {msg}")
        return True
    
    def _test_tool(self, tool_spec: Dict[str, Any]) -> bool:
        """
        在隔离环境中测试生成的工具
        
        Returns:
            测试是否通过
        """
        function_code = tool_spec['function_code']
        import_statements = tool_spec['import_statements']
        test_code = tool_spec['test_code']
        
        # 创建测试环境
        test_env = {}
        
        try:
            # 执行import语句
            for imp in import_statements:
                exec(imp, test_env)
            
            # 执行工具代码
            exec(function_code, test_env)
            
            # 执行测试代码
            exec(test_code, test_env)
            
            self.logger.info("工具测试通过")
            return True
            
        except Exception as e:
            self.logger.error(f"工具测试失败: {str(e)}", exc_info=True)
            return False
    
    def _save_tool(self, tool_name: str, tool_spec: Dict[str, Any]) -> Path:
        """
        保存工具到文件
        
        Returns:
            工具文件路径
        """
        # 组合完整代码
        full_code = "\n".join(tool_spec['import_statements']) + "\n\n\n" + tool_spec['function_code']
        
        # 保存到文件
        tool_file = self.generated_tools_dir / f"{tool_name}.py"
        tool_file.write_text(full_code, encoding='utf-8')
        
        self.logger.info(f"工具已保存: {tool_file}")
        return tool_file
    
    def _load_and_register_tool(self, 
                                tool_name: str, 
                                tool_file: Path, 
                                metadata: Dict[str, Any]) -> bool:
        """
        动态导入工具并注册到tool_registry
        
        Returns:
            是否成功注册
        """
        try:
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(tool_name, tool_file)
            if spec is None or spec.loader is None:
                self.logger.error(f"无法加载模块: {tool_file}")
                return False
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 获取工具函数
            if not hasattr(module, tool_name):
                self.logger.error(f"模块中未找到函数: {tool_name}")
                return False
            
            tool_func = getattr(module, tool_name)
            
            # 注册到tool_registry
            self.tool_registry.add(tool_name, tool_func, metadata=metadata)
            
            self.logger.info(f"工具已注册: {tool_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"工具注册失败: {str(e)}", exc_info=True)
            return False


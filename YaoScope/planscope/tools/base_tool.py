"""
工具基类 - 所有工具必须继承

使用示例:
    ```python
    from planscope.tools.base_tool import BaseTool
    
    class MyTool(BaseTool):
        TOOL_NAME = "my_tool"
        TOOL_DESCRIPTION = "工具描述"
        TOOL_TYPE = "function"  # 或 "llm", "vl"
        INPUT_PARAMETERS = {
            "param1": {"type": "str", "required": True, "description": "参数说明"}
        }
        OUTPUT_JSON_SCHEMA = '{"result": "返回值说明"}'
        
        def __init__(self, some_client):
            super().__init__()
            self.client = some_client
        
        def _execute_impl(self, param1: str, **kwargs) -> dict:
            # 实现工具逻辑
            return {"result": "..."}
    ```

规范要求:
    1. 必须定义所有类属性（TOOL_NAME, TOOL_DESCRIPTION等）
    2. 必须实现_execute_impl方法
    3. 不要覆盖execute()方法
    4. 通过__init__接收运行时依赖（如model_client）
    5. LLM/VL类型工具必须定义OUTPUT_JSON_SCHEMA
    6. LLM/VL类型工具的prompt中应包含{{OUTPUT_JSON_SCHEMA}}占位符
       该占位符会在执行时被VariableResolver替换为实际的schema
"""
from typing import Dict, Any


class BaseTool:
    """
    工具基类，所有工具应继承此类
    
    设计目标：
    1. 标准化工具元数据定义（description, input_parameters, output_json_schema）
    2. 提供统一的执行接口
    3. 支持运行时依赖注入
    4. schema通过占位符机制注入（{{OUTPUT_JSON_SCHEMA}}）
    """
    
    # 类属性（子类必须定义）
    TOOL_NAME: str = ""
    TOOL_DESCRIPTION: str = ""
    TOOL_TYPE: str = ""  # 工具类型："llm", "vl", "function"
    INPUT_PARAMETERS: Dict[str, Any] = {}
    OUTPUT_JSON_SCHEMA: str = ""
    
    def __init__(self, **kwargs):
        """
        初始化工具，接收运行时注入的参数
        
        Args:
            **kwargs: 运行时注入的参数，如：
                - vl_model_client: VL模型客户端
                - llm_model_client: LLM模型客户端
                - 其他工具特定参数
        """
        # 子类可以覆盖此方法来处理特定的初始化逻辑
        pass
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行工具（统一入口）
        
        对于llm/vl类型工具，自动在prompt末尾拼接OUTPUT_JSON_SCHEMA
        
        Args:
            **kwargs: 工具执行参数
            
        Returns:
            Dict[str, Any]: 执行结果，必须包含"content"字段
        """
        # 如果是llm/vl类型且有prompt参数，自动拼接schema
        if self.TOOL_TYPE in ['llm', 'vl'] and 'prompt' in kwargs:
            original_prompt = kwargs.get('prompt', '')
            if self.OUTPUT_JSON_SCHEMA and original_prompt:
                schema_text = f"\n\n**必须严格按以下JSON格式返回：**\n{self.OUTPUT_JSON_SCHEMA}\n\n⚠️ 注意：必须返回完整的JSON对象，不要遗漏任何字段。"
                kwargs['prompt'] = original_prompt + schema_text
        
        return self._execute_impl(**kwargs)
    
    def _execute_impl(self, **kwargs) -> Dict[str, Any]:
        """
        子类必须实现此方法（替代原来的execute）
        
        Args:
            **kwargs: 工具执行参数
            
        Returns:
            Dict[str, Any]: 执行结果，必须包含"content"字段
            
        Raises:
            NotImplementedError: 子类未实现此方法
        """
        raise NotImplementedError(f"{self.__class__.__name__}必须实现_execute_impl方法")
    
    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        获取工具元数据
        
        Returns:
            Dict[str, Any]: 工具元数据，包含：
                - name: 工具名称
                - description: 工具描述
                - tool_type: 工具类型
                - input_parameters: 输入参数定义
                - output_json_schema: 输出JSON格式定义
        """
        return {
            "name": cls.TOOL_NAME,
            "description": cls.TOOL_DESCRIPTION,
            "tool_type": cls.TOOL_TYPE,
            "input_parameters": cls.INPUT_PARAMETERS,
            "output_json_schema": cls.OUTPUT_JSON_SCHEMA
        }
    
    @classmethod
    def validate_metadata(cls) -> tuple:
        """
        验证工具元数据是否完整
        
        Returns:
            tuple: (is_valid: bool, missing_fields: list[str])
        """
        missing = []
        
        if not cls.TOOL_NAME:
            missing.append("TOOL_NAME")
        if not cls.TOOL_DESCRIPTION:
            missing.append("TOOL_DESCRIPTION")
        if not cls.TOOL_TYPE:
            missing.append("TOOL_TYPE")
        elif cls.TOOL_TYPE not in ["llm", "vl", "function"]:
            missing.append(f"TOOL_TYPE (invalid value: {cls.TOOL_TYPE}, must be 'llm', 'vl', or 'function')")
        
        if not isinstance(cls.INPUT_PARAMETERS, dict):
            missing.append("INPUT_PARAMETERS (must be dict)")
        
        # LLM/VL类型工具必须定义OUTPUT_JSON_SCHEMA
        if cls.TOOL_TYPE in ["llm", "vl"] and not cls.OUTPUT_JSON_SCHEMA:
            missing.append("OUTPUT_JSON_SCHEMA (required for llm/vl tools)")
        
        return len(missing) == 0, missing


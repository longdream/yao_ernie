"""
JSON格式验证器
验证工作流JSON的结构完整性
"""
from typing import Dict, Any, List
from planscope.core.exceptions import PlanValidationError


class PlanJSONValidator:
    """
    工作流JSON验证器
    验证生成的JSON是否符合预期格式
    """
    
    # 必需的顶层字段
    REQUIRED_TOP_LEVEL_FIELDS = ["steps"]
    
    # 可选的顶层字段
    OPTIONAL_TOP_LEVEL_FIELDS = [
        "overall_strategy", "complexity_level", "estimated_steps",
        "app_name", "original_query", "used_model", "flow_id",
        "query_hash", "created_at"
    ]
    
    # 步骤必需字段
    REQUIRED_STEP_FIELDS = ["step_id", "description", "tool", "tool_input"]
    
    # 步骤可选字段
    OPTIONAL_STEP_FIELDS = ["dependencies", "reasoning"]
    
    @staticmethod
    def validate(plan_json: Dict[str, Any]) -> None:
        """
        验证工作流JSON格式
        
        Args:
            plan_json: 工作流JSON对象
            
        Raises:
            PlanValidationError: 验证失败
        """
        if not isinstance(plan_json, dict):
            raise PlanValidationError("工作流JSON必须是字典类型")
        
        # 验证顶层字段
        PlanJSONValidator._validate_top_level(plan_json)
        
        # 验证steps数组
        PlanJSONValidator._validate_steps(plan_json["steps"])
    
    @staticmethod
    def _validate_top_level(plan_json: Dict[str, Any]) -> None:
        """
        验证顶层字段
        
        Args:
            plan_json: 工作流JSON对象
            
        Raises:
            PlanValidationError: 验证失败
        """
        # 检查必需字段
        for field in PlanJSONValidator.REQUIRED_TOP_LEVEL_FIELDS:
            if field not in plan_json:
                raise PlanValidationError(f"缺少必需字段: {field}")
        
        # 验证steps是列表
        if not isinstance(plan_json["steps"], list):
            raise PlanValidationError("'steps' 字段必须是列表类型")
        
        # 验证steps不为空
        if len(plan_json["steps"]) == 0:
            raise PlanValidationError("'steps' 列表不能为空")
    
    @staticmethod
    def _validate_steps(steps: List[Dict[str, Any]]) -> None:
        """
        验证步骤列表
        
        Args:
            steps: 步骤列表
            
        Raises:
            PlanValidationError: 验证失败
        """
        step_ids = set()
        
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                raise PlanValidationError(f"步骤 {i} 必须是字典类型")
            
            # 验证必需字段
            for field in PlanJSONValidator.REQUIRED_STEP_FIELDS:
                if field not in step:
                    raise PlanValidationError(
                        f"步骤 {i} 缺少必需字段: {field}"
                    )
            
            # 验证step_id
            step_id = step["step_id"]
            if not isinstance(step_id, int):
                raise PlanValidationError(
                    f"步骤 {i} 的 'step_id' 必须是整数类型"
                )
            
            if step_id in step_ids:
                raise PlanValidationError(
                    f"步骤ID {step_id} 重复"
                )
            step_ids.add(step_id)
            
            # 验证description
            if not isinstance(step["description"], str):
                raise PlanValidationError(
                    f"步骤 {step_id} 的 'description' 必须是字符串类型"
                )
            
            # 验证tool
            if not isinstance(step["tool"], str):
                raise PlanValidationError(
                    f"步骤 {step_id} 的 'tool' 必须是字符串类型"
                )
            
            # 验证tool_input
            if not isinstance(step["tool_input"], dict):
                raise PlanValidationError(
                    f"步骤 {step_id} 的 'tool_input' 必须是字典类型"
                )
            
            # 验证dependencies（如果存在）
            if "dependencies" in step:
                dependencies = step["dependencies"]
                if not isinstance(dependencies, list):
                    raise PlanValidationError(
                        f"步骤 {step_id} 的 'dependencies' 必须是列表类型"
                    )
                
                for dep in dependencies:
                    if not isinstance(dep, int):
                        raise PlanValidationError(
                            f"步骤 {step_id} 的依赖项必须是整数类型"
                        )
    
    @staticmethod
    def validate_dependencies(plan_json: Dict[str, Any]) -> None:
        """
        验证依赖关系的合法性
        
        Args:
            plan_json: 工作流JSON对象
            
        Raises:
            PlanValidationError: 验证失败
        """
        steps = plan_json["steps"]
        step_ids = {step["step_id"] for step in steps}
        
        for step in steps:
            step_id = step["step_id"]
            dependencies = step.get("dependencies", [])
            
            for dep_id in dependencies:
                # 检查依赖的步骤是否存在
                if dep_id not in step_ids:
                    raise PlanValidationError(
                        f"步骤 {step_id} 依赖的步骤 {dep_id} 不存在"
                    )
                
                # 检查是否存在自依赖
                if dep_id == step_id:
                    raise PlanValidationError(
                        f"步骤 {step_id} 不能依赖自己"
                    )


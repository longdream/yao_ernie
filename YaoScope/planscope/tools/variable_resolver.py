"""
变量解析器
处理工作流中的变量引用，如 {steps.1.screenshot_path}
"""
import re
from typing import Any, Dict
from planscope.core.exceptions import VariableResolutionError


class VariableResolver:
    """
    变量解析器
    支持解析和替换 {{steps.X.field}} 或 {steps.X.field} 格式的变量引用
    优先匹配双括号格式以避免与JSON字段名冲突
    """
    
    # 匹配 {{steps.1.field}} 格式（优先）
    DOUBLE_BRACE_PATTERN = re.compile(r'\{\{steps\.(\d+)\.([^}]+)\}\}')
    # 匹配 {steps.1.field} 格式（向后兼容）
    SINGLE_BRACE_PATTERN = re.compile(r'\{steps\.(\d+)\.([^}]+)\}')
    
    def __init__(self, context: Dict[str, Any], logger=None):
        """
        初始化变量解析器
        
        Args:
            context: 执行上下文，包含已执行步骤的结果
                    格式: {"steps": {1: {...}, 2: {...}}}
            logger: 日志记录器（可选）
        """
        self.context = context
        self.logger = logger
        self.replacements = []  # 记录所有替换操作
    
    def resolve(self, value: Any) -> Any:
        """
        解析值中的变量引用
        
        Args:
            value: 待解析的值（可以是字符串、字典、列表等）
            
        Returns:
            解析后的值
            
        Raises:
            VariableResolutionError: 变量解析失败
        """
        if isinstance(value, str):
            return self._resolve_string(value)
        elif isinstance(value, dict):
            return self._resolve_dict(value)
        elif isinstance(value, list):
            return self._resolve_list(value)
        else:
            return value
    
    def _resolve_string(self, text: str) -> Any:
        """
        解析字符串中的变量引用
        只处理 {{steps.X.field}} 格式的步骤间引用
        
        Args:
            text: 待解析的字符串
            
        Returns:
            解析后的值（可能是字符串或其他类型）
        """
        # 优先匹配双括号格式
        double_matches = list(self.DOUBLE_BRACE_PATTERN.finditer(text))
        # 然后匹配单括号格式
        single_matches = list(self.SINGLE_BRACE_PATTERN.finditer(text))
        
        # 合并匹配结果，双括号优先
        matches = double_matches + single_matches
        
        if not matches:
            return text
        
        # 如果整个字符串就是一个变量引用，返回原始类型
        if len(matches) == 1 and matches[0].group(0) == text:
            step_id = int(matches[0].group(1))
            field_path = matches[0].group(2)
            value = self._extract_value(step_id, field_path)
            
            # 记录替换
            placeholder = matches[0].group(0)
            self.replacements.append({
                "placeholder": placeholder,
                "value": value,
                "type": type(value).__name__
            })
            if self.logger:
                self.logger.debug(f"占位符替换: {placeholder} → {self._format_value(value)}")
            
            return value
        
        # 如果包含多个变量或混合文本，进行字符串替换
        result = text
        for match in matches:
            step_id = int(match.group(1))
            field_path = match.group(2)
            value = self._extract_value(step_id, field_path)
            placeholder = match.group(0)
            
            # 记录替换
            self.replacements.append({
                "placeholder": placeholder,
                "value": value,
                "type": type(value).__name__
            })
            if self.logger:
                self.logger.debug(f"占位符替换: {placeholder} → {self._format_value(value)}")
            
            # 转换为字符串进行替换
            result = result.replace(placeholder, str(value))
        
        return result
    
    def _resolve_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        递归解析字典中的变量引用
        
        Args:
            data: 待解析的字典
            
        Returns:
            解析后的字典
        """
        return {key: self.resolve(value) for key, value in data.items()}
    
    def _resolve_list(self, data: list) -> list:
        """
        递归解析列表中的变量引用
        
        Args:
            data: 待解析的列表
            
        Returns:
            解析后的列表
        """
        return [self.resolve(item) for item in data]
    
    def _extract_value(self, step_id: int, field_path: str) -> Any:
        """
        从上下文中提取指定步骤的字段值
        
        Args:
            step_id: 步骤ID
            field_path: 字段路径，如 "screenshot_path" 或 "result.data"
            
        Returns:
            提取的值
            
        Raises:
            VariableResolutionError: 提取失败
        """
        # 检查步骤是否存在
        if "steps" not in self.context:
            raise VariableResolutionError(f"上下文中缺少 'steps' 字段")
        
        steps = self.context["steps"]
        if step_id not in steps:
            raise VariableResolutionError(f"步骤 {step_id} 的结果不存在")
        
        step_result = steps[step_id]
        
        # 解析字段路径
        fields = field_path.split('.')
        current = step_result
        
        for field in fields:
            # 处理数组索引，如 data[0]
            if '[' in field and ']' in field:
                field_name = field[:field.index('[')]
                index_str = field[field.index('[') + 1:field.index(']')]
                
                try:
                    index = int(index_str)
                except ValueError:
                    raise VariableResolutionError(f"无效的数组索引: {index_str}")
                
                if field_name:
                    if not isinstance(current, dict) or field_name not in current:
                        raise VariableResolutionError(
                            f"步骤 {step_id} 的结果中不存在字段: {field_name}"
                        )
                    current = current[field_name]
                
                if not isinstance(current, (list, tuple)):
                    raise VariableResolutionError(
                        f"字段 {field_name} 不是数组类型"
                    )
                
                if index >= len(current):
                    raise VariableResolutionError(
                        f"数组索引 {index} 超出范围（长度: {len(current)}）"
                    )
                
                current = current[index]
            else:
                # 普通字段访问
                if isinstance(current, dict):
                    if field not in current:
                        raise VariableResolutionError(
                            f"步骤 {step_id} 的结果中不存在字段: {field}"
                        )
                    current = current[field]
                else:
                    raise VariableResolutionError(
                        f"无法从非字典类型中访问字段: {field}"
                    )
        
        return current
    
    def has_variables(self, value: Any) -> bool:
        """
        检查值中是否包含变量引用（双括号或单括号格式）
        
        Args:
            value: 待检查的值
            
        Returns:
            是否包含变量引用
        """
        if isinstance(value, str):
            return bool(self.DOUBLE_BRACE_PATTERN.search(value) or self.SINGLE_BRACE_PATTERN.search(value))
        elif isinstance(value, dict):
            return any(self.has_variables(v) for v in value.values())
        elif isinstance(value, list):
            return any(self.has_variables(item) for item in value)
        else:
            return False
    
    def _format_value(self, value: Any) -> str:
        """
        格式化值用于日志显示
        
        Args:
            value: 要格式化的值
            
        Returns:
            格式化后的字符串
        """
        if isinstance(value, str):
            if len(value) > 50:
                return f'"{value[:50]}..."'
            return f'"{value}"'
        elif isinstance(value, (list, dict)):
            return f"{type(value).__name__}({len(value)} items)"
        else:
            return str(value)
    
    def get_replacements_summary(self) -> str:
        """
        获取所有替换操作的摘要
        
        Returns:
            替换操作摘要字符串
        """
        if not self.replacements:
            return "无占位符替换"
        
        summary_lines = [f"共替换 {len(self.replacements)} 个占位符:"]
        for i, repl in enumerate(self.replacements, 1):
            summary_lines.append(
                f"  {i}. {repl['placeholder']} → {self._format_value(repl['value'])} ({repl['type']})"
            )
        return "\n".join(summary_lines)


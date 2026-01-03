"""
代码验证器
验证生成的工具代码的语法和安全性
"""
import re
from typing import Tuple


class CodeValidator:
    """代码验证器，检查生成的工具代码"""
    
    # 危险操作模式
    DANGEROUS_PATTERNS = [
        (r'os\.system', '禁止使用os.system执行系统命令'),
        (r'subprocess\.(call|run|Popen)', '禁止使用subprocess执行外部命令'),
        (r'eval\s*\(', '禁止使用eval执行动态代码'),
        (r'exec\s*\(', '禁止使用exec执行动态代码'),
        (r'__import__', '禁止使用__import__动态导入'),
        (r'compile\s*\(', '禁止使用compile编译代码'),
        (r'open\s*\([^)]*[\'"]w', '禁止写入文件（需要限制路径）'),
        (r'shutil\.rmtree', '禁止删除目录树'),
        (r'os\.(remove|unlink|rmdir)', '禁止删除文件或目录'),
        (r'Registry|winreg', '禁止操作Windows注册表'),
        (r'ctypes', '禁止使用ctypes调用系统API'),
        (r'pickle\.loads', '禁止使用pickle.loads（安全风险）'),
    ]
    
    # 允许的写入路径前缀（相对路径）
    ALLOWED_WRITE_PATHS = [
        'generated_tools/',
        'test_ace_vl_final/',
        'temp/',
        'logs/',
    ]
    
    @staticmethod
    def validate_syntax(code: str) -> Tuple[bool, str]:
        """
        验证Python语法
        
        Args:
            code: Python代码
            
        Returns:
            (是否有效, 错误信息)
        """
        try:
            compile(code, '<string>', 'exec')
            return True, "语法正确"
        except SyntaxError as e:
            return False, f"语法错误: 第{e.lineno}行: {e.msg}"
        except Exception as e:
            return False, f"编译错误: {str(e)}"
    
    @classmethod
    def check_safety(cls, code: str) -> Tuple[bool, str]:
        """
        检查代码安全性
        
        Args:
            code: Python代码
            
        Returns:
            (是否安全, 错误信息)
        """
        # 检查危险操作
        for pattern, reason in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"包含危险操作: {reason} (模式: {pattern})"
        
        # 检查文件写入操作的路径
        write_matches = re.findall(r'open\s*\(([^)]+)[\'"]w', code)
        for match in write_matches:
            # 提取路径
            path_match = re.search(r'[\'"]([^\'"]+)[\'"]', match)
            if path_match:
                path = path_match.group(1)
                # 检查是否在允许的路径内
                if not any(path.startswith(allowed) for allowed in cls.ALLOWED_WRITE_PATHS):
                    return False, f"写入文件路径不安全: {path}。只允许写入: {', '.join(cls.ALLOWED_WRITE_PATHS)}"
        
        return True, "安全检查通过"
    
    @classmethod
    def validate(cls, code: str) -> Tuple[bool, str]:
        """
        完整验证（语法 + 安全）
        
        Args:
            code: Python代码
            
        Returns:
            (是否有效, 错误信息)
        """
        # 1. 验证语法
        valid, msg = cls.validate_syntax(code)
        if not valid:
            return False, msg
        
        # 2. 检查安全性
        safe, msg = cls.check_safety(code)
        if not safe:
            return False, msg
        
        return True, "验证通过"


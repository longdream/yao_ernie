"""
流程解析器
解析工作流JSON，构建依赖图，生成执行顺序
"""
from typing import Dict, Any, List, Set
from collections import deque

from planscope.core.exceptions import PlanParsingError, DependencyError


class PlanParser:
    """
    流程解析器
    分析依赖关系并生成拓扑排序的执行顺序
    """
    
    def __init__(self, logger_manager):
        """
        初始化流程解析器
        
        Args:
            logger_manager: 日志管理器
        """
        self.logger_manager = logger_manager
        self.logger = logger_manager.get_logger("plan_parser")
    
    def parse(self, plan_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析工作流JSON
        
        Args:
            plan_json: 工作流JSON对象
            
        Returns:
            解析结果，包含执行顺序和依赖图
            
        Raises:
            PlanParsingError: 解析失败
        """
        self.logger.info("开始解析工作流")
        
        try:
            steps = plan_json["steps"]
            
            # 构建步骤映射
            step_map = self._build_step_map(steps)
            
            # 构建依赖图
            dependency_graph = self._build_dependency_graph(steps)
            
            # 检测循环依赖
            self._detect_circular_dependencies(dependency_graph)
            
            # 生成拓扑排序的执行顺序
            execution_order = self._topological_sort(dependency_graph)
            
            self.logger.info(f"工作流解析成功，执行顺序: {execution_order}")
            
            return {
                "step_map": step_map,
                "dependency_graph": dependency_graph,
                "execution_order": execution_order,
                "step_count": len(steps)
            }
            
        except Exception as e:
            error_msg = f"工作流解析失败: {str(e)}"
            self.logger.error(error_msg)
            raise PlanParsingError(error_msg) from e
    
    def _build_step_map(self, steps: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        """
        构建步骤ID到步骤对象的映射
        
        Args:
            steps: 步骤列表
            
        Returns:
            步骤映射字典
        """
        step_map = {}
        for step in steps:
            step_id = step["step_id"]
            step_map[step_id] = step
        return step_map
    
    def _build_dependency_graph(self, steps: List[Dict[str, Any]]) -> Dict[int, List[int]]:
        """
        构建依赖图
        
        Args:
            steps: 步骤列表
            
        Returns:
            依赖图，格式: {step_id: [依赖的step_id列表]}
        """
        dependency_graph = {}
        
        for step in steps:
            step_id = step["step_id"]
            dependencies = step.get("dependencies", [])
            dependency_graph[step_id] = dependencies
        
        return dependency_graph
    
    def _detect_circular_dependencies(self, dependency_graph: Dict[int, List[int]]) -> None:
        """
        检测循环依赖
        
        Args:
            dependency_graph: 依赖图
            
        Raises:
            DependencyError: 存在循环依赖
        """
        visited = set()
        rec_stack = set()
        
        def has_cycle(node: int, path: List[int]) -> bool:
            """DFS检测环"""
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in dependency_graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, path):
                        return True
                elif neighbor in rec_stack:
                    # 找到环
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    raise DependencyError(f"检测到循环依赖: {' -> '.join(map(str, cycle))}")
            
            path.pop()
            rec_stack.remove(node)
            return False
        
        for node in dependency_graph:
            if node not in visited:
                has_cycle(node, [])
    
    def _topological_sort(self, dependency_graph: Dict[int, List[int]]) -> List[int]:
        """
        使用Kahn算法进行拓扑排序
        
        Args:
            dependency_graph: 依赖图，格式: {step_id: [依赖的step_id列表]}
            
        Returns:
            拓扑排序后的步骤ID列表
            
        Raises:
            DependencyError: 存在循环依赖
        """
        # 计算每个节点的入度（有多少个节点依赖它）
        in_degree = {node: 0 for node in dependency_graph}
        
        # 遍历所有节点，计算入度
        for node in dependency_graph:
            # node依赖的每个节点，其入度加1
            for dep in dependency_graph[node]:
                # 注意：这里是node依赖dep，所以是node的入度加1，不是dep的
                in_degree[node] = in_degree.get(node, 0) + 1
        
        # 将入度为0的节点加入队列（没有依赖的节点）
        queue = deque([node for node in in_degree if in_degree[node] == 0])
        result = []
        
        while queue:
            # 取出入度为0的节点
            node = queue.popleft()
            result.append(node)
            
            # 找到所有依赖当前节点的其他节点，减少它们的入度
            for other_node in dependency_graph:
                if node in dependency_graph[other_node]:
                    in_degree[other_node] -= 1
                    if in_degree[other_node] == 0:
                        queue.append(other_node)
        
        # 如果结果数量不等于节点数量，说明存在循环依赖
        if len(result) != len(dependency_graph):
            raise DependencyError("存在循环依赖，无法生成执行顺序")
        
        return result
    
    def get_step_dependencies(self,
                             step_id: int,
                             dependency_graph: Dict[int, List[int]]) -> List[int]:
        """
        获取指定步骤的所有依赖
        
        Args:
            step_id: 步骤ID
            dependency_graph: 依赖图
            
        Returns:
            依赖的步骤ID列表
        """
        return dependency_graph.get(step_id, [])
    
    def get_dependent_steps(self,
                           step_id: int,
                           dependency_graph: Dict[int, List[int]]) -> List[int]:
        """
        获取依赖指定步骤的所有步骤
        
        Args:
            step_id: 步骤ID
            dependency_graph: 依赖图
            
        Returns:
            依赖该步骤的步骤ID列表
        """
        dependent_steps = []
        for node, deps in dependency_graph.items():
            if step_id in deps:
                dependent_steps.append(node)
        return dependent_steps


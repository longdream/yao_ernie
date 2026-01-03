"""
ACE (Agentic Context Engineering) 框架
可自我进化的工作流引擎
"""
from planscope.ace.context_entry import ContextEntry, ContextEntryType
from planscope.ace.execution_trace import ExecutionTrace
from planscope.ace.context_manager import ContextManager
from planscope.ace.generator import ACEGenerator
from planscope.ace.reflector import ACEReflector
from planscope.ace.curator import ACECurator
from planscope.ace.task_matcher import TaskMatcher
from planscope.ace.llm_analyzer import LLMAnalyzer
from planscope.ace.tool_understanding_agent import ToolUnderstandingAgent
from planscope.ace.reflection_chain import ReflectionChain, ReflectionChainEntry
from planscope.ace.reflection_chain_viewer import ReflectionChainViewer, generate_html_report

__all__ = [
    'ContextEntry',
    'ContextEntryType',
    'ExecutionTrace',
    'ContextManager',
    'ACEGenerator',
    'ACEReflector',
    'ACECurator',
    'TaskMatcher',
    'LLMAnalyzer',
    'ToolUnderstandingAgent',
    'ReflectionChain',
    'ReflectionChainEntry',
    'ReflectionChainViewer',
    'generate_html_report'
]

__version__ = '1.0.2'


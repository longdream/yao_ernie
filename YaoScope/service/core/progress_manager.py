"""
全局进度管理器 - 管理所有 session 的执行进度
"""
import asyncio
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class StepStatus:
    """步骤状态"""
    step: str           # 步骤名称
    status: str         # 状态描述
    timestamp: float    # 时间戳
    # Extended fields for richer progress info
    kind: str = "status"  # status | plan_ready | step_start | step_done | step_error
    step_id: Optional[int] = None
    tool: Optional[str] = None
    description: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class ProgressManager:
    """全局进度管理器 - 管理所有 session 的执行进度"""
    _instance = None
    
    def __init__(self):
        self._sessions: Dict[str, asyncio.Queue] = {}
    
    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def get_or_create_session(self, session_id: str) -> asyncio.Queue:
        """获取或创建 session 队列 (幂等操作)"""
        if session_id not in self._sessions:
            self._sessions[session_id] = asyncio.Queue()
            print(f"[ProgressManager] 创建新 session (缓冲模式): {session_id}")
        else:
            print(f"[ProgressManager] 复用现有 session: {session_id}")
        return self._sessions[session_id]
    
    def publish(self, session_id: str, step: str, status: str, **kwargs):
        """发布步骤状态 (如果 session 不存在会自动创建，实现消息缓冲)"""
        # 自动获取或创建 session，确保消息不丢失
        queue = self.get_or_create_session(session_id)
        
        try:
            queue.put_nowait(StepStatus(
                step=step,
                status=status,
                timestamp=datetime.now().timestamp(),
                **kwargs
            ))
            print(f"[ProgressManager] ✅ 状态已入队 [{session_id}]: {status}")
        except Exception as e:
            print(f"[ProgressManager] ❌ 入队失败: {e}")
    
    def publish_plan_ready(self, session_id: str, steps: List[Dict[str, Any]]):
        """发布 plan_ready 事件，包含所有步骤信息"""
        queue = self.get_or_create_session(session_id)
        
        try:
            queue.put_nowait(StepStatus(
                step="plan_ready",
                status=f"工作流已生成，共 {len(steps)} 个步骤",
                timestamp=datetime.now().timestamp(),
                kind="plan_ready",
                data={"steps": steps}
            ))
            print(f"[ProgressManager] ✅ plan_ready 已入队 [{session_id}]: {len(steps)} 步骤")
        except Exception as e:
            print(f"[ProgressManager] ❌ plan_ready 入队失败: {e}")
    
    def publish_step_start(self, session_id: str, step_id: int, tool: str, description: str):
        """发布 step_start 事件"""
        queue = self.get_or_create_session(session_id)
        
        try:
            queue.put_nowait(StepStatus(
                step=f"step_{step_id}",
                status=f"正在执行步骤 {step_id}: {description}",
                timestamp=datetime.now().timestamp(),
                kind="step_start",
                step_id=step_id,
                tool=tool,
                description=description
            ))
            print(f"[ProgressManager] ✅ step_start [{session_id}]: 步骤 {step_id} ({tool})")
        except Exception as e:
            print(f"[ProgressManager] ❌ step_start 入队失败: {e}")
    
    def publish_step_done(self, session_id: str, step_id: int, tool: str, description: str):
        """发布 step_done 事件"""
        queue = self.get_or_create_session(session_id)
        
        try:
            queue.put_nowait(StepStatus(
                step=f"step_{step_id}",
                status=f"步骤 {step_id} 完成: {description}",
                timestamp=datetime.now().timestamp(),
                kind="step_done",
                step_id=step_id,
                tool=tool,
                description=description
            ))
            print(f"[ProgressManager] ✅ step_done [{session_id}]: 步骤 {step_id} ({tool})")
        except Exception as e:
            print(f"[ProgressManager] ❌ step_done 入队失败: {e}")
    
    def publish_step_error(self, session_id: str, step_id: int, tool: str, error: str):
        """发布 step_error 事件"""
        queue = self.get_or_create_session(session_id)
        
        try:
            queue.put_nowait(StepStatus(
                step=f"step_{step_id}",
                status=f"步骤 {step_id} 失败: {error[:100]}",
                timestamp=datetime.now().timestamp(),
                kind="step_error",
                step_id=step_id,
                tool=tool,
                error=error
            ))
            print(f"[ProgressManager] ✅ step_error [{session_id}]: 步骤 {step_id} ({tool})")
        except Exception as e:
            print(f"[ProgressManager] ❌ step_error 入队失败: {e}")
    
    def close_session(self, session_id: str):
        """关闭 session"""
        if session_id in self._sessions:
            try:
                self._sessions[session_id].put_nowait(None)  # 发送结束信号
                print(f"[ProgressManager] 发送关闭信号: {session_id}")
                # 不立即删除，等待 SSE 端点读取完成信号
            except Exception as e:
                print(f"[ProgressManager] 发送关闭信号失败: {e}")
    
    def remove_session(self, session_id: str):
        """移除 session（SSE 端点调用，彻底清理）"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            print(f"[ProgressManager] 移除 session: {session_id}")

"""
向量数据库管理API路由
"""
import json
import asyncio
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, HTTPException

from service.core.planscope_wrapper import PlanScopeWrapper

router = APIRouter(prefix="/vector_db", tags=["vector_db"])


@router.post("/migrate")
async def migrate_tasks():
    """
    迁移任务到向量数据库
    
    将现有的任务文件迁移到ChromaDB向量数据库
    """
    try:
        # 获取PlanScope实例
        if not PlanScopeWrapper.is_initialized():
            raise HTTPException(status_code=500, detail="PlanScope未初始化")
        
        planscope = PlanScopeWrapper.get_instance()
        vector_db = planscope.vector_db_manager
        
        if not vector_db or not vector_db.is_available():
            raise HTTPException(status_code=500, detail="向量数据库不可用")
        
        # 获取任务目录
        task_dir = Path(planscope.storage_manager.get_path("tasks"))
        
        if not task_dir.exists():
            return {
                "success": True,
                "message": "任务目录不存在，无需迁移",
                "migrated": 0,
                "skipped": 0,
                "failed": 0
            }
        
        # 扫描任务文件
        task_files = list(task_dir.glob("task_*.json"))
        
        if not task_files:
            return {
                "success": True,
                "message": "没有需要迁移的任务",
                "migrated": 0,
                "skipped": 0,
                "failed": 0
            }
        
        # 迁移统计
        migrated_count = 0
        skipped_count = 0
        failed_count = 0
        failed_tasks = []
        
        # 迁移每个任务
        for task_file in task_files:
            try:
                # 读取任务数据
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = json.load(f)
                
                flow_id = task_data.get('flow_id', '')
                # 尝试多个可能的字段名
                task_description = (task_data.get('original_query') or 
                                   task_data.get('task_description') or
                                   task_data.get('plan_json', {}).get('original_query', ''))
                success = task_data.get('success', False)
                
                if not flow_id or not task_description:
                    failed_count += 1
                    failed_tasks.append(f"{task_file.name}: 缺少必要字段")
                    continue
                
                # 检查是否已存在
                existing = await vector_db.get_task(flow_id)
                if existing:
                    skipped_count += 1
                    continue
                
                # 添加到向量数据库
                result = await vector_db.add_task(
                    flow_id=flow_id,
                    task_description=task_description,
                    metadata={
                        'success': success,
                        'app_name': task_data.get('app_name', 'unknown'),
                        'created_at': task_data.get('created_at', ''),
                        'steps_count': len(task_data.get('steps', [])),
                        'task_id': task_data.get('task_id', f"task_{flow_id}")
                    }
                )
                
                if result:
                    migrated_count += 1
                else:
                    failed_count += 1
                    failed_tasks.append(f"{task_file.name}: 添加失败")
                
            except Exception as e:
                failed_count += 1
                failed_tasks.append(f"{task_file.name}: {str(e)}")
        
        return {
            "success": True,
            "message": f"迁移完成: {migrated_count}个成功, {skipped_count}个跳过, {failed_count}个失败",
            "total": len(task_files),
            "migrated": migrated_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "failed_tasks": failed_tasks[:10]  # 最多返回10个失败任务
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"迁移失败: {str(e)}")


@router.get("/stats")
async def get_vector_db_stats():
    """
    获取向量数据库统计信息
    """
    try:
        if not PlanScopeWrapper.is_initialized():
            raise HTTPException(status_code=500, detail="PlanScope未初始化")
        
        planscope = PlanScopeWrapper.get_instance()
        vector_db = planscope.vector_db_manager
        
        if not vector_db or not vector_db.is_available():
            return {
                "available": False,
                "message": "向量数据库不可用"
            }
        
        stats = vector_db.get_stats()
        
        return {
            "available": True,
            "stats": stats
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


"""
Memory API路由 - LLM QA记录管理
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pathlib import Path
import json
from typing import Optional
from datetime import datetime

router = APIRouter()


class MarkQARequest(BaseModel):
    """标记QA状态请求"""
    status: str  # correct/incorrect/unmarked
    reason: str = ""


@router.get("/llm_qa/list")
async def list_qa_records(status: str = "all", model_type: str = "all", limit: int = 100):
    """列出QA记录"""
    try:
        qa_dir = Path("service/data/memories/qa_records")
        qa_dir.mkdir(parents=True, exist_ok=True)
        
        records = []
        for qa_file in qa_dir.glob("qa_*.json"):
            try:
                with open(qa_file, 'r', encoding='utf-8') as f:
                    record = json.load(f)
                    
                    # 过滤status
                    if status != "all" and record.get("status") != status:
                        continue
                    
                    # 过滤model_type
                    if model_type != "all" and record.get("model_type") != model_type:
                        continue
                    
                    records.append(record)
            except Exception as e:
                print(f"[WARN] 读取QA记录失败 {qa_file}: {e}")
                continue
        
        # 按时间排序，最新的在前
        records.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return JSONResponse(
            content={
                "success": True,
                "records": records[:limit]
            },
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        print(f"[ERROR] 列出QA记录失败: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.get("/llm_qa/statistics")
async def get_qa_statistics():
    """获取统计信息"""
    try:
        qa_dir = Path("service/data/memories/qa_records")
        qa_dir.mkdir(parents=True, exist_ok=True)
        
        total = 0
        correct = incorrect = unmarked = 0
        vl_count = llm_count = 0
        light_model_usage = 0
        
        for qa_file in qa_dir.glob("qa_*.json"):
            try:
                total += 1
                with open(qa_file, 'r', encoding='utf-8') as f:
                    record = json.load(f)
                    status = record.get("status", "unmarked")
                    if status == "correct":
                        correct += 1
                    elif status == "incorrect":
                        incorrect += 1
                    else:
                        unmarked += 1
                    
                    # 统计model_type
                    model_type = record.get("model_type", "llm")
                    if model_type == "vl":
                        vl_count += 1
                    else:
                        llm_count += 1
                    
                    # 统计light model使用
                    if record.get("model_used", "").lower().find("light") >= 0:
                        light_model_usage += 1
            except:
                continue
        
        correct_rate = f"{(correct / total * 100):.1f}%" if total > 0 else "0%"
        
        return JSONResponse(
            content={
                "success": True,
                "statistics": {
                    "total": total,
                    "correct": correct,
                    "incorrect": incorrect,
                    "unmarked": unmarked,
                    "correct_rate": correct_rate,
                    "vl_count": vl_count,
                    "llm_count": llm_count,
                    "light_model_usage": light_model_usage
                }
            },
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        print(f"[ERROR] 获取统计信息失败: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.get("/llm_qa/{qa_id}")
async def get_qa_record(qa_id: str):
    """获取QA详情"""
    try:
        qa_file = Path(f"service/data/memories/qa_records/{qa_id}.json")
        if not qa_file.exists():
            return JSONResponse(
                content={"success": False, "error": "记录不存在"},
                status_code=404,
                media_type="application/json; charset=utf-8"
            )
        
        with open(qa_file, 'r', encoding='utf-8') as f:
            record = json.load(f)
        
        return JSONResponse(
            content={"success": True, "record": record},
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        print(f"[ERROR] 获取QA记录失败: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.put("/llm_qa/{qa_id}/mark")
async def mark_qa_status(qa_id: str, request: MarkQARequest):
    """标记QA状态"""
    try:
        qa_file = Path(f"service/data/memories/qa_records/{qa_id}.json")
        if not qa_file.exists():
            return JSONResponse(
                content={"success": False, "error": "记录不存在"},
                status_code=404,
                media_type="application/json; charset=utf-8"
            )
        
        with open(qa_file, 'r', encoding='utf-8') as f:
            record = json.load(f)
        
        record["status"] = request.status
        record["mark_reason"] = request.reason
        record["marked_at"] = datetime.now().isoformat()
        
        with open(qa_file, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        
        print(f"[MARK_QA] {qa_id} 标记为 {request.status}")
        
        return JSONResponse(
            content={"success": True, "record": record},
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        print(f"[ERROR] 标记QA状态失败: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.delete("/llm_qa/{qa_id}")
async def delete_qa_record(qa_id: str):
    """删除QA记录"""
    try:
        qa_file = Path(f"service/data/memories/qa_records/{qa_id}.json")
        if not qa_file.exists():
            return JSONResponse(
                content={"success": False, "error": "记录不存在"},
                status_code=404,
                media_type="application/json; charset=utf-8"
            )
        
        # 删除文件
        qa_file.unlink()
        print(f"[DELETE_QA] 已删除QA记录: {qa_id}")
        
        return JSONResponse(
            content={"success": True, "message": "删除成功"},
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        print(f"[ERROR] 删除QA记录失败: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


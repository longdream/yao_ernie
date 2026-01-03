"""
API路由定义 - 完全兼容AgenticService接口
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json
import re
import asyncio

from service.config import service_config
from service.core.planscope_wrapper import PlanScopeWrapper
from service.core.progress_manager import ProgressManager

# 创建路由器
router = APIRouter()

# 导入子路由
from service.api import memory_routes, vector_db_routes

# 注册子路由
router.include_router(memory_routes.router)
router.include_router(vector_db_routes.router)

# 全局状态标志
_planscope_initialized = False


class ConfigRequest(BaseModel):
    """配置更新请求"""
    # 主模型配置
    main_model: str
    main_api_base: str
    main_api_key: str
    
    # 高级模型配置
    advanced_model: str
    advanced_api_base: str
    advanced_api_key: str
    
    # VL模型配置
    vl_model: str
    vl_api_base: str
    vl_api_key: str
    
    # 轻量模型配置
    light_model: str
    light_api_base: str
    light_api_key: str
    
    # Embedding模型配置
    embedding_model: str
    embedding_api_base: str
    embedding_api_key: str
    
    # Rerank模型配置
    rerank_model: str = ""
    rerank_api_base: str = ""
    rerank_api_key: str = ""


class AgentRequest(BaseModel):
    """Agent执行请求"""
    model_config = {"str_strip_whitespace": True}
    
    app_name: str
    window_title: Optional[str] = None
    prompt: str
    session_id: Optional[str] = None


class GeneratePlanRequest(BaseModel):
    """手动生成Plan请求"""
    task_description: str
    app_name: str = ""


class UpdatePromptRequest(BaseModel):
    """更新步骤Prompt请求"""
    new_prompt: str


class RegeneratePromptRequest(BaseModel):
    """重新生成步骤Prompt请求"""
    additional_instructions: str = ""


@router.get("/health")
async def health_check():
    """健康检查"""
    global _planscope_initialized
    return JSONResponse(
        content={
            "status": "healthy" if _planscope_initialized else "waiting_for_config",
            "agent_initialized": _planscope_initialized,
            "agent_ready": _planscope_initialized,
            "framework": "PlanScope",
            "message": "PlanScope ready" if _planscope_initialized else "Waiting for configuration from Rust frontend"
        },
        media_type="application/json; charset=utf-8"
    )


@router.get("/agent/progress/{session_id}")
async def agent_progress(session_id: str):
    """SSE 端点：推送任务执行进度"""
    pm = ProgressManager.get_instance()
    # 使用 get_or_create_session 来获取可能已经由 execute_agent 创建的队列（包含缓冲消息）
    queue = pm.get_or_create_session(session_id)
    
    async def event_generator():
        try:
            print(f"[SSE] 开始为 session {session_id} 推送进度")
            while True:
                # 等待队列中的状态，超时时间60秒
                status = await asyncio.wait_for(queue.get(), timeout=60)
                
                if status is None:  # 结束信号
                    print(f"[SSE] Session {session_id} 收到结束信号")
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    break
                
                # 发送状态（包含扩展字段）
                data = {
                    'step': status.step,
                    'status': status.status,
                    'timestamp': status.timestamp,
                    'kind': getattr(status, 'kind', 'status'),
                }
                
                # 添加可选的扩展字段
                if hasattr(status, 'step_id') and status.step_id is not None:
                    data['step_id'] = status.step_id
                if hasattr(status, 'tool') and status.tool is not None:
                    data['tool'] = status.tool
                if hasattr(status, 'description') and status.description is not None:
                    data['description'] = status.description
                if hasattr(status, 'error') and status.error is not None:
                    data['error'] = status.error
                if hasattr(status, 'data') and status.data is not None:
                    data['data'] = status.data
                
                print(f"[SSE] 推送状态: {data.get('kind', 'status')} - {data.get('status', '')[:50]}")
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                
        except asyncio.TimeoutError:
            print(f"[SSE] Session {session_id} 超时")
            yield f"data: {json.dumps({'timeout': True})}\n\n"
        except Exception as e:
            # 忽略连接重置错误（前端主动断开）
            if "WinError 10054" in str(e) or "ConnectionResetError" in str(e):
                print(f"[SSE] Session {session_id} 连接已断开 (正常)")
                return
                
            print(f"[SSE] Session {session_id} 错误: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # 清理 session
            pm.remove_session(session_id)
            print(f"[SSE] Session {session_id} 已关闭")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用 nginx 缓冲
        }
    )


@router.post("/config/update")
async def update_config(config: ConfigRequest):
    """更新配置 - 动态初始化PlanScope"""
    global _planscope_initialized
    
    try:
        print("[INPUT] 接收到配置更新请求")
        print(f"[CONFIG] 主模型: {config.main_model} @ {config.main_api_base}")
        print(f"[BRAIN] 高级模型: {config.advanced_model} @ {config.advanced_api_base}")
        print(f"[VISION] 视觉模型: {config.vl_model} @ {config.vl_api_base}")
        print(f"[FAST] 轻量模型: {config.light_model} @ {config.light_api_base}")
        print(f"[EMBED] Embedding模型: {config.embedding_model} @ {config.embedding_api_base}")
        print(f"[RERANK] Rerank模型: {config.rerank_model} @ {config.rerank_api_base}")
        
        # 构建配置字典
        main_config = {
            "model_name": config.main_model,
            "api_key": config.main_api_key,
            "api_base": config.main_api_base
        }
        
        advanced_config = {
            "model_name": config.advanced_model,
            "api_key": config.advanced_api_key,
            "api_base": config.advanced_api_base
        }
        
        vl_config = {
            "model_name": config.vl_model,
            "api_key": config.vl_api_key,
            "api_base": config.vl_api_base
        }
        
        light_config = {
            "model_name": config.light_model,
            "api_key": config.light_api_key,
            "api_base": config.light_api_base
        }
        
        embedding_config = {
            "model_name": config.embedding_model,
            "api_key": config.embedding_api_key,
            "api_base": config.embedding_api_base
        }
        
        rerank_config = {
            "model_name": config.rerank_model,
            "api_key": config.rerank_api_key,
            "api_base": config.rerank_api_base
        }
        
        # 初始化PlanScope
        print("[INIT] 初始化PlanScope...")
        PlanScopeWrapper.initialize(
            main_config, advanced_config, vl_config, light_config, embedding_config, rerank_config,
            work_dir=service_config.work_dir
        )
        print("[OK] PlanScope初始化成功")
        
        _planscope_initialized = True
        
        return JSONResponse(
            content={
                "success": True,
                "message": "PlanScope配置更新成功",
                "updated_at": __import__('datetime').datetime.now().isoformat(),
                "agent_initialized": True,
                "models_configured": 5,
                "framework": "PlanScope",
                "models": {
                    "main_model": config.main_model,
                    "advanced_model": config.advanced_model,
                    "vl_model": config.vl_model,
                    "light_model": config.light_model,
                    "embedding_model": config.embedding_model
                }
            },
            media_type="application/json; charset=utf-8"
        )
            
    except Exception as e:
        print(f"[ERROR] 配置更新失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"配置更新失败: {str(e)}")


@router.post("/agent/execute")
async def execute_agent(request: AgentRequest):
    """执行Agent任务（核心接口）"""
    global _planscope_initialized
    
    # 生成或使用提供的 session_id
    import time
    session_id = request.session_id or f"session_{int(time.time() * 1000)}"
    
    # 获取进度管理器
    pm = ProgressManager.get_instance()
    
    try:
        if not _planscope_initialized:
            raise HTTPException(
                status_code=503, 
                detail="PlanScope未初始化，请先通过/config/update更新配置"
            )
        
        # 确保参数正确编码
        try:
            app_name = request.app_name.encode('utf-8').decode('utf-8') if request.app_name else ""
            prompt = request.prompt.encode('utf-8').decode('utf-8') if request.prompt else ""
        except (AttributeError, UnicodeError):
            app_name = str(request.app_name) if request.app_name else ""
            prompt = str(request.prompt) if request.prompt else ""
        
        print("\n" + "[START]" * 30)
        print("[START] 开始执行任务")
        print(f"[APP] 目标应用: {app_name}")
        print(f"[CHAT] 用户提示: {prompt}")
        print(f"[SESSION] Session ID: {session_id}")
        print(f"[SESSION] 来自请求: {request.session_id}")
        print("[START]" * 30)
        
        # 检查 ProgressManager 中的 session (DEBUG)
        print(f"[DEBUG] ProgressManager 当前 sessions: {list(pm._sessions.keys())}")
        
        # 获取PlanScope实例
        ps = PlanScopeWrapper.get_instance()
        
        # 步骤1: 生成plan
        print("\n[步骤1] 生成任务计划...")
        pm.publish(session_id, "task_start", "开始分析任务...")
        
        try:
            # 构建完整的用户需求描述（包含app_name上下文）
            # 如果有window_title，也包含进去
            if app_name and request.window_title:
                full_prompt = f"目标应用: {app_name} (窗口标题: {request.window_title})\n用户需求: {prompt}"
            elif app_name:
                full_prompt = f"目标应用: {app_name}\n用户需求: {prompt}"
            else:
                full_prompt = prompt
            
            plan = ps.generate_plan(
                prompt=full_prompt,
                session_id=session_id,  # 传递 session_id
                save_to_file=True
            )
            print(f"[步骤1] 计划生成成功: {plan.get('flow_id')}")
            print(f"   步骤数: {len(plan.get('steps', []))}")
            
            # 打印每个步骤的工具名称（便于调试）
            print("   工作流详情:")
            steps_info = []
            for step in plan.get('steps', []):
                step_id = step.get('step_id')
                tool_name = step.get('tool')
                desc = step.get('description', '')[:50]
                print(f"     步骤{step_id}: {tool_name} - {desc}...")
                steps_info.append({
                    'step_id': step_id,
                    'tool': tool_name,
                    'description': step.get('description', ''),
                    'dependencies': step.get('dependencies', [])
                })
            
            # 发布 plan_ready 事件，让前端可以显示所有步骤
            pm.publish_plan_ready(session_id, steps_info)
            
            # 将 session_id 注入到 plan 中，供 executor 使用
            plan['session_id'] = session_id
        except Exception as e:
            print(f"[步骤1] 计划生成失败: {e}")
            print(f"[步骤1] 异常类型: {type(e).__name__}")
            print(f"[步骤1] 异常详情: {repr(e)}")
            
            # 打印完整的traceback
            import traceback
            print(f"[步骤1] 完整traceback:")
            traceback.print_exc()
            
            return JSONResponse(
                content={
                    "success": False,
                    "result": None,
                    "reasoning": None,
                    "error": f"计划生成失败: {str(e)}"
                },
                status_code=200,
                media_type="application/json; charset=utf-8"
            )
        
        # 步骤2: 构建工具字典（从PlanScope的tool_registry获取所有工具）
        print("\n[步骤2] 准备工具...")
        tools = {}
        
        # 获取PlanScope中所有已注册的工具
        all_tools = ps.tool_registry.list_tools()
        
        for tool_name in all_tools:
            try:
                tool_func = ps.tool_registry.get(tool_name)
                tools[tool_name] = tool_func
            except Exception as e:
                print(f"[WARNING] 工具 {tool_name} 获取失败: {e}")
        
        print(f"[步骤2] 已准备 {len(tools)} 个工具")
        
        # 步骤3: 执行plan（在线程池中运行同步代码，避免阻塞事件循环）
        print("\n[步骤3] 执行任务计划...")
        pm.publish(session_id, "plan_execution", "正在执行工作流...")
        
        try:
            import functools
            loop = asyncio.get_event_loop()
            # 使用functools.partial正确传递参数
            execute_func = functools.partial(ps.execute_plan, plan, tools)
            result = await loop.run_in_executor(None, execute_func)
            print(f"[步骤3] 计划执行完成")
        except Exception as e:
            print(f"[步骤3] 计划执行失败: {e}")
            pm.close_session(session_id)  # 关闭 session
            return JSONResponse(
                content={
                    "success": False,
                    "result": None,
                    "reasoning": None,
                    "error": f"计划执行失败: {str(e)}"
                },
                status_code=200,
                media_type="application/json; charset=utf-8"
            )
        
        # 步骤4: 提取最终结果
        print("\n[步骤4] 汇总结果...")
        final_result = _extract_final_result(result)
        print(f"[步骤4] 提取的最终结果长度: {len(final_result) if final_result else 0}")
        
        # 输出最终结果内容（用于调试和验证）
        if final_result:
            print("\n" + "=" * 80)
            print("[最终结果内容]")
            print("=" * 80)
            print(final_result)
            print("=" * 80 + "\n")
        
        print("\n" + "[OK]" * 30)
        print(f"[OK] 任务执行完成: {result.get('success', False)}")
        print("[OK]" * 30 + "\n")
        
        # 关闭 session（发送完成信号）
        pm.close_session(session_id)
        
        # 返回兼容AgenticService的格式
        response_data = {
            "success": result.get("success", False),
            "result": final_result,
            "reasoning": None,
            "error": result.get("error"),
            "session_id": session_id  # 返回 session_id 给前端
        }
        
        json_content = json.dumps(response_data, ensure_ascii=False, indent=2)
        
        return Response(
            content=json_content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
        
    except HTTPException as he:
        print(f"[ERROR] Agent执行失败 (HTTP异常): {he.detail}")
        pm.close_session(session_id)  # 关闭 session
        return JSONResponse(
            content={
                "success": False,
                "result": None,
                "reasoning": None,
                "error": he.detail
            },
            status_code=200,
            media_type="application/json; charset=utf-8"
        )
    except Exception as e:
        print(f"[ERROR] Agent执行失败 (未知异常): {e}")
        pm.close_session(session_id)  # 关闭 session
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={
                "success": False,
                "result": None,
                "reasoning": None,
                "error": f"{type(e).__name__}: {str(e)}"
            },
            media_type="application/json; charset=utf-8"
        )


def _extract_final_result(result: Dict[str, Any]) -> Optional[str]:
    """
    从执行结果中提取最终输出
    
    Args:
        result: PlanScope执行结果
        
    Returns:
        最终结果字符串
    """
    # 优先使用final_step（最后一步的结果）
    if "final_step" in result:
        final_step = result["final_step"]
        if isinstance(final_step, dict):
            # 尝试多个可能的字段
            if "content" in final_step:
                return final_step["content"]
            elif "output" in final_step:
                output = final_step["output"]
                if isinstance(output, str):
                    return output
                elif isinstance(output, dict) and "content" in output:
                    return output["content"]
    
    # 备选方案：从step_results（字典）中提取
    step_results = result.get("step_results", {})
    if isinstance(step_results, dict):
        # 按照execution_order倒序查找
        execution_order = result.get("execution_order", [])
        for step_id in reversed(execution_order):
            step_data = step_results.get(step_id, {})
            if isinstance(step_data, dict):
                if "content" in step_data:
                    return step_data["content"]
                elif "output" in step_data:
                    output = step_data["output"]
                    if isinstance(output, str):
                        return output
                    elif isinstance(output, dict) and "content" in output:
                        return output["content"]
    
    # 如果没有找到结果，返回汇总信息
    if result.get("success"):
        executed_steps = result.get("executed_steps", [])
        return f"任务完成，共执行 {len(executed_steps)} 个步骤"
    else:
        return None


@router.get("/flows/list")
async def list_task_flows():
    """列出所有任务流程"""
    try:
        if not _planscope_initialized:
            return JSONResponse(
                content={"success": False, "error": "PlanScope未初始化"},
                status_code=503,
                media_type="application/json; charset=utf-8"
            )
        
        ps = PlanScopeWrapper.get_instance()
        
        # 获取任务历史
        flows = ps.get_task_history(limit=100)
        
        return JSONResponse(
            content={
                "success": True,
                "flows": flows,
                "count": len(flows)
            },
            media_type="application/json; charset=utf-8"
        )
    except Exception as e:
        print(f"[ERROR] 列出任务流程失败: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.get("/flows/{flow_id}")
async def get_task_flow(flow_id: str):
    """获取任务流程详情"""
    try:
        if not _planscope_initialized:
            return JSONResponse(
                content={"success": False, "error": "PlanScope未初始化"},
                status_code=503,
                media_type="application/json; charset=utf-8"
            )
        
        ps = PlanScopeWrapper.get_instance()
        flow = ps.load_plan(flow_id)
        
        if flow:
            # 提取关键字段到顶层（与/flows/list保持一致）
            # 添加steps_count
            if "steps" in flow:
                flow["steps_count"] = len(flow["steps"])
            
            # 从original_query中提取app_name（如果存在"目标应用:"）
            if "original_query" in flow and "app_name" not in flow:
                original_query = flow["original_query"]
                if "目标应用:" in original_query:
                    import re
                    match = re.search(r'目标应用:\s*([^\n(]+)', original_query)
                    if match:
                        flow["app_name"] = match.group(1).strip()
            
            return JSONResponse(
                content={
                    "success": True,
                    "flow": flow
                },
                media_type="application/json; charset=utf-8"
            )
        else:
            return JSONResponse(
                content={
                    "success": False,
                    "error": f"流程不存在: {flow_id}"
                },
                status_code=404,
                media_type="application/json; charset=utf-8"
            )
    except Exception as e:
        print(f"[ERROR] 获取任务流程失败: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.delete("/flows/{flow_id}")
async def delete_task_flow(flow_id: str):
    """删除任务流程"""
    try:
        if not _planscope_initialized:
            return JSONResponse(
                content={"success": False, "error": "PlanScope未初始化"},
                status_code=503,
                media_type="application/json; charset=utf-8"
            )
        
        success = PlanScopeWrapper.delete_plan(flow_id)
        
        return JSONResponse(
            content={
                "success": success,
                "message": f"流程已删除: {flow_id}" if success else "删除失败"
            },
            media_type="application/json; charset=utf-8"
        )
    except Exception as e:
        print(f"[ERROR] 删除任务流程失败: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


class FlowUpdateRequest(BaseModel):
    """流程更新请求 - 接受完整的flow对象"""
    model_config = {"extra": "allow"}  # 允许额外字段


@router.put("/flows/{flow_id}")
async def update_task_flow(flow_id: str, request: Request):
    """更新任务流程 - 接受完整的flow JSON"""
    try:
        if not _planscope_initialized:
            return JSONResponse(
                content={"success": False, "error": "PlanScope未初始化"},
                status_code=503,
                media_type="application/json; charset=utf-8"
            )
        
        # 解析请求体为JSON
        flow_data = await request.json()
        
        # 前端发送的是完整的flow对象，直接使用
        success = PlanScopeWrapper.update_plan(flow_id, flow_data)
        
        return JSONResponse(
            content={
                "success": success,
                "message": f"流程已更新: {flow_id}" if success else "更新失败"
            },
            media_type="application/json; charset=utf-8"
        )
    except Exception as e:
        print(f"[ERROR] 更新任务流程失败: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.post("/llm/debug")
async def debug_llm(request: Request):
    """LLM调试工具 - 用于测试和优化Prompt"""
    try:
        if not _planscope_initialized:
            return JSONResponse(
                content={"success": False, "error": "PlanScope未初始化"},
                status_code=503,
                media_type="application/json; charset=utf-8"
            )
        
        # 解析请求
        data = await request.json()
        prompt = data.get("prompt", "")
        model_type = data.get("model_type", "llm")  # llm 或 vl
        
        if not prompt:
            return JSONResponse(
                content={"success": False, "error": "Prompt不能为空"},
                status_code=400,
                media_type="application/json; charset=utf-8"
            )
        
        print(f"[DEBUG] LLM调试请求，model_type: {model_type}, prompt长度: {len(prompt)}")
        
        # 获取对应的模型客户端
        ps = PlanScopeWrapper.get_instance()
        
        # PlanScope对象有model_client属性（默认LLM模型）
        # 对于VL模型，我们需要从工具池中获取或使用默认的model_client
        model_client = ps.model_client
        
        print(f"[DEBUG] 使用模型客户端: {type(model_client).__name__}")
        
        # 调用LLM
        import asyncio
        response = await model_client.call_model(prompt=prompt, temperature=0.7)
        
        print(f"[DEBUG] LLM响应长度: {len(response)}")
        
        return JSONResponse(
            content={
                "success": True,
                "response": response,
                "model_type": model_type,
                "prompt_length": len(prompt),
                "response_length": len(response)
            },
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        print(f"[ERROR] LLM调试失败: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.get("/agents")
async def get_agents():
    """获取代理信息 - 兼容旧接口"""
    global _planscope_initialized
    
    agents = []
    if _planscope_initialized:
        agents.append({
            "name": "PlanScope",
            "type": "workflow_engine",
            "initialized": True,
            "config": {
                "framework": "PlanScope",
                "tools": ["screenshot_and_analyze", "ocr_extract_text", "general_llm_processor", "interaction"]
            }
        })
    
    return JSONResponse(
        content=agents,
        media_type="application/json; charset=utf-8"
    )


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str
    agent_type: Optional[str] = "assistant"
    stream: bool = False
    context: Optional[Dict[str, Any]] = None


@router.post("/chat")
async def chat(request: ChatRequest):
    """聊天接口 - 使用PlanScope处理聊天"""
    global _planscope_initialized
    
    if not _planscope_initialized:
        return JSONResponse(
            content={
                "message": "",
                "agent_name": "PlanScope",
                "success": False,
                "error": "服务未配置，请先配置模型"
            },
            status_code=503,
            media_type="application/json; charset=utf-8"
        )
    
    try:
        print(f"[CHAT] 接收到聊天请求: {request.message[:50]}...")
        
        # 使用agent_execute来处理聊天
        agent_request = AgentRequest(
            app_name="chat",
            prompt=request.message,
            session_id=None
        )
        
        result = await execute_agent(agent_request)
        result_dict = json.loads(result.body.decode())
        
        return JSONResponse(
            content={
                "message": result_dict.get("result", ""),
                "agent_name": "PlanScope",
                "success": result_dict.get("success", False),
                "error": result_dict.get("error")
            },
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        print(f"[ERROR] 聊天失败: {e}")
        return JSONResponse(
            content={
                "message": "",
                "agent_name": "PlanScope",
                "success": False,
                "error": str(e)
            },
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天 - 暂不支持，返回普通响应"""
    # PlanScope当前不支持流式输出，返回完整结果
    return await chat(request)


class SystemAction(BaseModel):
    """系统操作请求"""
    action: str
    params: Optional[Dict[str, Any]] = {}


@router.post("/system/action")
async def system_action(request: SystemAction):
    """系统操作接口 - 兼容旧接口"""
    global _planscope_initialized
    
    if not _planscope_initialized:
        return JSONResponse(
            content={
                "success": False,
                "result": None,
                "error": "服务未配置，请先配置模型"
            },
            status_code=503,
            media_type="application/json; charset=utf-8"
        )
    
    try:
        print(f"[SYSTEM] 系统操作: {request.action}")
        
        # 根据操作类型生成对应的prompt
        if request.action == "take_screenshot":
            save_path = request.params.get("save_path", "")
            prompt = f"截取当前屏幕并保存{f'到{save_path}' if save_path else ''}"
            
        elif request.action == "input_text":
            text = request.params.get("text", "")
            target_app = request.params.get("target_app", "")
            prompt = f"在{target_app if target_app else '当前窗口'}输入文字: {text}"
            
        elif request.action == "get_active_window":
            prompt = "获取当前活动窗口信息"
            
        else:
            return JSONResponse(
                content={
                    "success": False,
                    "result": None,
                    "error": f"不支持的操作: {request.action}"
                },
                status_code=400,
                media_type="application/json; charset=utf-8"
            )
        
        # 使用agent_execute处理
        agent_request = AgentRequest(
            app_name=request.params.get("target_app", "system"),
            prompt=prompt,
            session_id=None
        )
        
        result = await execute_agent(agent_request)
        result_dict = json.loads(result.body.decode())
        
        return JSONResponse(
            content={
                "success": result_dict.get("success", False),
                "result": result_dict.get("result"),
                "error": result_dict.get("error")
            },
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        print(f"[ERROR] 系统操作失败: {e}")
        return JSONResponse(
            content={
                "success": False,
                "result": None,
                "error": str(e)
            },
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.post("/flows/generate")
async def generate_plan_manual(request: GeneratePlanRequest):
    """手动生成Plan（不执行）"""
    global _planscope_initialized
    
    if not _planscope_initialized:
        return JSONResponse(
            content={
                "success": False,
                "error": "服务未配置，请先配置模型"
            },
            status_code=503,
            media_type="application/json; charset=utf-8"
        )
    
    try:
        print(f"[GENERATE_PLAN] 手动生成Plan请求")
        print(f"[TASK] {request.task_description}")
        print(f"[APP] {request.app_name}")
        
        # 构建完整prompt
        if request.app_name:
            full_prompt = f"目标应用: {request.app_name}\n用户需求: {request.task_description}"
        else:
            full_prompt = request.task_description
        
        # 调用PlanScope生成Plan
        ps = PlanScopeWrapper.get_instance()
        plan = ps.generate_plan(
            prompt=full_prompt,
            save_to_file=True
        )
        
        # 标记为用户手动创建
        plan["user_created"] = True
        plan["editable"] = True
        
        # 重新保存Plan（包含新标记）
        ps.plan_generator._save_plan(plan)
        
        print(f"[SUCCESS] Plan生成成功: {plan.get('flow_id')}")
        print(f"[STEPS] 包含 {len(plan.get('steps', []))} 个步骤")
        
        return JSONResponse(
            content={
                "success": True,
                "flow_id": plan["flow_id"],
                "plan": plan
            },
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        print(f"[ERROR] Plan生成失败: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={
                "success": False,
                "error": str(e)
            },
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.put("/flows/{flow_id}/steps/{step_id}/prompt")
async def update_step_prompt(flow_id: str, step_id: int, request: UpdatePromptRequest):
    """手动更新步骤的Prompt"""
    global _planscope_initialized
    
    if not _planscope_initialized:
        return JSONResponse(
            content={"success": False, "error": "服务未配置"},
            status_code=503,
            media_type="application/json; charset=utf-8"
        )
    
    try:
        ps = PlanScopeWrapper.get_instance()
        
        # 1. 加载Plan JSON
        plan = ps.plan_generator.load_plan(flow_id)
        
        # 2. 更新步骤的Prompt
        if step_id < 1 or step_id > len(plan["steps"]):
            return JSONResponse(
                content={"success": False, "error": "步骤ID无效"},
                status_code=400,
                media_type="application/json; charset=utf-8"
            )
        
        step = plan["steps"][step_id - 1]
        if "prompt" not in step.get("tool_input", {}):
            return JSONResponse(
                content={"success": False, "error": "该步骤没有Prompt参数"},
                status_code=400,
                media_type="application/json; charset=utf-8"
            )
        
        step["tool_input"]["prompt"] = request.new_prompt
        
        # 3. 保存Plan JSON
        ps.plan_generator._save_plan(plan)
        
        # 4. 更新Prompt缓存
        from planscope.core.prompt_cache_manager import PromptCacheManager
        tool_name = step["tool"]
        cache_manager = PromptCacheManager(ps.work_dir, flow_id, ps.storage_manager)
        cache_manager.update_tool_prompt(tool_name, request.new_prompt)
        
        print(f"[UPDATE_PROMPT] 步骤{step_id}的Prompt已更新")
        
        return JSONResponse(
            content={"success": True, "plan": plan},
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        print(f"[ERROR] 更新Prompt失败: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.post("/flows/{flow_id}/steps/{step_id}/regenerate_prompt")
async def regenerate_step_prompt(flow_id: str, step_id: int, request: RegeneratePromptRequest):
    """使用ACE重新生成步骤的Prompt"""
    global _planscope_initialized
    
    if not _planscope_initialized:
        return JSONResponse(
            content={"success": False, "error": "服务未配置"},
            status_code=503,
            media_type="application/json; charset=utf-8"
        )
    
    try:
        ps = PlanScopeWrapper.get_instance()
        
        # 1. 加载Plan JSON
        plan = ps.plan_generator.load_plan(flow_id)
        
        if step_id < 1 or step_id > len(plan["steps"]):
            return JSONResponse(
                content={"success": False, "error": "步骤ID无效"},
                status_code=400,
                media_type="application/json; charset=utf-8"
            )
        
        step = plan["steps"][step_id - 1]
        tool_name = step["tool"]
        
        # 2. 获取工具元数据
        tool_metadata = ps.tool_registry.get_tool_metadata(tool_name)
        
        # 3. 调用ACE重新生成Prompt
        import asyncio
        new_prompt = asyncio.run(
            ps.plan_generator._generate_prompt_for_tool(
                tool_name=tool_name,
                tool_metadata=tool_metadata,
                step_description=step.get("description", ""),
                step_reasoning=step.get("reasoning", ""),
                llm_generated_prompt=request.additional_instructions
            )
        )
        
        # 4. 更新Plan JSON和缓存
        step["tool_input"]["prompt"] = new_prompt
        ps.plan_generator._save_plan(plan)
        
        from planscope.core.prompt_cache_manager import PromptCacheManager
        cache_manager = PromptCacheManager(ps.work_dir, flow_id, ps.storage_manager)
        cache_manager.update_tool_prompt(tool_name, new_prompt)
        
        print(f"[REGENERATE_PROMPT] 步骤{step_id}的Prompt已重新生成")
        
        return JSONResponse(
            content={
                "success": True,
                "new_prompt": new_prompt,
                "plan": plan
            },
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        print(f"[ERROR] 重新生成Prompt失败: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


async def reconstruct_plan_after_deletion(
    ps, plan: Dict, deleted_step: Dict, deleted_step_id: int
) -> Dict:
    """
    调用LLM重构Plan：
    1. 重新编号所有步骤
    2. 调整输入输出引用
    3. 确保不包含已删除的步骤
    """
    
    # 构建LLM Prompt
    prompt = f"""
你是一个工作流计划优化专家。用户删除了步骤{deleted_step_id}（工具：{deleted_step['tool']}），请重新调整整个Plan。

**重要规则**：
1. 不要再包含已删除的步骤{deleted_step_id}（工具：{deleted_step['tool']}）
2. 重新编号所有步骤（从1开始连续编号）
3. 调整所有步骤的输入输出引用（如果步骤3引用了步骤2的输出，而步骤2被删除，则步骤3应该引用步骤1的输出）
4. 保持原有步骤的工具和描述不变，只调整编号和输入输出引用
5. 确保工作流逻辑连贯

**当前Plan（已删除步骤{deleted_step_id}）**：
{json.dumps(plan, ensure_ascii=False, indent=2)}

**任务**：
请返回重构后的完整Plan JSON，包含：
- flow_id: 保持不变
- app_name: 保持不变
- user_request: 保持不变
- steps: 重新编号和调整后的步骤列表

只返回JSON，不要有其他说明文字。
"""
    
    # 调用LLM（使用plan_model_client或默认model_client）
    llm_client = ps.plan_model_client if ps.plan_model_client else ps.model_client
    response = await llm_client.call_model(prompt)
    
    # 解析LLM返回的JSON
    # 提取JSON（去除可能的markdown代码块标记）
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_str = response.strip()
    
    reconstructed_plan = json.loads(json_str)
    
    # 验证重构后的Plan
    if deleted_step_id <= len(reconstructed_plan["steps"]):
        # 检查是否还包含已删除的步骤
        for step in reconstructed_plan["steps"]:
            if step.get("tool") == deleted_step["tool"] and \
               step.get("description") == deleted_step.get("description"):
                raise ValueError(f"LLM重构失败：仍然包含已删除的步骤")
    
    return reconstructed_plan


@router.post("/flows/{flow_id}/steps/{step_id}/delete_and_reconstruct")
async def delete_step_and_reconstruct(flow_id: str, step_id: int):
    """删除步骤并调用LLM重构整个Plan"""
    global _planscope_initialized
    
    if not _planscope_initialized:
        return JSONResponse(
            content={"success": False, "error": "服务未配置"},
            status_code=503,
            media_type="application/json; charset=utf-8"
        )
    
    try:
        ps = PlanScopeWrapper.get_instance()
        
        # 1. 加载Plan JSON
        plan = ps.plan_generator.load_plan(flow_id)
        
        # 2. 验证步骤ID
        if step_id < 1 or step_id > len(plan["steps"]):
            return JSONResponse(
                content={"success": False, "error": "步骤ID无效"},
                status_code=400,
                media_type="application/json; charset=utf-8"
            )
        
        # 3. 删除步骤
        deleted_step = plan["steps"].pop(step_id - 1)
        
        # 4. 调用LLM重构Plan
        reconstructed_plan = await reconstruct_plan_after_deletion(
            ps, plan, deleted_step, step_id
        )
        
        # 5. 保存重构后的Plan
        ps.plan_generator._save_plan(reconstructed_plan)
        
        print(f"[DELETE_STEP] 步骤{step_id}已删除，Plan已重构")
        
        return JSONResponse(
            content={
                "success": True,
                "plan": reconstructed_plan,
                "message": f"步骤{step_id}已删除，Plan已重构"
            },
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        print(f"[ERROR] 删除步骤并重构失败: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500,
            media_type="application/json; charset=utf-8"
        )


@router.post("/shutdown")
async def shutdown_service():
    """关闭服务"""
    import os
    import signal
    
    print("🛑 接收到关闭服务请求")
    
    def delayed_shutdown():
        import time
        time.sleep(0.5)
        print("👋 YaoScope服务正在关闭...")
        os.kill(os.getpid(), signal.SIGTERM)
    
    import threading
    threading.Thread(target=delayed_shutdown, daemon=True).start()
    
    return JSONResponse(
        content={
            "success": True,
            "message": "服务即将关闭"
        },
        media_type="application/json; charset=utf-8"
    )


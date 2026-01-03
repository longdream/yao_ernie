"""
YaoScope Service - 基于PlanScope的HTTP服务
主入口文件
"""
import os
import sys
from pathlib import Path

# 修复事件循环冲突：允许嵌套事件循环
import nest_asyncio
nest_asyncio.apply()

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置控制台编码为UTF-8
if sys.platform == "win32":
    import locale
    try:
        locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')
    except:
        try:
            locale.setlocale(locale.LC_ALL, 'Chinese_China.UTF-8')
        except:
            pass
    
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
import uvicorn

from service.api.routes import router
from service.config import service_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动事件
    print("=" * 80)
    print("[START] Starting YaoScope Service (PlanScope Implementation)")
    print("=" * 80)
    print("[INFO] Service Features:")
    print("  - PlanScope Multi-Step Workflow Engine")
    print("  - ACE Adaptive Context Engine")
    print("  - Real Screenshot Tool with VL Analysis")
    print("  - Dynamic LLM Configuration via HTTP")
    print("  - Task Flow Management with JSON Persistence")
    print("  - Tool Pool and Auto-Selection")
    print("=" * 80)
    
    # 创建必要的目录
    os.makedirs(service_config.data_dir, exist_ok=True)
    os.makedirs(service_config.work_dir, exist_ok=True)
    os.makedirs(service_config.log_dir, exist_ok=True)
    os.makedirs("data/screenshots", exist_ok=True)
    os.makedirs("data/memories", exist_ok=True)
    os.makedirs("data/task_flows", exist_ok=True)
    
    print("[OK] YaoScope Service started successfully")
    print("[INFO] Waiting for configuration from Rust frontend via /config/update")
    print("=" * 80)
    
    yield
    
    # 关闭事件
    print("[STOP] Shutting down YaoScope Service...")
    from service.core.planscope_wrapper import PlanScopeWrapper
    PlanScopeWrapper.cleanup()
    print("[OK] Service shut down successfully")


# 创建FastAPI应用
app = FastAPI(
    title="YaoScope Service (PlanScope)",
    description="基于PlanScope的多步骤工作流服务",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# UTF-8编码中间件
@app.middleware("http")
async def ensure_utf8_encoding(request: Request, call_next):
    response = await call_next(request)
    if hasattr(response, 'headers'):
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json") and "charset" not in content_type:
            response.headers["content-type"] = "application/json; charset=utf-8"
    return response

# 注册路由
from service.api.memory_routes import router as memory_router
app.include_router(router)
app.include_router(memory_router)


if __name__ == "__main__":
    print("=" * 80)
    print("🚀 Starting YaoScope Service (PlanScope)")
    print("=" * 80)
    print(f"📍 Host: {service_config.host}")
    print(f"📍 Port: {service_config.port}")
    print("=" * 80)
    
    uvicorn.run(
        app, 
        host=service_config.host, 
        port=service_config.port
    )


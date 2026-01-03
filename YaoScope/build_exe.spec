# -*- mode: python ; coding: utf-8 -*-
"""
YaoScope Service PyInstaller 打包配置
用于将Python服务打包成独立的exe可执行文件
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# 项目根目录
project_root = os.path.abspath('.')

# 收集所有需要的数据文件
datas = [
    # PlanScope相关
    ('planscope', 'planscope'),
    
    # 服务配置和工具
    ('service/api', 'service/api'),
    ('service/core', 'service/core'),
    ('service/tools', 'service/tools'),
    ('service/config.py', 'service'),
    ('service/__init__.py', 'service'),
]

# 模型文件（如果存在）
if os.path.exists('models'):
    datas.append(('models', 'models'))

# 收集PaddleOCR和其他包的数据文件
try:
    datas += collect_data_files('paddleocr')
except:
    pass

try:
    datas += collect_data_files('paddle')
except:
    pass

try:
    datas += collect_data_files('fastapi')
except:
    pass

try:
    datas += collect_data_files('chromadb')
except:
    pass

# 收集所有隐藏导入
hiddenimports = [
    # FastAPI相关
    'fastapi',
    'fastapi.routing',
    'fastapi.middleware',
    'fastapi.middleware.cors',
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    
    # Pydantic
    'pydantic',
    'pydantic.fields',
    'pydantic.main',
    'pydantic_core',
    
    # LangChain
    'langchain_core',
    'langchain_openai',
    'openai',
    
    # OCR相关
    'paddleocr',
    'paddlepaddle',
    'cv2',
    'PIL',
    'numpy',
    
    # UI自动化
    'pyautogui',
    'pyperclip',
    'pywinauto',
    
    # 向量数据库
    'chromadb',
    'chromadb.api',
    'chromadb.config',
    
    # Windows相关
    'win32api',
    'win32con',
    'win32gui',
    'win32process',
    'pywintypes',
    
    # 其他
    'nest_asyncio',
    'json_repair',
    'psutil',
]

# 尝试收集子模块
try:
    hiddenimports += collect_submodules('service')
    hiddenimports += collect_submodules('planscope')
except:
    pass

a = Analysis(
    ['service/main.py'],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的包以减小体积
        'matplotlib',
        'scipy',
        'pandas',
        'jupyter',
        'notebook',
        'IPython',
        'tkinter',
        'test',
        'tests',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='YaoScope',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YaoScope',
)



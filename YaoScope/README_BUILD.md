# YaoScope 分发包构建说明

## 📦 两种打包方案

YaoScope提供两种独立分发方案：

### 方案1：基于Python Embedded的分发包（推荐）✨
- **Full版本**：包含所有依赖，完全离线使用
- **Lite版本**：首次启动自动下载依赖
- **特点**：体积可控、启动快、真正独立
- **使用工具**：Python Embedded + Rust启动器

### 方案2：PyInstaller打包（备选）
- 单个exe文件或文件夹
- 体积较大（500MB-1GB）
- 首次启动需要解压

---

## 🚀 快速开始：一键生成分发包

### 完整构建流程（从零开始）

```bash
# 1. 进入YaoScope目录
cd E:\work\RustWorks\yao\YaoScope

# 2. 创建并激活虚拟环境（如果不存在）
python -m venv venv
call venv\Scripts\activate.bat

# 3. 安装Python依赖
pip install -r requirements.txt

# 4. 执行一键构建脚本
build_dist.bat
```

**就这么简单！** 脚本会自动完成以下所有步骤：
- ✅ 下载Python 3.11嵌入式版本
- ✅ 构建Full版本（包含所有依赖）
- ✅ 构建Lite版本（精简版）
- ✅ 编译Rust启动器
- ✅ 整合生成最终分发包

**构建时间**：
- 首次构建：约 10-15 分钟（需要下载Python和安装依赖）
- 后续构建：约 5-8 分钟（使用缓存）

**构建完成后**，你将得到：
```
YaoScope/dist/
├── YaoScope-Full/    # 完整版（800MB-1.5GB，可直接使用）
└── YaoScope-Lite/    # 精简版（50-100MB，首次启动下载依赖）
```

---

## 📋 详细构建步骤说明

### 前置要求

1. **Python 3.9+** 已安装并在PATH中
2. **Rust工具链** 已安装（用于编译启动器）
3. **网络连接**（首次构建需要下载Python嵌入式版本）

验证环境：
```bash
python --version   # 应显示 Python 3.9 或更高
cargo --version    # 应显示 cargo 版本
```

**如果没有安装Rust**：
```bash
# Windows下载安装：
# 访问 https://rustup.rs/
# 下载并运行 rustup-init.exe
# 安装完成后重启终端
```

### 步骤1：准备虚拟环境

```bash
cd YaoScope

# 如果虚拟环境不存在，创建它
python -m venv venv

# 激活虚拟环境（Windows）
call venv\Scripts\activate.bat

# 安装依赖（确保环境完整）
pip install -r requirements.txt
```

**注意**：虚拟环境仅用于运行构建脚本，不会打包进最终产品。

### 步骤2：执行构建

```bash
# 运行分发包构建脚本
build_dist.bat
```

**构建过程详解**：

#### 阶段1：Python环境准备（约2-3分钟）
```
[步骤 1/3: 构建 Python 环境]
- 下载 python-3.11.9-embed-amd64.zip（约30MB，首次下载后会缓存）
- 下载 get-pip.py（pip安装脚本）
```

#### 阶段2：构建Full版本（约5-8分钟）
```
[构建 Full 版本]
- 解压Python到 dist/YaoScope-Full/python/
- 配置 python311._pth（启用site-packages）
- 安装pip到嵌入式Python
- 复制服务文件（service/、planscope/、models/）
- 安装所有依赖到 python/Lib/site-packages/
  （这一步最耗时，约5-8分钟，从清华镜像下载）
```

#### 阶段3：构建Lite版本（约30秒）
```
[构建 Lite 版本]
- 解压Python到 dist/YaoScope-Lite/python/
- 配置 python311._pth
- 安装pip（仅pip，不安装其他依赖）
- 复制服务文件
- 创建 launcher_config.json（标记为Lite版本）
```

#### 阶段4：编译Rust启动器（约30秒）
```
[步骤 2/3: 编译 Rust 启动器]
- 进入 launcher/ 目录
- 执行 cargo build --release
- 生成 launcher/target/release/YaoScope.exe
```

#### 阶段5：整合分发包（约5秒）
```
[步骤 3/3: 整合分发包]
- 复制 YaoScope.exe 到 dist/YaoScope-Full/
- 复制 YaoScope.exe 到 dist/YaoScope-Lite/
- 创建 README.txt 使用说明
```

**总耗时**：
- 首次构建：约 10-15 分钟
- 后续构建：约 5-8 分钟（使用缓存的Python包）
- 仅更新代码：约 1-2 分钟（跳过依赖安装）

### 步骤3：获取分发包

构建完成后，会在 `YaoScope/dist/` 目录生成两个独立的分发包：

```
YaoScope/dist/
├── YaoScope-Full/          # Full版本（完整离线版）
│   ├── YaoScope.exe        # Rust启动器（约200KB）
│   ├── python/             # Python 3.11嵌入式环境 + 所有依赖
│   │   ├── python.exe      # Python解释器
│   │   ├── python311.dll   # Python核心库
│   │   ├── Lib/
│   │   │   └── site-packages/  # 所有Python依赖包都在这里
│   │   │       ├── fastapi/
│   │   │       ├── paddleocr/
│   │   │       ├── langchain_core/
│   │   │       └── ... (所有requirements.txt中的包)
│   │   └── Scripts/        # pip等工具
│   ├── service/            # YaoScope服务代码
│   │   ├── main.py         # 服务入口
│   │   ├── api/            # API路由
│   │   ├── core/           # 核心逻辑
│   │   └── tools/          # 工具实现
│   ├── planscope/          # PlanScope核心引擎
│   ├── models/             # 模型文件（OCR等）
│   ├── requirements.txt    # 依赖清单（记录）
│   └── README.txt          # 用户使用说明
│
└── YaoScope-Lite/          # Lite版本（在线精简版）
    ├── YaoScope.exe        # Rust启动器（约200KB）
    ├── python/             # Python 3.11嵌入式环境（仅基础）
    │   ├── python.exe      # Python解释器
    │   ├── python311.dll   # Python核心库
    │   ├── Lib/
    │   │   └── site-packages/  # 仅包含pip（首次启动时自动安装其他包）
    │   │       └── pip/
    │   └── Scripts/
    ├── service/            # YaoScope服务代码
    ├── planscope/          # PlanScope核心引擎
    ├── models/             # 模型文件
    ├── requirements.txt    # 依赖清单（首次启动时使用）
    ├── launcher_config.json # 启动器配置
    │   # 内容：{"version": "lite", "pip_mirror": "...", "first_run": true}
    └── README.txt          # 用户使用说明
```

**关键文件说明**：

1. **YaoScope.exe**：
   - Rust编写的启动器
   - 负责检测环境、安装依赖（Lite版）、启动Python服务
   - 体积小（约200KB）

2. **python/** 目录：
   - Python 3.11 嵌入式版本（Embedded Python）
   - 完全独立，不依赖系统Python
   - Full版：包含所有依赖（约800MB-1.5GB）
   - Lite版：仅基础环境（约50-100MB）

3. **launcher_config.json**（仅Lite版）：
   - 标记为Lite版本
   - 指定pip镜像源（清华源）
   - `first_run: true` 表示首次启动需要安装依赖

**版本对比**：

| 特性 | Full版本 | Lite版本 |
|------|---------|---------|
| 体积 | 约800MB-1.5GB | 约50-100MB |
| 首次启动 | 直接运行（0秒等待） | 需要下载依赖（5-10分钟） |
| 后续启动 | 直接运行 | 直接运行（依赖已安装） |
| 网络要求 | 完全离线 | 首次需要网络 |
| 依赖安装位置 | 已安装在 python/Lib/site-packages/ | 首次启动时自动安装到 python/Lib/site-packages/ |
| 适用场景 | 离线环境、网络不稳定、需要立即使用 | 网络良好、需要小体积、可以等待首次安装 |
| 分发方式 | 压缩后约400-800MB | 压缩后约30-50MB |

**推荐选择**：
- 🎯 **离线部署** → 使用 Full 版本
- 🎯 **在线分发** → 使用 Lite 版本（下载快，首次启动自动安装）
- 🎯 **U盘拷贝** → 使用 Full 版本（无需网络）
- 🎯 **网络下载** → 使用 Lite 版本（体积小）

### 步骤4：测试分发包

#### 方式1：使用测试脚本（推荐）

```bash
# 在YaoScope目录下运行
test_dist.bat

# 会提示选择：
# 1. Full 版本 (完整离线版)
# 2. Lite 版本 (在线精简版)
# 3. 退出
```

#### 方式2：手动测试

**测试Full版本**：
```bash
cd dist\YaoScope-Full
YaoScope.exe
```

**预期输出**：
```
========================================
  YaoScope Service Launcher
========================================

[INFO] 工作目录: E:\...\dist\YaoScope-Full
[OK] Python 环境: E:\...\dist\YaoScope-Full\python\python.exe
[OK] 服务文件: E:\...\dist\YaoScope-Full\service\main.py

========================================
  启动 YaoScope 服务...
========================================

[START] Starting YaoScope Service (PlanScope Implementation)
...
[OK] YaoScope Service started successfully
[INFO] Waiting for configuration from Rust frontend via /config/update
```

**测试Lite版本**：
```bash
cd dist\YaoScope-Lite
YaoScope.exe
```

**预期输出（首次启动）**：
```
========================================
  YaoScope Service Launcher
========================================

[INFO] 工作目录: E:\...\dist\YaoScope-Lite
[OK] Python 环境: E:\...\dist\YaoScope-Lite\python\python.exe
[INFO] 检测到 Lite 版本配置

[INFO] 首次运行，需要安装依赖包
[INFO] 这可能需要 5-10 分钟，请耐心等待...

[INFO] 开始安装依赖...
[INFO] 镜像源: https://pypi.tuna.tsinghua.edu.cn/simple
Looking in indexes: https://pypi.tuna.tsinghua.edu.cn/simple
Collecting fastapi>=0.104.1...
...（安装过程）...

[OK] 依赖安装完成！

========================================
  启动 YaoScope 服务...
========================================
...
```

**验证服务**：

1. 打开浏览器访问：http://127.0.0.1:8765/docs
2. 应该看到 FastAPI 自动生成的 API 文档界面
3. 测试几个接口，确认服务正常

**停止服务**：
- 在控制台按 `Ctrl+C` 停止服务
- 或直接关闭控制台窗口

### 步骤5：打包分发

#### 压缩分发包

**使用命令行（PowerShell）**：
```powershell
# 进入dist目录
cd dist

# 压缩Full版本
Compress-Archive -Path YaoScope-Full -DestinationPath YaoScope-Full-v1.0.0.zip

# 压缩Lite版本
Compress-Archive -Path YaoScope-Lite -DestinationPath YaoScope-Lite-v1.0.0.zip
```

**使用图形界面**：
```
1. 进入 dist/ 目录
2. 右键点击 YaoScope-Full 文件夹
3. 选择"发送到" -> "压缩(zipped)文件夹"
   或使用 7-Zip/WinRAR："添加到压缩文件..."
4. 重命名为 YaoScope-Full-v1.0.0.zip
5. 对 YaoScope-Lite 重复相同操作
```

**压缩后大小**：
- Full版本：约 400-800MB（压缩后）
- Lite版本：约 30-50MB（压缩后）

#### 分发给用户

**方式1：网络下载**
- 上传到云盘（百度网盘、阿里云盘等）
- 或上传到文件服务器
- 提供下载链接给用户

**方式2：U盘拷贝**
- 直接复制zip文件到U盘
- 适合离线环境

**方式3：内网分发**
- 放到共享文件夹
- 或通过企业内网分发

#### 用户使用指南

**提供给用户的说明**：

```
YaoScope 使用说明
===================

1. 解压文件
   - 将 YaoScope-Full.zip 或 YaoScope-Lite.zip 解压到任意目录
   - 推荐解压到：C:\Program Files\YaoScope 或 D:\YaoScope

2. 启动服务
   - 进入解压后的文件夹
   - 双击 YaoScope.exe 启动服务
   - 首次启动可能需要：
     * 防火墙授权（点击"允许访问"）
     * Lite版本需要等待5-10分钟下载依赖（需要网络）

3. 访问服务
   - 打开浏览器
   - 访问：http://127.0.0.1:8765
   - 或查看API文档：http://127.0.0.1:8765/docs

4. 停止服务
   - 在控制台窗口按 Ctrl+C
   - 或直接关闭控制台窗口

注意事项：
- 确保端口 8765 未被占用
- Windows 10/11 64位系统
- Lite版本首次启动需要稳定的网络连接
```

#### 版本发布建议

**文件命名规范**：
```
YaoScope-Full-v1.0.0-win64.zip      # Full版本
YaoScope-Lite-v1.0.0-win64.zip      # Lite版本
```

**发布清单**：
- [ ] YaoScope-Full-v1.0.0-win64.zip
- [ ] YaoScope-Lite-v1.0.0-win64.zip
- [ ] README.txt（使用说明）
- [ ] CHANGELOG.txt（更新日志）
- [ ] LICENSE.txt（许可证，如果需要）

---

## 🔧 方案2：PyInstaller打包（备选）

如果不想使用Rust启动器，可以使用传统的PyInstaller方案。

### 步骤1：安装PyInstaller

```bash
cd YaoScope
call venv\Scripts\activate.bat
pip install pyinstaller
```

### 步骤2：执行打包

```bash
# 使用PyInstaller打包脚本（如果存在）
build_exe.bat
```

### 步骤3：获取可执行文件

打包完成后，可执行文件位于：
```
YaoScope/dist/YaoScope/
├── YaoScope.exe          # 主程序
├── _internal/            # 依赖库（PyInstaller自动生成）
├── README.txt            # 使用说明
└── ...其他文件
```

**注意**：PyInstaller方案体积较大且启动较慢，推荐使用方案1。

---

## 📋 使用打包后的程序

### 部署步骤

1. **复制整个文件夹**
   ```
   将 dist/YaoScope 整个文件夹复制到目标机器
   ```

2. **添加模型文件**（如果需要OCR功能）
   ```
   将 models/ 文件夹复制到 YaoScope.exe 同级目录
   ```

3. **运行程序**
   ```
   双击 YaoScope.exe 启动服务
   ```

### 验证服务

服务启动后，访问：
```
http://127.0.0.1:8765/docs
```

应该能看到FastAPI的API文档界面。

## ⚙️ 打包配置说明

### build_exe.spec

这是PyInstaller的配置文件，包含：

- **数据文件收集**：planscope、service、models等
- **隐藏导入**：FastAPI、PaddleOCR、LangChain等
- **排除模块**：matplotlib、scipy等不需要的大型库
- **压缩设置**：使用UPX压缩减小体积

### 自定义配置

如果需要修改打包配置，编辑 `build_exe.spec`：

```python
# 添加额外的数据文件
datas = [
    ('your_data', 'your_data'),
]

# 添加隐藏导入
hiddenimports = [
    'your_module',
]

# 修改exe名称
exe = EXE(
    ...
    name='YourAppName',
    icon='your_icon.ico',  # 添加图标
    ...
)
```

## 📊 打包后的特点

### ✅ 优点

1. **零依赖部署**：目标机器无需安装Python
2. **一键启动**：双击exe即可运行
3. **完整功能**：包含所有Python依赖
4. **便于分发**：可以直接分发给用户

### ⚠️ 限制

1. **体积较大**：约500MB-1GB（包含所有依赖）
2. **首次启动慢**：需要解压临时文件（10-30秒）
3. **仅Windows**：当前配置仅支持Windows平台
4. **模型文件**：大型模型需要单独复制

## 🔧 故障排除

### 打包失败

**问题**：PyInstaller报错找不到模块

**解决**：
1. 检查虚拟环境是否激活
2. 确保所有依赖已安装：`pip install -r requirements.txt`
3. 在 `build_exe.spec` 的 `hiddenimports` 中添加缺失的模块

**问题**：打包时内存不足

**解决**：
1. 关闭其他程序释放内存
2. 在 `build_exe.spec` 中排除更多不需要的包

### 运行失败

**问题**：双击exe无反应

**解决**：
1. 在cmd中运行 `YaoScope.exe` 查看错误信息
2. 检查杀毒软件是否拦截
3. 确保有足够的磁盘空间（至少2GB）

**问题**：服务启动但无法访问

**解决**：
1. 检查端口8765是否被占用
2. 查看控制台输出的错误信息
3. 确保防火墙允许程序运行

**问题**：OCR功能不可用

**解决**：
1. 确保 `models/` 文件夹存在
2. 检查模型文件是否完整
3. 查看日志中的具体错误

## 🎯 高级选项

### 单文件打包

如果想打包成单个exe文件（不推荐，会更慢）：

修改 `build_exe.spec`：
```python
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,  # 添加这行
    a.zipfiles,  # 添加这行
    a.datas,     # 添加这行
    [],
    name='YaoScope',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)

# 删除 COLLECT 部分
```

### 无控制台窗口

如果不想显示控制台窗口（不推荐，无法看到日志）：

```python
exe = EXE(
    ...
    console=False,  # 改为False
    ...
)
```

### 添加图标

准备一个 `.ico` 文件，然后：

```python
exe = EXE(
    ...
    icon='path/to/your/icon.ico',
    ...
)
```

## 📝 重要注意事项

### 构建环境要求

1. **Python环境**：
   - 必须在安装了所有依赖的虚拟环境中构建
   - 虚拟环境用于运行构建脚本，不会打包进去
   - Full版本会在嵌入式Python中重新安装依赖

2. **Rust工具链**：
   - 需要安装Rust（用于编译启动器）
   - 下载地址：https://rustup.rs/
   - 安装后重启终端

3. **网络连接**：
   - 首次构建需要下载Python嵌入式版本（约30MB）
   - Full版本构建时需要下载所有Python依赖
   - 建议使用国内镜像源（已配置清华源）

### 版本管理

1. **不要提交到Git**：
   ```bash
   # .gitignore 已配置忽略
   dist/
   build/
   distribution/*.zip
   launcher/target/
   ```

2. **缓存文件**：
   - `distribution/python-3.11.9-embed-amd64.zip` - Python嵌入式版本（会缓存）
   - `distribution/get-pip.py` - pip安装脚本（会缓存）
   - 这些文件会被复用，无需每次下载

### 测试建议

1. **本地测试**：
   ```bash
   # 测试Full版本
   cd dist\YaoScope-Full
   YaoScope.exe
   
   # 测试Lite版本
   cd dist\YaoScope-Lite
   YaoScope.exe
   ```

2. **干净环境测试**：
   - 在没有安装Python的机器上测试
   - 在不同Windows版本上测试（Win10/Win11）
   - 测试防火墙授权流程

3. **功能验证**：
   - 访问 http://127.0.0.1:8765/docs
   - 测试几个API接口
   - 检查日志输出是否正常

## 🔄 更新和重新构建

### 代码更新后重新构建

```bash
cd YaoScope

# 1. 更新代码
git pull  # 或其他方式更新代码

# 2. 更新虚拟环境依赖（如果requirements.txt变化）
call venv\Scripts\activate.bat
pip install -r requirements.txt

# 3. 清理旧的构建（可选）
rmdir /s /q dist

# 4. 重新构建
build_dist.bat
```

### 仅重新编译启动器

如果只修改了启动器代码：

```bash
cd YaoScope\launcher
cargo build --release

# 复制到分发包
copy /Y target\release\YaoScope.exe ..\dist\YaoScope-Full\YaoScope.exe
copy /Y target\release\YaoScope.exe ..\dist\YaoScope-Lite\YaoScope.exe
```

### 清理缓存

如果需要完全重新构建：

```bash
cd YaoScope

# 清理分发包
rmdir /s /q dist

# 清理Rust编译缓存
cd launcher
cargo clean
cd ..

# 清理Python缓存（可选，会重新下载）
del distribution\python-3.11.9-embed-amd64.zip
del distribution\get-pip.py

# 重新构建
build_dist.bat
```

## 📞 技术支持

如果遇到问题：

1. 查看 `build/` 目录下的日志文件
2. 检查 PyInstaller 的警告信息
3. 确保使用最新版本的 PyInstaller：`pip install --upgrade pyinstaller`

---

**最后更新**: 2025-11-27



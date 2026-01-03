# YaoScope 快速构建指南

## 🚀 一键生成分发包

### 完整命令（复制粘贴即可）

```bash
# 1. 进入项目目录
cd E:\work\RustWorks\yao\YaoScope

# 2. 创建虚拟环境（如果不存在）
python -m venv venv

# 3. 激活虚拟环境
call venv\Scripts\activate.bat

# 4. 安装依赖
pip install -r requirements.txt

# 5. 执行构建
build_dist.bat
```

**就这么简单！** 等待10-15分钟，分发包就生成好了。

---

## 📦 构建结果

构建完成后，你会得到：

```
YaoScope/dist/
├── YaoScope-Full/     # 完整版（800MB-1.5GB）
│   └── YaoScope.exe   # 双击即可运行，无需网络
│
└── YaoScope-Lite/     # 精简版（50-100MB）
    └── YaoScope.exe   # 双击运行，首次需要网络下载依赖
```

---

## ✅ 测试分发包

```bash
# 测试Full版本
cd dist\YaoScope-Full
YaoScope.exe

# 或测试Lite版本
cd dist\YaoScope-Lite
YaoScope.exe
```

访问：http://127.0.0.1:8765/docs

---

## 📤 打包分发

```bash
# 压缩为zip
cd dist
Compress-Archive -Path YaoScope-Full -DestinationPath YaoScope-Full-v1.0.0.zip
Compress-Archive -Path YaoScope-Lite -DestinationPath YaoScope-Lite-v1.0.0.zip
```

完成！现在可以分发给用户了。

---

## ❓ 常见问题

**Q: 构建失败，提示找不到Python**
```bash
# 确保Python已安装并在PATH中
python --version
```

**Q: 构建失败，提示找不到cargo**
```bash
# 安装Rust工具链
# 访问 https://rustup.rs/ 下载安装
# 安装完成后重启终端
cargo --version
```

**Q: 想要重新构建**
```bash
# 清理旧的构建
rmdir /s /q dist

# 重新构建
build_dist.bat
```

**Q: 只想更新代码，不重新安装依赖**
```bash
# Full版本会重新安装依赖（确保完整性）
# 如果只是小改动，可以手动复制文件到 dist/YaoScope-Full/service/
```

---

## 📚 详细文档

查看完整文档：[README_BUILD.md](README_BUILD.md)

---

**最后更新**: 2025-11-27


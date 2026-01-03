# 配置文件说明

## 配置文件位置

配置文件现在位于项目根目录的 `config` 文件夹中：

```
yao/
├── config/
│   ├── settings.json          # 实际配置文件
│   └── settings.json.template # 配置模板
```

## 为什么改到这里？

之前配置文件存储在：
- Windows: `C:\Users\<用户名>\AppData\Roaming\com.yao.chat\settings.json`
- 位置太深，不方便用户查找和修改

现在改为项目根目录的 `config` 文件夹，方便：
- ✅ 快速访问和编辑配置
- ✅ 与项目代码一起管理
- ✅ Git 版本控制
- ✅ 团队协作时共享配置

## 配置文件结构

```json
{
  "provider": "openai",              // LLM提供商
  "baseUrl": "https://...",          // API地址
  "apiKey": "your-api-key",          // API密钥
  "model": "model-name",             // 默认模型
  "models": [...],                   // 可用模型列表
  "vlModel": "vl-model-name",        // 视觉语言模型
  "advancedModel": "advanced-model", // 高级模型
  "lightModel": "light-model",       // 轻量模型
  "embedding_url": "https://...",    // Embedding服务地址
  "temperature": 0.7,                // 生成温度
  "language": "zh"                   // 界面语言
}
```

## 首次使用

1. 复制 `settings.json.template` 为 `settings.json`
2. 编辑 `settings.json`，填入你的 API 密钥
3. 启动应用

## 迁移说明

如果你之前使用过旧版本，配置文件会在首次启动时自动从 AppData 迁移到这里。

迁移完成后，可以删除旧的配置文件：
```
C:\Users\<用户名>\AppData\Roaming\com.yao.chat\settings.json
```

## 注意事项

⚠️ **重要**: `settings.json` 包含敏感的 API 密钥
- 如果是公开仓库，请勿提交到 Git
- 建议始终只提交 `settings.json.template`，本地复制一份 `settings.json` 自用（已在 `.gitignore` 中忽略）


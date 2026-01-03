# Contributing
#
# 贡献指南

Thanks for contributing to Yao!

欢迎贡献 Yao！

## Development setup / 开发环境

1. Install dependencies: Python 3.10+, Node.js 18+, Rust toolchain
2. Create local config (do not commit):
   - Copy `config/settings.json.template` to `config/settings.json`
3. Start dev:

```bat
start.bat
```

`start.bat` should print `=== START SUCCESS ===`.

## Rules / 规则

- Do not commit secrets (API keys, tokens) or personal data (logs, conversations, screenshots).
- Do not commit large model files (`*.gguf`).
- Keep changes clean and minimal. Prefer small PRs.

## Pull Requests / 提交 PR

- Describe what/why clearly.
- Include reproduction steps if you fixed a bug.
- Ensure `start.bat` succeeds locally.



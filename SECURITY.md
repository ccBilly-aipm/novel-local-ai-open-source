# Security Policy

## Supported version

当前仅维护最新的 `main` 和最新发布标签。`v1.0.0` 是首个开源基线。

## Reporting a vulnerability

请使用 GitHub Private Vulnerability Reporting（仓库 Security 页面）报告安全问题。不要在公开 Issue 中提交：

- API Key、访问令牌或其他凭据；
- 用户小说正文、角色资料或数据库；
- 包含本机用户名、绝对路径或服务配置的日志；
- 可直接利用的漏洞细节。

报告应包括受影响版本、复现步骤、影响范围和建议修复。维护者会先确认问题，再决定修复和披露时间。

## Current security boundaries

- 应用默认只监听本机回环地址，不应直接暴露到公网。
- API Key 当前存储在本地 SQLite，尚未接入 macOS Keychain。
- FastAPI API 当前没有商业级认证与多用户隔离。
- Prompt、模型原始输出和小说内容可能出现在本地日志/数据库中。
- 自动模式的权限仅限当前小说项目内的生成、修订、提交和记忆更新，不应拥有系统级权限。

在加入认证、密钥存储和日志脱敏之前，不要把该服务部署为公共互联网服务。

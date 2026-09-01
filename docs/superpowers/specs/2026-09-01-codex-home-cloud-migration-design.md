# Codex Home 与 Cloud 环境迁移设计

## 目标

将 Codex 的持久状态目录从含中文用户名的默认路径
`C:\Users\愚者\.codex` 迁移到纯 ASCII 路径
`D:\CodexData\codex-home`，消除浏览器可信服务路径校验失败，并在恢复浏览器控制后为
`lc931223-lc/a-share-daily-review` 创建 Codex Cloud 环境。

## 已确认根因

- 当前用户级和机器级 `CODEX_HOME` 均未设置。
- Codex 因此在每次启动时使用默认目录 `C:\Users\愚者\.codex`。
- 启动过程会重新生成 `config.toml` 中的 Node REPL 与浏览器服务配置，覆盖手工修改。
- 浏览器服务路径包含中文用户名后，可信 RPC 路径规范化校验失败。
- 官方文档确认 `CODEX_HOME` 是 Codex 状态根目录的稳定公开配置，目录必须预先存在。

## 选定方案

采用完整迁移方案，不使用目录联接或启动后配置修补：

1. 创建 `D:\CodexData\codex-home`。
2. 在 Codex 完全退出后，将 `C:\Users\愚者\.codex` 完整复制到新目录。
3. 复制成功并通过关键文件校验后，设置用户级环境变量：
   `CODEX_HOME=D:\CodexData\codex-home`。
4. 保留旧目录原样，不删除、不移动，作为即时回滚副本。
5. 重新启动 Codex，让应用从新目录生成运行配置。

## 执行模型

迁移由一次性 PowerShell 脚本执行。脚本必须：

- 使用固定、经验证的绝对源路径和目标路径。
- 在复制前确认目标位于 `D:\CodexData` 下。
- 等待 Codex/ChatGPT 桌面进程退出后才开始最终复制。
- 使用可重试、保留时间戳和目录结构的复制工具。
- 不删除源目录。
- 只有在复制退出码和关键文件校验均成功后才设置 `CODEX_HOME`。
- 写入独立迁移日志，且不得记录认证令牌或文件内容。
- 返回明确的成功或失败状态。

## 数据范围

迁移整个 `.codex` 状态根目录，包括：

- `config.toml`
- 登录与认证状态文件
- sessions、history 和 SQLite 状态
- skills、plugins 和 automations
- logs 与其他 Codex 持久元数据

不改变项目仓库、GitHub 仓库、Windows 用户目录或 `D:\CodexData\.codex-live`。

## 安全与回滚

- 旧目录 `C:\Users\愚者\.codex` 保持不变。
- 迁移失败时不设置 `CODEX_HOME`，下次启动继续使用旧目录。
- 迁移成功后如出现异常，清除用户级 `CODEX_HOME` 并重新启动 Codex，即可恢复旧目录。
- 不读取、复制到日志或输出任何访问令牌的内容。
- 不清理旧目录，除非用户日后单独确认。

## 验证标准

重启后必须逐项确认：

1. 进程环境或新配置显示 `CODEX_HOME=D:\CodexData\codex-home`。
2. 当前任务、项目列表和登录状态仍可访问。
3. 浏览器可信服务路径位于纯 ASCII 的新目录或受信任插件目录。
4. 内置浏览器连接成功，不再出现 `Trusted RPC dependency` 错误。
5. GitHub 授权后可以选择 `lc931223-lc` 和仓库 `a-share-daily-review`。

## Cloud 环境配置

浏览器恢复后创建 Cloud Environment：

- GitHub 主体：`lc931223-lc`
- Repository：`a-share-daily-review`
- Branch：`main`
- Python：3.12（可选版本时）
- Setup script：

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

创建后启动正式 Cloud 任务，要求：

- 验证远程仓库、`main` 分支和迁移提交 `2c5918e`。
- 阅读 `README.md`、`CODEx_MEMORY.md` 和 `CHECKPOINT.md`。
- 使用缓存数据运行 `tools/review_sentiment_20260824_20260828.py`。
- 验证思源黑体 PDF 生成。
- 不读取、输出或提交 Token。

## 完成条件

同时满足以下条件才视为完成：

- Codex 稳定使用新的 ASCII `CODEX_HOME`。
- 原状态与任务可访问，旧目录仍保留。
- 浏览器自动化恢复。
- Cloud Environment 已创建并绑定目标仓库的 `main` 分支。
- 正式 Cloud 任务已创建并返回可打开的任务 ID。

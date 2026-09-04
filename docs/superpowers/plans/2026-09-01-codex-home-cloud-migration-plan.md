# Codex Home 与 Cloud 环境迁移实施计划

## 阶段一：迁移准备

1. 确认源目录 `C:\Users\愚者\.codex` 存在且包含 `config.toml`。
2. 确认目标目录固定为 `D:\CodexData\codex-home`，且位于允许的父目录下。
3. 记录当前 Codex 应用可执行文件路径。
4. 执行迁移脚本预检，不修改文件或环境变量。

## 阶段二：退出后迁移

1. 以隐藏、独立 PowerShell 进程启动迁移脚本。
2. 用户完全退出 Codex。
3. 脚本等待所有 `ChatGPT.exe` 和 `codex.exe` 进程结束。
4. 使用 `robocopy` 复制完整状态目录，保留时间戳、目录结构以及目录联接本身，但不展开联接目标。
5. 检查复制退出码、关键文件和文件数量。
6. 仅在校验通过后设置用户级 `CODEX_HOME`。
7. 在新环境变量下重新启动 Codex。

## 阶段三：迁移验证

1. 检查用户级和当前进程的 `CODEX_HOME`。
2. 检查新目录中的 `config.toml`、sessions、skills 和 plugins。
3. 确认任务列表和登录状态可用。
4. 重置并连接内置浏览器，确认可信 RPC 路径错误消失。

## 阶段四：Cloud 配置

1. 打开 Cloud Environment 创建页。
2. 选择 GitHub 主体 `lc931223-lc`。
3. 选择仓库 `a-share-daily-review` 和分支 `main`。
4. 配置 Python 依赖安装脚本。
5. 创建环境并启动正式 Cloud 任务。
6. 验证 Cloud 任务检出的远程、分支和提交。

## 回滚

如迁移后 Codex 状态异常，运行迁移脚本的 `-Rollback` 模式清除用户级
`CODEX_HOME`，完全退出并重新启动 Codex。旧目录在整个过程中保持不变。

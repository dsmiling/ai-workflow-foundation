# Cursor CLI API Key 认证 + Wayland 接入指南

> 适用：Windows 10/11，Wayland 通过 ACP 连接 Cursor Agent CLI  
> 参考环境：Cursor Agent `2026.06.12-01-15-52-7244546`，Wayland v0.9.6-rc.2.1  
> 官方文档：[Cursor CLI Authentication](https://cursor.com/docs/cli/reference/authentication)

---

## 1. 先回答：Wayland 里能切换 Composer / Fable 等模型，是因为 API 认证吗？

**不完全是。** 能切换模型的根本原因是：

1. **Cursor CLI 已成功认证**（API Key **或** 浏览器 `agent login` 均可）
2. **你的 Cursor 账号订阅/权益**允许使用这些模型（例如 Ultra 计划）
3. **Wayland 通过 ACP 协议**连上 `agent acp` 后，会向后端查询「当前账号可用模型列表」，并在 UI 里提供切换

也就是说：

| 认证方式 | 能否在 Wayland 里切模型 |
|----------|-------------------------|
| `CURSOR_API_KEY` 环境变量 | ✅ 可以（推荐无头/多机复用） |
| `agent login` 浏览器登录（凭证存本地） | ✅ 可以 |
| 未认证 | ❌ 不行，常见 `No models available` / 会话启动失败 |

**API Key 并不是「唯一能切模型」的方式**，它只是更适合：

- 不想每次浏览器登录
- Wayland 从桌面快捷方式启动、环境变量需要显式配置
- 另一台电脑快速复用同一套认证

Wayland 显示的模型名（如 Composer、Fable 等）来自 **Cursor 服务端按账号下发的模型目录**；终端里 `agent models` 列的是 model id（如 `composer-2.5`、`composer-2.5-fast`），UI 可能用更友好的显示名。

---

## 2. 在新电脑上：完整配置流程（推荐顺序）

### 步骤 A — 安装 Cursor Agent CLI

PowerShell（管理员不必）：

```powershell
irm 'https://cursor.com/install?win32=true' | iex
```

验证：

```powershell
where.exe agent
agent --version
```

安装目录通常在：

```text
%LOCALAPPDATA%\cursor-agent\
```

> **已知问题（2026.06 版本目录名）：** 若 `agent` 报找不到版本目录，检查 `cursor-agent.ps1` / `agent.ps1` 里版本正则是否匹配 `2026.06.12-01-15-52-7244546` 这种带时间段的格式。

---

### 步骤 B — 生成 User API Key

1. 打开 Cursor 控制台：[https://cursor.com/dashboard](https://cursor.com/dashboard)（或 Settings → Integrations → **User API Keys**）
2. 创建 **User API Key**（不是 Admin API Key，也不是仅用于 REST 的其他类型 key）
3. **立即复制保存**（通常只显示一次）

官方说明：[Authentication - API key](https://cursor.com/docs/cli/reference/authentication)

---

### 步骤 C — 配置 API Key（推荐：用户级环境变量）

**方式 1：系统环境变量（推荐，Wayland 也能继承）**

安全脚本（交互输入，不回显、不写进脚本文件）：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:APPDATA\Wayland\set-cursor-api-key.ps1"
```

或项目内：`scripts\set-cursor-api-key.ps1`

手动设置（Key 会进入命令历史，不推荐）：

```powershell
[Environment]::SetEnvironmentVariable('CURSOR_API_KEY', 'YOUR_KEY', 'User')
```

设置后 **完全退出并重启**：

- 所有已打开的终端
- Wayland（若要用 Wayland 连接）

**方式 2：仅当前终端临时使用**

```powershell
$env:CURSOR_API_KEY = 'YOUR_KEY'
```

**方式 3：命令行参数（适合脚本，不适合 Wayland 长期配置）**

```powershell
agent --api-key YOUR_KEY "hello"
```

---

### 步骤 D — 验证认证与模型列表

新开一个 PowerShell（确保已加载用户环境变量）：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:CURSOR_API_KEY = [Environment]::GetEnvironmentVariable('CURSOR_API_KEY','User')

agent status
agent about
agent models
```

期望结果示例：

```text
agent status
✓ Logged in as your@email.com

agent about
Subscription Tier   Ultra
User Email          your@email.com
Model               Composer 2.5

agent models
composer-2.5 - Composer 2.5
composer-2.5-fast - Composer 2.5 Fast
...
```

说明：

- 用 API Key 时，`agent status` 有时曾显示 `Not logged in`，但 `agent about` / `agent models` 正常即可继续
- 若 `agent models` 为空或报错，优先查 **key 类型、网络、CLI 版本**

---

### 步骤 E — 配置 Wayland 连接 Cursor CLI（Windows 必做）

Wayland 默认 `cliPath: "agent"` 在 Windows 上常会 `ENOENT` / `EINVAL`。

**必须把 cliPath 改成 PowerShell 包装：**

```text
"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File C:\Users\<用户名>\AppData\Local\cursor-agent\cursor-agent.ps1
```

一键修复脚本（**修改前务必完全退出 Wayland**）：

```powershell
node "$env:APPDATA\Wayland\fix-wayland-cursor-cliPath.js"
```

更详细的 spawn 问题说明见：[wayland-cursor-agent-fix.md](./wayland-cursor-agent-fix.md)

---

### 步骤 F — 在 Wayland 里使用

1. 确认步骤 C 的 `CURSOR_API_KEY` 已写入 **用户环境变量**（Wayland 从桌面启动时能读到）
2. 完全退出并重启 Wayland
3. 新建 **Cursor Agent** ACP 会话（不是 Wayland Core）
4. 在会话设置/模型选择里切换 Composer 等（以你账号实际 entitlement 为准）
5. 日志应出现 `cursor process spawned`，且无 `ENOENT` / `EINVAL`

调试日志路径：

```text
%APPDATA%\Wayland\logs\
%APPDATA%\Wayland\bun-tmp\cursor-agent-logs\
```

---

## 3. 两种认证方式对比

| 项目 | API Key (`CURSOR_API_KEY`) | 浏览器登录 (`agent login`) |
|------|---------------------------|---------------------------|
| 适用场景 | Wayland、CI、多机、无头环境 | 本机交互开发 |
| 凭证存储 | 环境变量 / 命令行参数 | `%USERPROFILE%\.cursor\` 本地加密存储 |
| Wayland 兼容 | ✅ 需用户级环境变量 | ✅ 若 Wayland 能读到本地凭证 |
| 模型列表 | 按账号权益下发 | 按账号权益下发 |
| 退出登录 | 删除环境变量即可 | `agent logout` |

**可以二选一，不必两个都配。**

---

## 4. 默认模型：Composer 标准版 vs Fast 版

CLI 默认模型写在 `%USERPROFILE%\.cursor\cli-config.json`。

- `fast: false` → **Composer 2.5（标准）**
- `fast: true` → **Composer 2.5 Fast**
- 也可用独立 id：`composer-2.5-fast`

---

## 5. 故障排查速查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| `The provided API key is invalid` | key 错误、网络/TLS、CLI 版本过旧 | 更新 CLI；确认是 **User API Key** |
| Wayland `spawn agent ENOENT` | cliPath 仍是 `agent` | 运行 `fix-wayland-cursor-cliPath.js` |
| Wayland `spawn EINVAL` | cliPath 指向 `.cmd` | 改用 PowerShell 调 `cursor-agent.ps1` |
| `No models available` | 未认证或订阅无权益 | 检查 `agent models`、账号计划 |

---

## 6. 新电脑最小检查清单

```powershell
agent --version
[Environment]::GetEnvironmentVariable('CURSOR_API_KEY','User')  # 应有值
agent about
agent models
node "$env:APPDATA\Wayland\fix-wayland-cursor-cliPath.js"       # 退出 Wayland 后执行
```

---

## 7. 安全提醒

- **不要把 API Key 提交到 Git、截图、聊天记录**
- 泄露后立即在 Cursor Dashboard **吊销并重建**

---

*文档来源：微信分享 `cursor-cli-api-auth-wayland.md`，已同步至本仓库 docs。*

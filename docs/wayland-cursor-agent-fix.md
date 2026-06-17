# Wayland 连接 Cursor Agent 修复指南

> 适用场景：Wayland 无法启动 Cursor Agent 后端，日志出现 `AgentSpawnError` / `ENOENT` / `EINVAL`。
>
> 测试环境：Windows 10/11，Wayland v0.9.6-rc.2.1，Cursor Agent 2026.06.04-5fd875e

---

## 1. 症状

Wayland 日志（`%APPDATA%\Wayland\logs\YYYY-MM-DD.log`）中出现：

```text
[AcpSession] Starting session with backend cursor
AgentSpawnError: Failed to spawn agent "cursor": spawn agent ENOENT
```

或（在将 `cliPath` 改为 `agent.cmd` 绝对路径后）：

```text
AgentSpawnError: Failed to spawn agent "cursor": spawn EINVAL
```

终端中 `agent` 命令本身通常可用：

```powershell
where.exe agent
# => %LOCALAPPDATA%\cursor-agent\agent.cmd

agent --version
agent status
```

---

## 2. 根因（两层问题）

### 2.1 ENOENT：Wayland 进程找不到 `agent`

- Wayland 默认用 `cliPath: "agent"` 启动 Cursor 后端。
- 从桌面快捷方式启动的 Electron 应用**不一定继承**用户 PATH 中的 `cursor-agent` 目录。
- 日志中 `[Wayland:env] PATH` 通常**不包含** `%LOCALAPPDATA%\cursor-agent`。

### 2.2 EINVAL：`.cmd` 无法被直接 spawn

- Wayland 使用 Node.js `child_process.spawn()`，且 **`shell: false`**。
- Windows 上不能直接 spawn `agent.cmd`，会报 `EINVAL`。
- 必须改为 spawn 真正的可执行文件（如 `powershell.exe` 或 `node.exe`）。

---

## 3. 修复前检查

```powershell
# 1. 确认 Cursor Agent 已安装
where.exe agent
agent --version
agent status

# 2. 确认 cursor-agent.ps1 存在
Test-Path "$env:LOCALAPPDATA\cursor-agent\cursor-agent.ps1"

# 3. 查看当前 Cursor 会话的 cliPath
sqlite3 "$env:APPDATA\Wayland\wayland\wayland.db" `
  "SELECT id, name, json_extract(extra,'$.cliPath') FROM conversations WHERE type='acp' AND json_extract(extra,'$.backend')='cursor';"

# 4. 查看全局 ACP 配置
node -e "const fs=require('fs');const p=process.env.APPDATA+'/Wayland/config/wayland-config.txt';const d=JSON.parse(decodeURIComponent(Buffer.from(fs.readFileSync(p,'utf8').trim(),'base64').toString('utf8')));console.log(JSON.stringify(d['acp.config'],null,2));"
```

---

## 4. 推荐修复方案

将 `cliPath` 改为通过 **PowerShell** 调用 `cursor-agent.ps1`。该脚本会自动解析最新版本，比写死 `versions\xxx\node.exe` 更耐用。

### 4.1 目标 cliPath 值

将下面路径中的用户名替换为目标机器的实际用户目录（或使用 `$env:LOCALAPPDATA` 动态生成）：

```text
"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File C:\Users\<用户名>\AppData\Local\cursor-agent\cursor-agent.ps1
```

PowerShell 一行生成（推荐在其他环境使用）：

```powershell
$ps1 = "$env:LOCALAPPDATA\cursor-agent\cursor-agent.ps1"
$cliPath = "`"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`" -NoProfile -ExecutionPolicy Bypass -File $ps1"
Write-Host $cliPath
```

Wayland 会自动追加 `acp` 参数（等价于命令行执行 `agent acp`）。

---

## 5. 一键修复脚本

**操作前必须完全退出 Wayland**（否则数据库/配置文件可能被锁定或覆盖）。

将以下内容保存为 `fix-wayland-cursor.js`，然后执行 `node fix-wayland-cursor.js`：

```javascript
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ps1 = path.join(process.env.LOCALAPPDATA, 'cursor-agent', 'cursor-agent.ps1');
if (!fs.existsSync(ps1)) {
  console.error('未找到 cursor-agent.ps1:', ps1);
  process.exit(1);
}

const CLI_PATH =
  `"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File ${ps1.replace(/\\/g, '\\\\')}`;

const configPath = path.join(process.env.APPDATA, 'Wayland', 'config', 'wayland-config.txt');
const dbPath = path.join(process.env.APPDATA, 'Wayland', 'wayland', 'wayland.db');

function backup(filePath) {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const backupPath = `${filePath}.bak-cursor-fix-${stamp}`;
  fs.copyFileSync(filePath, backupPath);
  return backupPath;
}

function readConfig(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8').trim();
  return JSON.parse(decodeURIComponent(Buffer.from(raw, 'base64').toString('utf8')));
}

function writeConfig(filePath, data) {
  const encoded = Buffer.from(encodeURIComponent(JSON.stringify(data)), 'utf8').toString('base64');
  fs.writeFileSync(filePath, encoded, 'utf8');
}

// A) 全局配置 wayland-config.txt
const configBackup = backup(configPath);
const config = readConfig(configPath);
config['acp.config'] = config['acp.config'] || {};
config['acp.config'].cursor = config['acp.config'].cursor || {};
config['acp.config'].cursor.cliPath = CLI_PATH;
writeConfig(configPath, config);
console.log('[OK] wayland-config.txt 已更新，备份:', configBackup);

// B) 已有 Cursor 会话的数据库记录
const dbBackup = backup(dbPath);
const escaped = CLI_PATH.replace(/'/g, "''");
const sql = `UPDATE conversations SET extra = json_set(extra, '$.cliPath', '${escaped}'), updated_at = CAST(strftime('%s','now') AS INTEGER) * 1000 WHERE type='acp' AND json_extract(extra,'$.backend')='cursor'; SELECT changes();`;
const changes = execFileSync('sqlite3', [dbPath, sql], { encoding: 'utf8' }).trim();
console.log('[OK] conversations 更新行数:', changes, '，备份:', dbBackup);
console.log('[INFO] cliPath =', CLI_PATH);
```

依赖：`node`（系统已装）、`sqlite3`（可用 `winget install SQLite.SQLite` 或从 sqlite.org 安装）。

---

## 6. 手动修复（不用脚本时）

### 6.1 更新全局配置

文件路径：

```text
%APPDATA%\Wayland\config\wayland-config.txt
```

该文件为 **Base64 编码的 URL 编码 JSON**。解码后找到/创建：

```json
{
  "acp.config": {
    "cursor": {
      "cliPath": "\"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe\" -NoProfile -ExecutionPolicy Bypass -File C:\\Users\\<用户名>\\AppData\\Local\\cursor-agent\\cursor-agent.ps1"
    }
  }
}
```

修改后重新 Base64 编码写回（建议用脚本，避免手工编码出错）。

### 6.2 更新已有会话（SQLite）

```powershell
# 先备份
$db = "$env:APPDATA\Wayland\wayland\wayland.db"
Copy-Item $db "$db.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"

# 生成 cliPath
$ps1 = "$env:LOCALAPPDATA\cursor-agent\cursor-agent.ps1"
$cliPath = "`"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`" -NoProfile -ExecutionPolicy Bypass -File $ps1"

# 更新所有 Cursor ACP 会话
sqlite3 $db "UPDATE conversations SET extra = json_set(extra, '`$.cliPath', '$($cliPath -replace "'","''")'), updated_at = CAST(strftime('%s','now') AS INTEGER) * 1000 WHERE type='acp' AND json_extract(extra,'$.backend')='cursor'; SELECT changes();"
```

---

## 7. 验证

### 7.1 验证 spawn 方式（可选）

```powershell
node -e "const {spawn}=require('child_process'); const p=spawn('C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',process.env.LOCALAPPDATA+'\\cursor-agent\\cursor-agent.ps1','acp'],{stdio:'pipe'}); p.on('error',e=>console.log('FAIL',e)); setTimeout(()=>{console.log('OK pid',p.pid); p.kill();},2000);"
```

应输出 `OK pid ...`，不应出现 `EINVAL`。

### 7.2 验证配置已写入

```powershell
sqlite3 "$env:APPDATA\Wayland\wayland\wayland.db" `
  "SELECT name, json_extract(extra,'$.cliPath') FROM conversations WHERE json_extract(extra,'$.backend')='cursor';"
```

### 7.3 验证 Wayland 实机

1. 完全退出 Wayland
2. 重新启动
3. 打开 Cursor Agent 会话
4. 检查日志，应看到 `[ACP-PERF] connect: cursor process spawned`，且**不再**出现 `ENOENT` / `EINVAL`

---

## 8. 其他环境注意事项

| 项目 | 说明 |
|------|------|
| 用户名/路径 | 用 `$env:LOCALAPPDATA` 和 `$env:APPDATA` 代替硬编码用户名 |
| 加 PATH  alone | 仅加用户 PATH **不够**，Wayland 可能仍读不到；本方案不依赖 PATH |
| `agent.cmd` 绝对路径 | 会触发 `EINVAL`，不要用 |
| `node.exe` + `index.js` | 可行但版本号会变；PowerShell 包装更稳 |
| 退出 Wayland | 修改 DB/配置前必须完全退出 |
| 权限 | 用户级配置，**不需要**管理员 |
| Cursor 账号 | 修复 spawn 后若仍无法对话，单独检查 `agent models` / `agent status` |

### 备选 cliPath（写死 node.exe 版本）

若 PowerShell 方式不可用，可改用（版本号需按本机实际目录替换）：

```text
"C:\Users\<用户名>\AppData\Local\cursor-agent\versions\2026.06.04-5fd875e\node.exe" C:\Users\<用户名>\AppData\Local\cursor-agent\versions\2026.06.04-5fd875e\index.js
```

查看本机版本目录：

```powershell
Get-ChildItem "$env:LOCALAPPDATA\cursor-agent\versions" -Directory | Sort-Object Name -Descending | Select-Object -First 1
```

---

## 9. 故障排查速查

| 日志错误 | 可能原因 | 处理 |
|----------|----------|------|
| `spawn agent ENOENT` | cliPath 仍为 `agent`，且 Wayland PATH 无 cursor-agent | 执行本文修复脚本 |
| `spawn EINVAL` | cliPath 指向 `.cmd` | 改为 PowerShell 或 node.exe 方案 |
| `Session failed to start` | spawn 已成功但 ACP 握手失败 | 查 `bun-tmp\cursor-agent-logs\` 和 `agent status` |
| `No models available` | Cursor 账号/订阅问题 | 与 spawn 无关，单独登录/检查 entitlement |

关键路径：

```text
Wayland 日志     : %APPDATA%\Wayland\logs\
Wayland 配置     : %APPDATA%\Wayland\config\wayland-config.txt
Wayland 数据库   : %APPDATA%\Wayland\wayland\wayland.db
Cursor Agent     : %LOCALAPPDATA%\cursor-agent\
Agent 调试日志   : %APPDATA%\Wayland\bun-tmp\cursor-agent-logs\
```

---

## 10. 修复记录（参考）

| 步骤 | 操作 | 结果 |
|------|------|------|
| 1 | 将 DB `cliPath` 从 `agent` 改为 `agent.cmd` 绝对路径 | `ENOENT` → `EINVAL` |
| 2 | 将 cliPath 改为 PowerShell 调用 `cursor-agent.ps1` | 可正确 spawn |
| 3 | 同时写入 `acp.config.cursor.cliPath` | 新建会话也生效 |

---

*文档生成日期：2026-06-12*

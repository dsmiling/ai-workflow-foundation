# MVP 边界 v0.2

版本：v0.2  
状态：已对齐（2026-06-10）  
基于：`ai-workflow-foundation-requirements.md` v0.1

---

## 1. 成功标准（一句话）

**能显示桌面级界面，能正常调度任务，可以正确跑通一次 AI 调度任务流程。**

拆解为可验收项：

| # | 验收项 | 说明 |
|---|--------|------|
| S1 | 桌面级 UI | 三栏布局完整可用：工作流/节点、Artifact、Review/Revision；非 demo 级按钮堆砌 |
| S2 | UI 创建工作流 | 用户可在 UI 中创建/编辑工作流（节点、Skill、输入输出、审批），不必手写 JSON |
| S3 | 任务调度 | 从 UI 启动 Run，顺序执行节点，状态实时可见，失败/审核可停住 |
| S4 | 跑通完整流程 | 至少一条端到端流程：执行 → 审核 →（可选变更/重跑）→ 提交 Revision |
| S5 | Skill 编排 | 底座按节点调度 Skill 执行，Skill 为外部可挂载描述，底座不替代 Cursor Skill |
| S6 | Unity 示例 | `unity_activity_create` 工作流跑通，产出 md/json，不生成 Unity 工程代码 |

---

## 2. 已拍板决策

### 2.1 产品边界

| 决策 | 结论 |
|------|------|
| 第一版用户 | 个人/工程型用户（设计者本人） |
| 与 Cursor Skill 关系 | **编排**：底座调度 Skill 执行，Skill 保持独立可挂载 |
| Unity 示例目标 | **A**：证明底座能承载 4～5 节点真实业务流，产物 md/json 即可 |
| 工作流 authoring | **UI 必做**，文件为底层持久化格式 |
| 近两周 P0 | **Artifact 编辑** + **Unity 示例 workflow** |

### 2.2 技术边界（IN / OUT）

#### v0.2 必须做（IN）

- 桌面级 Web 面板（Tauri 原生窗启动 `serve`，浏览器手动打开仅作调试）
- UI：工作流列表、节点编辑表单、Run 控制、节点状态
- UI：Artifact 查看 + **编辑保存**
- UI：Review / Change / Revision（已有基础，需补全体验）
- Skill 编排协议：`SkillSpec` + `SkillExecutor` 适配器（第一版可先读 `SKILL.md` / skill.json 再调 LLM 或子进程）
- Unity 示例工作流：`unity_activity_create`（线性，含人工审核节点）
- Executor：`mock`（开发/验收）+ `openai`（真实 AI）+ `skill`（编排外部 Skill 描述）
- 线性工作流 only（`nodes` 数组顺序，无分支）
- JSON 持久化（YAML 后补）
- 轻量 Revision（现有实现延续）
- 文本 Artifact diff
- workflow 包导入导出（已有）

#### v0.2 明确不做（OUT）

| 项 | 原因 |
|----|------|
| 拖拽画布 | 节点列表 + 表单优先 |
| `route` 条件分支 | 用 rerun 上游节点代替 |
| `tool` / `script` 节点（通用） | 通过 `skill` 编排收口 |
| `approval: ai` | 第二版 |
| 多人协作 / 权限 / 租户 | 本地单人 |
| Unity 代码 / Prefab 自动生成 | 示例只产出文档 |
| Desktop 安装包（NSIS/MSI） | v0.2 提供 Tauri 可执行文件；安装包可选 |
| SQLite 索引 | 纯文件系统，`.aiwf/` 可见 |
| 真实 Git 后端 | 轻量 Revision 够用 |
| 图片/二进制 diff | 文本 diff only |

### 2.3 待二次确认（不阻塞 P0）

| 项 | 默认假设 |
|----|----------|
| 「桌面级」是否含原生窗口 | v0.2 = Tauri 原生窗 + 精致 Web 面板 |
| Skill 编排第一版实现 | 读取 Skill 描述文件 + LLM 执行；不接 Cursor API 直连 |
| change 是否需 confirm 步骤 | 保持 `Apply` = 确认 |
| reject 后首选路径 | 反馈 → change → apply → rerun（A 路径） |
| 全局 Skill 写回 | run 内 `workflow.lock.json` 调参；commit revision 定稿 |

---

## 3. Unity 示例工作流定义

**工作流 ID**：`unity_activity_create`

```text
raw_requirement（输入）
  → requirement_analysis（ai, auto）
  → module_mapping（ai, auto）
  → review_mapping（review, human）
  → build_plan（ai, auto）
```

**产物契约**：

| 节点 | 主产物 | 结构化产物 |
|------|--------|------------|
| requirement_analysis | requirement_analysis.md | — |
| module_mapping | module_mapping.md | module_mapping.json |
| review_mapping | —（审核卡点） | review_report.json |
| build_plan | build_plan.md | — |

**输入方式（v0.2）**：UI 表单粘贴需求文本或 Wiki 摘要，不强制接 Wiki 爬取。

**Skill 挂载**：每个 AI 节点引用 `examples/skills/` 或 `.aiwf/skills/` 下对应 SkillSpec；Skill 描述可对齐现有大活动 Skill 的 goal/quality，但 v0.2 不强制调用 Cursor Agent runtime。

---

## 4. Skill 编排协议（v0.2 最小版）

底座与 Skill 的分工：

```text
Workflow（底座）     → 决定顺序、输入绑定、审批、产物路径、Run 状态
SkillSpec（挂载）   → 决定执行意图、质量标准、输出契约
Executor（适配器）  → 把 Node + Skill + Inputs 变成 Artifact
```

节点 → Executor 映射：

| 节点 type | Executor | 行为 |
|-----------|----------|------|
| `ai` | `openai` / `mock` | LLM 按 SkillSpec 生成产物 |
| `ai` + `skill_ref` | `skill` | 加载外部 Skill 描述（SKILL.md 或 skill.json），按描述执行 |
| `review` | 内置 | 暂停，等待 UI/CLI approve 或 reject |

SkillSpec 扩展字段（v0.2 新增，向后兼容）：

```json
{
  "id": "module_mapping",
  "ref": "optional/path/to/SKILL.md",
  "executor": "skill"
}
```

`ref` 缺省时，行为与现有 `skill.json` 一致。

---

## 5. UI 必做范围

相对当前 `web/index.html` 的增量：

| 能力 | 现状 | v0.2 目标 |
|------|------|-----------|
| 工作流选择 | 手填文件路径 | 工作流列表 + 新建/编辑 |
| 节点配置 | 无 | 节点表单：id、type、skill、inputs、outputs、approval |
| Skill 预览 | 无 | 选中节点显示 SkillSpec |
| Run 控制 | 有 | 保留并优化状态展示 |
| Artifact | 只读 | **可编辑 + 保存** |
| Review/Change/Revision | 有 | 保留，补 rollback 按钮 |

「桌面级」最低体验标准：

- 固定三栏，不依赖横向滚动
- 节点状态色块 + 当前节点高亮
- Artifact 区支持 Markdown 编辑（textarea 或简易编辑器）
- 操作有明确成功/失败反馈
- 无需打开 `.aiwf/` 目录即可完成一次完整流程

---

## 6. 与当前实现的差距

| 差距 | 优先级 | 说明 |
|------|--------|------|
| Artifact 编辑 API + UI | **P0** | `GET` 已有，`PUT` 缺失 |
| Unity 示例 workflow + skills | **P0** | 新建 json 定义 |
| UI 工作流创建/编辑 | **P0**（UI 必做） | 需 workflow CRUD API + 表单 |
| Skill Executor 适配器 | **P1** | 编排外部 Skill 描述 |
| 工作流列表 API | **P1** | 扫描 `.aiwf/workflows` + examples |
| 节点详情 + Skill 预览 | **P1** | 读 workflow.lock + skill 文件 |
| 桌面原生壳（Tauri） | **已完成** | `.\Launch-AIWF.ps1` |

---

## 7. 实施顺序（建议）

### 阶段 A — P0（近两周）

1. `PUT /runs/{id}/artifact` — 保存编辑后的产物
2. Web：Artifact 编辑模式 + Save
3. `unity_activity_create` workflow + 4 个 skill json
4. `doctor` 增加 unity 流程验收（mock executor）

### 阶段 B — UI 必做（紧随 P0）

5. Workflow CRUD API（创建/读取/更新 `.aiwf/workflows/*.json`）
6. Web：工作流编辑器（节点列表 + 添加/删除/排序 + 表单）
7. Web：从列表选工作流 → Run

### 阶段 C — Skill 编排

8. `SkillExecutor`：加载 `ref` 指向的 Skill 描述
9. 节点级 `executor` 字段或 skill 级 `executor: skill`
10. Unity 流改用 `skill` executor（仍可用 mock/openai 兜底）

### 阶段 D — 体验收尾

11. Revision rollback 按钮、diff 可读性
12. 验收清单自动化（`doctor` 覆盖 S1–S6）

---

## 8. 验收清单（v0.2 Done Definition）

在 mock executor 下，通过 UI 完成：

- [x] 创建或编辑 `unity_activity_create` 工作流
- [x] 输入需求文本，点击 Run
- [x] 查看各节点产物（md/json）
- [x] 在 UI 中编辑某 Artifact 并保存
- [x] 在 review 节点 Reject → 生成 Change → Apply + Rerun
- [x] 或 Approve → 继续执行至完成
- [x] Commit Revision
- [x] 查看 Revision diff
- [x] `py -B aiwf_cli.py doctor` 返回 `{"ok": true}`

---

## 9. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-10 | 初版：基于需求对齐 grill 5 项拍板 |
| 2026-06-10 | v0.2 完成：Workflow CRUD、Skill Executor、Web 编辑器 |

"""One-shot generator: split web/index.html into CSS + ES module files."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
EXTRACT_CSS = ROOT / "_extract_css.txt"
EXTRACT_JS = ROOT / "_extract_js.txt"

WORKFLOW_VARS = [
    "currentState",
    "runPollTimer",
    "runClockTimer",
    "currentArtifactRef",
    "workflowCatalog",
    "editingWorkflow",
    "selectedNodeIndex",
    "nodeEditOpen",
    "workflowEditOpen",
    "currentWorkflowPath",
    "currentWorkflowEditable",
    "suppressNodeForm",
]
SETTINGS_VARS = [
    "skillCatalog",
    "skillAssistantSource",
    "selectedSkillId",
    "selectedSkillEditable",
    "selectedSkillCloneFrom",
    "skillEditorIsNew",
    "waylandSkillCatalog",
    "marketSkillCatalog",
]

TRANSITIONS = {
    "nodeRole",
    "nodeRoleLabel",
    "normalizeNodeType",
    "resolveExecutorLabel",
    "formatDuration",
    "parseTimestamp",
    "nodePhaseLabel",
    "expectedOutputLabel",
    "workflowDisplayOrder",
    "resolveNodeDisplayStatus",
    "nodeDurationMs",
    "runDurationMs",
    "outgoingTransitions",
    "branchTagsHtml",
    "transitionEdgeHtml",
    "buildStateMachineNodeHtml",
    "buildNodeCardHtml",
}
CATALOG = {
    "renderWorkflowCards",
    "updateWorkflowCounts",
    "refreshWorkflowCatalog",
    "populateWorkflowForm",
    "syncWorkflowFormToWorkflow",
    "loadWorkflowData",
    "selectWorkflow",
    "openWorkflowEditor",
    "openWorkflowNodes",
    "renderWorkflowInspector",
    "loadWorkflowForEdit",
    "saveWorkflow",
    "blankWorkflow",
    "defaultNode",
    "syncLinearTransitions",
}
INSPECTOR = {"setWorkflowView", "renderNodeInspector"}
EDITOR = {
    "renderRunLiveBanner",
    "shouldPollRunState",
    "stopRunTimers",
    "startRunTimers",
    "renderEditorNodes",
    "selectNode",
    "openNodeEditor",
}
NODE_FORM = {
    "applyNodeFormVisibility",
    "currentNode",
    "renderNodeForm",
    "syncNodeFormToWorkflow",
    "refreshSkillPreview",
    "addOption",
}
RUN = {
    "setState",
    "renderRunNodes",
    "refreshArtifactOptions",
    "loadState",
    "refreshChanges",
    "refreshRevisions",
    "openArtifact",
}
SKILLS = {
    "refreshSkillCatalog",
    "resetSkillEditor",
    "setSkillSourceTab",
    "blankSkill",
    "ensureSkillApi",
    "refreshSkillAssistant",
    "renderSkillAssistantList",
    "loadSkillEditor",
    "fillSkillEditor",
    "loadWaylandSkillPreview",
    "loadMarketSkillPreview",
    "collectSkillEditorPayload",
}
GENERAL = {"setSettingsView"}


def css_bucket(block: str) -> str:
    b = block.strip()
    if b.startswith(":root"):
        return "tokens"
    if b.startswith("@media"):
        return "layout"
    if any(
        b.startswith(p)
        for p in (
            "header",
            "main ",
            "main{",
            "nav ",
            "nav{",
            ".tab",
            ".page",
            ".settings-layout",
        )
    ):
        return "layout"
    if any(
        x in b
        for x in (
            ".settings-",
            ".skill-",
            ".market-card",
            ".wayland-card",
        )
    ):
        return "settings"
    if any(
        x in b
        for x in (
            ".workflow-",
            ".context-",
            ".stage",
            ".inspector",
            ".workflow-view",
            ".workflow-grid",
            ".workflow-card",
            ".node-canvas",
            ".node-role-",
            ".run-grid",
            ".run-panel",
            ".run-live",
            ".sm-",
            ".state-machine",
            ".editor-node-list",
            ".panel-block",
        )
    ):
        return "workflow"
    return "base"


def map_state(code: str) -> str:
    for var in WORKFLOW_VARS:
        code = re.sub(rf"\b{var}\b", f"workflowState.{var}", code)
    for var in SETTINGS_VARS:
        code = re.sub(rf"\b{var}\b", f"settingsState.{var}", code)
    return code


def extract_functions(js_body: str) -> dict[str, str]:
    pattern = re.compile(r"^async function (\w+)|^function (\w+)", re.M)
    positions = [(m.start(), m.group(1) or m.group(2)) for m in pattern.finditer(js_body)]
    positions.append((len(js_body), None))
    functions: dict[str, str] = {}
    for index, (start, name) in enumerate(positions[:-1]):
        end = positions[index + 1][0]
        if name:
            functions[name] = js_body[start:end].rstrip()
    return functions


def fn_module(name: str) -> str:
    if name in TRANSITIONS:
        return "transitions"
    if name in CATALOG:
        return "catalog"
    if name in INSPECTOR:
        return "inspector"
    if name in EDITOR:
        return "editor"
    if name in NODE_FORM:
        return "node-form"
    if name in RUN:
        return "run"
    if name in SKILLS:
        return "skills"
    if name in GENERAL:
        return "general"
    raise ValueError(f"Unknown function: {name}")


def make_export(body: str) -> str:
    body = map_state(body)
    if body.startswith("async function "):
        name = re.match(r"async function (\w+)", body).group(1)
        return body.replace(f"async function {name}", f"export async function {name}", 1)
    name = re.match(r"function (\w+)", body).group(1)
    return body.replace(f"function {name}", f"export function {name}", 1)


def split_css(css: str) -> None:
    blocks: list[str] = []
    current: list[str] = []
    for line in css.splitlines():
        if line.strip() == "" and current:
            blocks.append("\n".join(current))
            current = []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))

    css_files = {key: [] for key in ("tokens", "base", "layout", "workflow", "settings")}
    for block in blocks:
        css_files[css_bucket(block)].append(block)

    styles_dir = WEB / "styles"
    styles_dir.mkdir(parents=True, exist_ok=True)
    for name, parts in css_files.items():
        (styles_dir / f"{name}.css").write_text("\n\n".join(parts).strip() + "\n", encoding="utf-8")


def write_core() -> None:
    core = WEB / "js" / "core"
    core.mkdir(parents=True, exist_ok=True)
    (core / "dom.js").write_text(
        """export const $ = (id) => document.getElementById(id);

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
""",
        encoding="utf-8",
    )
    (core / "api.js").write_text(
        """export async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}
""",
        encoding="utf-8",
    )
    (core / "log.js").write_text(
        """import { $ } from "./dom.js";

export function setLog(message) {
  $("log").textContent = message;
}
""",
        encoding="utf-8",
    )


def write_state() -> None:
    wf = WEB / "js" / "workflow" / "state.js"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(
        """export const workflowState = {
  currentState: null,
  runPollTimer: null,
  runClockTimer: null,
  currentArtifactRef: null,
  workflowCatalog: [],
  editingWorkflow: { id: "", name: "", nodes: [] },
  selectedNodeIndex: 0,
  nodeEditOpen: false,
  workflowEditOpen: false,
  currentWorkflowPath: "",
  currentWorkflowEditable: false,
  suppressNodeForm: false,
};
""",
        encoding="utf-8",
    )
    st = WEB / "js" / "settings" / "state.js"
    st.parent.mkdir(parents=True, exist_ok=True)
    st.write_text(
        """export const settingsState = {
  skillCatalog: [],
  skillAssistantSource: "workspace",
  selectedSkillId: "",
  selectedSkillEditable: false,
  selectedSkillCloneFrom: "",
  skillEditorIsNew: false,
  waylandSkillCatalog: [],
  marketSkillCatalog: [],
};
""",
        encoding="utf-8",
    )


MODULE_IMPORTS = {
    "transitions": [
        'import { $ } from "../core/dom.js";',
        'import { escapeHtml } from "../core/dom.js";',
        "import { workflowState } from \"./state.js\";",
    ],
    "catalog": [
        'import { $ } from "../core/dom.js";',
        'import { escapeHtml } from "../core/dom.js";',
        'import { api } from "../core/api.js";',
        'import { setLog } from "../core/log.js";',
        "import { workflowState } from \"./state.js\";",
        'import { renderWorkflowInspector } from "./inspector.js";',
        'import { renderNodeInspector } from "./inspector.js";',
        'import { setWorkflowView } from "./inspector.js";',
        'import { renderEditorNodes } from "./editor.js";',
        'import { syncNodeFormToWorkflow } from "./node-form.js";',
        'import { defaultNode, syncLinearTransitions } from "./catalog.js";',
    ],
    "inspector": [
        'import { $ } from "../core/dom.js";',
        'import { escapeHtml } from "../core/dom.js";',
        "import { workflowState } from \"./state.js\";",
        'import { renderWorkflowInspector } from "./inspector.js";',
        'import { renderNodeInspector } from "./inspector.js";',
        'import { nodeRole, nodeRoleLabel, resolveExecutorLabel } from "./transitions.js";',
    ],
    "editor": [
        'import { $ } from "../core/dom.js";',
        'import { escapeHtml } from "../core/dom.js";',
        "import { workflowState } from \"./state.js\";",
        'import { updateWorkflowCounts } from "./catalog.js";',
        'import { renderRunLiveBanner, shouldPollRunState, stopRunTimers, startRunTimers } from "./editor.js";',
        'import { renderRunNodes } from "./run.js";',
        'import { loadState } from "./run.js";',
        'import { workflowDisplayOrder, resolveNodeDisplayStatus, buildStateMachineNodeHtml, transitionEdgeHtml, nodeRole, formatDuration, runDurationMs } from "./transitions.js";',
        'import { selectNode, openNodeEditor } from "./editor.js";',
        'import { syncNodeFormToWorkflow } from "./node-form.js";',
        'import { renderNodeForm } from "./node-form.js";',
        'import { renderNodeInspector } from "./inspector.js";',
    ],
    "node-form": [
        'import { $ } from "../core/dom.js";',
        'import { api } from "../core/api.js";',
        "import { workflowState } from \"./state.js\";",
        'import { nodeRole, normalizeNodeType } from "./transitions.js";',
    ],
    "run": [
        'import { $ } from "../core/dom.js";',
        'import { escapeHtml } from "../core/dom.js";',
        'import { api } from "../core/api.js";',
        'import { setLog } from "../core/log.js";',
        "import { workflowState } from \"./state.js\";",
        'import { renderEditorNodes, renderRunLiveBanner, shouldPollRunState, stopRunTimers, startRunTimers } from "./editor.js";',
        'import { updateWorkflowCounts } from "./catalog.js";',
        'import { workflowDisplayOrder, resolveNodeDisplayStatus, buildStateMachineNodeHtml, nodeRole } from "./transitions.js";',
        'import { addOption } from "./node-form.js";',
        'import { setState } from "./run.js";',
    ],
    "skills": [
        'import { $ } from "../core/dom.js";',
        'import { escapeHtml } from "../core/dom.js";',
        'import { api } from "../core/api.js";',
        "import { settingsState } from \"./state.js\";",
        'import { addOption } from "../workflow/node-form.js";',
    ],
    "general": [
        'import { $ } from "../core/dom.js";',
        "import { refreshSkillAssistant } from \"./skills.js\";",
    ],
}


def write_js_modules(functions: dict[str, str]) -> None:
    mods: dict[str, list[str]] = {key: [] for key in MODULE_IMPORTS}
    for name, body in functions.items():
        mods[fn_module(name)].append(make_export(body))

    for mod_name, bodies in mods.items():
        if not bodies:
            continue
        path = WEB / "js" / ("workflow" if mod_name not in ("skills", "general") else "settings") / f"{mod_name}.js"
        path.parent.mkdir(parents=True, exist_ok=True)
        # dedupe imports - use fixed import blocks per module instead
        imports = {
            "transitions": [
                'import { escapeHtml } from "../core/dom.js";',
                "import { workflowState } from \"./state.js\";",
            ],
            "catalog": [
                'import { $ } from "../core/dom.js";',
                'import { escapeHtml } from "../core/dom.js";',
                'import { api } from "../core/api.js";',
                'import { setLog } from "../core/log.js";',
                "import { workflowState } from \"./state.js\";",
                'import { renderWorkflowInspector, renderNodeInspector, setWorkflowView } from "./inspector.js";',
                'import { renderEditorNodes } from "./editor.js";',
                'import { syncNodeFormToWorkflow } from "./node-form.js";',
            ],
            "inspector": [
                'import { $ } from "../core/dom.js";',
                'import { escapeHtml } from "../core/dom.js";',
                "import { workflowState } from \"./state.js\";",
                'import { nodeRole, nodeRoleLabel, resolveExecutorLabel } from "./transitions.js";',
            ],
            "editor": [
                'import { $ } from "../core/dom.js";',
                'import { escapeHtml } from "../core/dom.js";',
                "import { workflowState } from \"./state.js\";",
                'import { updateWorkflowCounts } from "./catalog.js";',
                'import { renderRunNodes, loadState } from "./run.js";',
                'import { workflowDisplayOrder, resolveNodeDisplayStatus, buildStateMachineNodeHtml, transitionEdgeHtml, nodeRole, formatDuration, runDurationMs } from "./transitions.js";',
                'import { syncNodeFormToWorkflow } from "./node-form.js";',
                'import { renderNodeForm } from "./node-form.js";',
                'import { renderNodeInspector } from "./inspector.js";',
            ],
            "node-form": [
                'import { $ } from "../core/dom.js";',
                'import { api } from "../core/api.js";',
                "import { workflowState } from \"./state.js\";",
                'import { nodeRole, normalizeNodeType } from "./transitions.js";',
            ],
            "run": [
                'import { $ } from "../core/dom.js";',
                'import { escapeHtml } from "../core/dom.js";',
                'import { api } from "../core/api.js";',
                'import { setLog } from "../core/log.js";',
                "import { workflowState } from \"./state.js\";",
                'import { renderEditorNodes, renderRunLiveBanner, shouldPollRunState, stopRunTimers, startRunTimers } from "./editor.js";',
                'import { updateWorkflowCounts } from "./catalog.js";',
                'import { workflowDisplayOrder, resolveNodeDisplayStatus, buildStateMachineNodeHtml, nodeRole } from "./transitions.js";',
                'import { addOption } from "./node-form.js";',
            ],
            "skills": [
                'import { $ } from "../core/dom.js";',
                'import { escapeHtml } from "../core/dom.js";',
                'import { api } from "../core/api.js";',
                "import { settingsState } from \"./state.js\";",
                'import { addOption } from "../workflow/node-form.js";',
            ],
            "general": [
                'import { $ } from "../core/dom.js";',
                "import { refreshSkillAssistant } from \"./skills.js\";",
            ],
        }[mod_name]
        content = "\n".join(imports) + "\n\n" + "\n\n".join(bodies) + "\n"
        path.write_text(content, encoding="utf-8")


def main() -> None:
    css = EXTRACT_CSS.read_text(encoding="utf-8")
    js = EXTRACT_JS.read_text(encoding="utf-8")
    split_css(css)
    write_core()
    write_state()
    # strip top-level lets and api/dom/setLog from js
    js_body = js
    for var in WORKFLOW_VARS + SETTINGS_VARS:
        js_body = re.sub(rf"^let {var} =.*;\n", "", js_body, flags=re.M)
    js_body = re.sub(
        r"^const \$ = \(id\) => document\.getElementById\(id\);\n",
        "",
        js_body,
        flags=re.M,
    )
    js_body = re.sub(
        r"^async function api\(path, options = \{\}\) \{.*?\n\}\n\n",
        "",
        js_body,
        flags=re.S | re.M,
    )
    js_body = re.sub(
        r"^function setLog\(message\) \{.*?\}\n\n",
        "",
        js_body,
        flags=re.M,
    )
    js_body = re.sub(
        r"^function escapeHtml\(value\) \{.*?\n\}\n\n",
        "",
        js_body,
        flags=re.S | re.M,
    )
    functions = extract_functions(js_body)
    write_js_modules(functions)
    print("Generated CSS + core + state + workflow/settings modules")
    print("Functions:", len(functions))


if __name__ == "__main__":
    main()

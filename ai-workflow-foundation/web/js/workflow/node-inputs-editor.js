import { $ } from "../core/dom.js";
import { workflowState } from "./state.js";

const SOURCE_LITERAL = "literal";
const SOURCE_ARTIFACT = "artifact";

let advancedMode = false;

function upstreamNodeIds(currentNodeId) {
  const nodes = workflowState.editingWorkflow?.nodes || [];
  const ids = [];
  for (const item of nodes) {
    if (item.id === currentNodeId) break;
    if (item.id) ids.push(item.id);
  }
  return ids;
}

export function normalizeInputBinding(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const source = String(value.source || SOURCE_LITERAL);
    if (source === SOURCE_ARTIFACT) {
      return {
        source: SOURCE_ARTIFACT,
        ref: String(value.ref || ""),
        path: value.path ? String(value.path) : "primary",
      };
    }
    return {
      source: SOURCE_LITERAL,
      value: value.value != null ? String(value.value) : "",
    };
  }
  if (typeof value === "string") {
    if (value.startsWith("artifact.")) {
      return { source: SOURCE_ARTIFACT, ref: value.slice("artifact.".length), path: "primary" };
    }
    return { source: SOURCE_LITERAL, value };
  }
  return { source: SOURCE_LITERAL, value: String(value ?? "") };
}

export function serializeInputBinding(binding) {
  if (binding.source === SOURCE_ARTIFACT) {
    const ref = binding.ref?.trim();
    if (!ref) return "";
    if (binding.path && binding.path !== "primary") {
      return { source: SOURCE_ARTIFACT, ref, path: binding.path };
    }
    return `artifact.${ref}`;
  }
  return binding.value ?? "";
}

export function bindingsFromInputs(inputs) {
  const rows = [];
  for (const [name, raw] of Object.entries(inputs || {})) {
    rows.push({ name, binding: normalizeInputBinding(raw) });
  }
  return rows;
}

export function inputsFromRows(rows) {
  const inputs = {};
  for (const row of rows) {
    const name = row.name?.trim();
    if (!name) continue;
    inputs[name] = serializeInputBinding(row.binding);
  }
  return inputs;
}

function createRowElement(row, { upstreamIds, onChange }) {
  const wrap = document.createElement("div");
  wrap.className = "input-binding-row";
  wrap.style.display = "grid";
  wrap.style.gridTemplateColumns = "1fr 120px 1.5fr auto";
  wrap.style.gap = "8px";
  wrap.style.marginBottom = "8px";
  wrap.style.alignItems = "start";

  const nameInput = document.createElement("input");
  nameInput.placeholder = "参数名";
  nameInput.value = row.name || "";
  nameInput.addEventListener("input", () => {
    row.name = nameInput.value;
    onChange();
  });

  const sourceSelect = document.createElement("select");
  for (const [value, label] of [
    [SOURCE_LITERAL, "固定文本"],
    [SOURCE_ARTIFACT, "上游产出"],
  ]) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    sourceSelect.appendChild(opt);
  }
  sourceSelect.value = row.binding.source || SOURCE_LITERAL;
  sourceSelect.addEventListener("change", () => {
    row.binding =
      sourceSelect.value === SOURCE_ARTIFACT
        ? { source: SOURCE_ARTIFACT, ref: upstreamIds[0] || "", path: "primary" }
        : { source: SOURCE_LITERAL, value: "" };
    renderValueEditor();
    onChange();
  });

  const valueHost = document.createElement("div");

  function renderValueEditor() {
    valueHost.innerHTML = "";
    if (row.binding.source === SOURCE_ARTIFACT) {
      const select = document.createElement("select");
      select.style.width = "100%";
      if (!upstreamIds.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "（无上游节点）";
        select.appendChild(opt);
      } else {
        for (const id of upstreamIds) {
          const opt = document.createElement("option");
          opt.value = id;
          opt.textContent = id;
          select.appendChild(opt);
        }
      }
      select.value = row.binding.ref || upstreamIds[0] || "";
      select.addEventListener("change", () => {
        row.binding.ref = select.value;
        onChange();
      });
      valueHost.appendChild(select);
    } else {
      const textarea = document.createElement("textarea");
      textarea.className = "code-editor";
      textarea.rows = 3;
      textarea.style.minHeight = "72px";
      textarea.placeholder = "固定文本值";
      textarea.value = row.binding.value || "";
      textarea.addEventListener("input", () => {
        row.binding.value = textarea.value;
        onChange();
      });
      valueHost.appendChild(textarea);
    }
  }

  renderValueEditor();

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.textContent = "删除";
  removeBtn.addEventListener("click", () => {
    wrap.remove();
    onChange();
  });

  wrap.appendChild(nameInput);
  wrap.appendChild(sourceSelect);
  wrap.appendChild(valueHost);
  wrap.appendChild(removeBtn);
  return wrap;
}

function renderFormEditor(container, inputs, currentNodeId, onChange) {
  const upstreamIds = upstreamNodeIds(currentNodeId);
  const rows = bindingsFromInputs(inputs);
  container.innerHTML = "";

  const header = document.createElement("div");
  header.style.display = "flex";
  header.style.justifyContent = "space-between";
  header.style.alignItems = "center";
  header.style.marginBottom = "8px";
  const title = document.createElement("strong");
  title.textContent = "输入绑定";
  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.textContent = "+ 添加参数";
  addBtn.addEventListener("click", () => {
    const list = container.querySelector(".input-binding-list");
    const row = { name: "", binding: { source: SOURCE_LITERAL, value: "" } };
    list.appendChild(createRowElement(row, { upstreamIds, onChange: syncFromDom }));
    syncFromDom();
  });
  header.appendChild(title);
  header.appendChild(addBtn);
  container.appendChild(header);

  const list = document.createElement("div");
  list.className = "input-binding-list";
  for (const row of rows) {
    list.appendChild(createRowElement(row, { upstreamIds, onChange: syncFromDom }));
  }
  container.appendChild(list);

  function syncFromDom() {
    const nextRows = [];
    list.querySelectorAll(".input-binding-row").forEach((el, index) => {
      const name = el.querySelector("input")?.value || "";
      const source = el.querySelector("select")?.value || SOURCE_LITERAL;
      let binding;
      if (source === SOURCE_ARTIFACT) {
        const refSelect = el.querySelector("div select");
        binding = { source: SOURCE_ARTIFACT, ref: refSelect?.value || "", path: "primary" };
      } else {
        const textarea = el.querySelector("textarea");
        binding = { source: SOURCE_LITERAL, value: textarea?.value || "" };
      }
      nextRows.push({ name, binding });
    });
    onChange(inputsFromRows(nextRows));
  }
}

function setAdvancedVisible(show) {
  advancedMode = show;
  const form = $("nodeInputsEditor");
  const advanced = $("nodeInputsAdvanced");
  const toggle = $("nodeInputsAdvancedToggle");
  if (form) form.hidden = show;
  if (advanced) advanced.hidden = !show;
  if (toggle) toggle.textContent = show ? "表单模式" : "高级 · JSON";
}

export function readNodeInputsFromEditor() {
  if (advancedMode) {
    try {
      return JSON.parse($("nodeInputs")?.value || "{}");
    } catch (error) {
      throw new Error(`Inputs JSON 无效: ${error.message}`);
    }
  }
  const container = $("nodeInputsEditor");
  if (!container) return {};
  const rows = [];
  container.querySelectorAll(".input-binding-row").forEach((el) => {
    const name = el.querySelector("input")?.value || "";
    const source = el.querySelector("select")?.value || SOURCE_LITERAL;
    let binding;
    if (source === SOURCE_ARTIFACT) {
      const refSelect = el.querySelector("div select");
      binding = { source: SOURCE_ARTIFACT, ref: refSelect?.value || "", path: "primary" };
    } else {
      const textarea = el.querySelector("textarea");
      binding = { source: SOURCE_LITERAL, value: textarea?.value || "" };
    }
    rows.push({ name, binding });
  });
  return inputsFromRows(rows);
}

export function fillNodeInputsEditor(inputs, currentNodeId) {
  const container = $("nodeInputsEditor");
  if (!container) return;
  if (!advancedMode) {
    renderFormEditor(container, inputs || {}, currentNodeId, (next) => {
      const ta = $("nodeInputs");
      if (ta) ta.value = JSON.stringify(next, null, 2);
    });
  }
  const ta = $("nodeInputs");
  if (ta) ta.value = JSON.stringify(inputs || {}, null, 2);
}

export function initNodeInputsEditor() {
  const toggle = $("nodeInputsAdvancedToggle");
  if (toggle && !toggle.dataset.bound) {
    toggle.dataset.bound = "1";
    toggle.addEventListener("click", () => {
      if (!advancedMode) {
        try {
          const inputs = readNodeInputsFromEditor();
          $("nodeInputs").value = JSON.stringify(inputs, null, 2);
        } catch (error) {
          setLog?.(error.message);
          return;
        }
      } else {
        try {
          const inputs = JSON.parse($("nodeInputs").value || "{}");
          fillNodeInputsEditor(inputs, currentNode()?.id);
        } catch {
          return;
        }
      }
      setAdvancedVisible(!advancedMode);
    });
  }
}

function currentNode() {
  return workflowState.editingWorkflow?.nodes?.[workflowState.selectedNodeIndex];
}

function setLog(message) {
  const el = $("log");
  if (el) el.textContent = message;
}

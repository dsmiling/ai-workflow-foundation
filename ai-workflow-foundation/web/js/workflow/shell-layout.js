const STORAGE_KEY = "aiwf.workflowShellLayout.v5";

const COLUMNS = ["context", "stage", "inspector", "assist"];

const COLUMN_MIN = {
  context: 140,
  stage: 240,
  inspector: 200,
  assist: 200,
};

const COLUMN_DEFAULT = {
  context: 220,
  stage: 420,
  inspector: 340,
  assist: 320,
};

const RESIZE_PAIRS = {
  "context-stage": { before: "context", after: "stage" },
  "stage-inspector": { before: "stage", after: "inspector" },
  "inspector-assist": { before: "inspector", after: "assist" },
};

const SHRINK_ORDER = ["stage", "inspector", "assist", "context"];

function readNumber(value, fallback) {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function readPrefs(shell) {
  const style = getComputedStyle(shell);
  return {
    context: readNumber(style.getPropertyValue("--wf-col-context"), COLUMN_DEFAULT.context),
    stage: readNumber(style.getPropertyValue("--wf-col-stage"), COLUMN_DEFAULT.stage),
    inspector: readNumber(style.getPropertyValue("--wf-col-inspector"), COLUMN_DEFAULT.inspector),
    assist: readNumber(style.getPropertyValue("--wf-col-assist"), COLUMN_DEFAULT.assist),
  };
}

function setPref(shell, column, width) {
  shell.style.setProperty(`--wf-col-${column}`, `${Math.round(width)}px`);
}

function clampPref(column, width) {
  return Math.max(COLUMN_MIN[column], width);
}

function getHandleSpace(shell) {
  const style = getComputedStyle(shell);
  const handleWidth = readNumber(style.getPropertyValue("--wf-shell-handle-width"), 10);
  const gap = readNumber(style.getPropertyValue("--wf-shell-gap"), 10);
  const count = shell.querySelectorAll(".workflow-shell-handle").length;
  return count * (handleWidth + gap);
}

function sumWidths(widths) {
  return COLUMNS.reduce((total, column) => total + widths[column], 0);
}

function applyLayoutWidths(shell, widths) {
  for (const column of COLUMNS) {
    shell.style.setProperty(`--wf-col-${column}-layout`, `${Math.round(widths[column])}px`);
  }
}

function computeLayout(prefs, available) {
  const layout = { ...prefs };
  let total = sumWidths(layout);

  if (total < available) {
    layout.stage += available - total;
    return layout;
  }

  if (total > available) {
    let deficit = total - available;
    for (const column of SHRINK_ORDER) {
      if (deficit <= 0) break;
      const shrinkable = layout[column] - COLUMN_MIN[column];
      const take = Math.min(deficit, shrinkable);
      layout[column] -= take;
      deficit -= take;
    }
  }

  return layout;
}

function reflowShell(shell, viewport) {
  if (!shell || !viewport) return;
  const available = Math.max(0, viewport.clientWidth - getHandleSpace(shell));
  const layout = computeLayout(readPrefs(shell), available);
  applyLayoutWidths(shell, layout);
}

function applyPairResize(shell, pair, delta, startPrefs) {
  const { before, after } = RESIZE_PAIRS[pair];
  let beforeWidth = startPrefs[before] + delta;
  let afterWidth = startPrefs[after] - delta;

  const beforeOverflow = beforeWidth - clampPref(before, beforeWidth);
  if (beforeOverflow < 0) {
    afterWidth -= beforeOverflow;
    beforeWidth = clampPref(before, beforeWidth);
  }

  const afterOverflow = afterWidth - clampPref(after, afterWidth);
  if (afterOverflow < 0) {
    beforeWidth -= afterOverflow;
    afterWidth = clampPref(after, afterWidth);
  }

  setPref(shell, before, clampPref(before, beforeWidth));
  setPref(shell, after, clampPref(after, afterWidth));
}

function loadSavedPrefs(shell) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    for (const column of COLUMNS) {
      const width = readNumber(saved?.[column], COLUMN_DEFAULT[column]);
      setPref(shell, column, clampPref(column, width));
    }
  } catch {
    // ignore invalid persisted layout
  }
}

function persistPrefs(shell) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(readPrefs(shell)));
}

function bindColumnResize(shell, viewport) {
  shell.querySelectorAll(".workflow-shell-handle[data-resize-pair]").forEach((handle) => {
    if (handle.dataset.resizeBound) return;
    handle.dataset.resizeBound = "1";

    const pair = handle.getAttribute("data-resize-pair");
    const pairColumns = RESIZE_PAIRS[pair];
    if (!pairColumns) return;

    let resizing = false;
    let startX = 0;
    let startPrefs = {};

    const stopResize = () => {
      if (!resizing) return;
      resizing = false;
      handle.classList.remove("is-at-limit");
      document.body.classList.remove("workflow-shell-resizing");
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
      persistPrefs(shell);
    };

    const onPointerMove = (event) => {
      if (!resizing) return;
      applyPairResize(shell, pair, event.clientX - startX, startPrefs);
      reflowShell(shell, viewport);
      const prefs = readPrefs(shell);
      const atLimit =
        prefs[pairColumns.before] <= COLUMN_MIN[pairColumns.before] + 0.5 &&
        prefs[pairColumns.after] <= COLUMN_MIN[pairColumns.after] + 0.5;
      handle.classList.toggle("is-at-limit", atLimit);
    };

    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      resizing = true;
      startX = event.clientX;
      startPrefs = readPrefs(shell);
      document.body.classList.add("workflow-shell-resizing");
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", stopResize);
      window.addEventListener("pointercancel", stopResize);
    });

    handle.addEventListener("keydown", (event) => {
      const step = event.shiftKey ? 24 : 8;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        const direction = event.key === "ArrowRight" ? 1 : -1;
        applyPairResize(shell, pair, direction * step, readPrefs(shell));
        reflowShell(shell, viewport);
        persistPrefs(shell);
      }
    });

    handle.addEventListener("dblclick", () => {
      setPref(shell, pairColumns.before, COLUMN_DEFAULT[pairColumns.before]);
      setPref(shell, pairColumns.after, COLUMN_DEFAULT[pairColumns.after]);
      reflowShell(shell, viewport);
      persistPrefs(shell);
    });
  });
}

export function initWorkflowShellLayout() {
  const shell = document.getElementById("workflowShell");
  const viewport = document.getElementById("workflowShellViewport");
  if (!shell || !viewport) return;

  for (const column of COLUMNS) {
    setPref(shell, column, COLUMN_DEFAULT[column]);
  }
  loadSavedPrefs(shell);
  bindColumnResize(shell, viewport);
  reflowShell(shell, viewport);

  const observer = new ResizeObserver(() => reflowShell(shell, viewport));
  observer.observe(viewport);
  window.addEventListener("resize", () => reflowShell(shell, viewport));
}

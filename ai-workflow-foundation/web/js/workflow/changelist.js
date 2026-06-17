import { escapeHtml } from "../core/dom.js";

const ACTION_LABELS = {
  create: "新建",
  modify: "修改",
  delete: "删除",
  rename: "重命名",
};

function actionIcon(action) {
  const labels = { create: "+", modify: "~", delete: "-", rename: ">" };
  return labels[action] || "?";
}

export function renderChangelist(container, result, { onAssetClick } = {}) {
  if (!container) return;
  if (!result) {
    container.innerHTML = '<div class="muted">尚无执行结果。运行节点测试或完整 Run 后显示变更清单。</div>';
    return;
  }

  const summary = result.summary || "（无摘要）";
  const assets = result.assets || [];
  const changes = result.changes || [];

  const parts = [`<div class="changelist-summary"><strong>摘要</strong><div>${escapeHtml(summary)}</div></div>`];

  if (changes.length) {
    parts.push('<div class="changelist-section"><strong>变更</strong><ul class="changelist-changes">');
    for (const item of changes) {
      const action = item.action || "create";
      const target = (item.target || "").replace(/^artifacts\//, "");
      parts.push(
        `<li class="changelist-change changelist-change--${escapeHtml(action)}">` +
          `<span class="changelist-action" title="${escapeHtml(ACTION_LABELS[action] || action)}">${escapeHtml(actionIcon(action))}</span>` +
          `<span class="changelist-target">${escapeHtml(target)}</span>` +
          `<span class="changelist-change-summary muted">${escapeHtml(item.summary || "")}</span>` +
          `</li>`,
      );
    }
    parts.push("</ul></div>");
  }

  if (assets.length) {
    parts.push('<div class="changelist-section"><strong>资产</strong><table class="changelist-table"><thead><tr><th>文件</th><th>类型</th><th>操作</th></tr></thead><tbody>');
    for (const asset of assets) {
      const ref = asset.ref || "";
      const shortRef = ref.replace(/^artifacts\//, "");
      const clickable = typeof onAssetClick === "function";
      parts.push(
        "<tr>" +
          `<td>${clickable ? `<button type="button" class="linkish" data-changelist-ref="${escapeHtml(ref)}">${escapeHtml(shortRef)}</button>` : escapeHtml(shortRef)}</td>` +
          `<td>${escapeHtml(asset.kind || "-")}</td>` +
          `<td>${escapeHtml(ACTION_LABELS[asset.action] || asset.action || "-")}</td>` +
          "</tr>",
      );
    }
    parts.push("</tbody></table></div>");
  }

  if (!changes.length && !assets.length) {
    parts.push('<div class="muted">结果为空。</div>');
  }

  container.innerHTML = parts.join("");
  if (typeof onAssetClick === "function") {
    container.querySelectorAll("[data-changelist-ref]").forEach((button) => {
      button.addEventListener("click", () => {
        onAssetClick(button.getAttribute("data-changelist-ref"));
      });
    });
  }
}

export async function fetchNodeResult(runId, nodeId) {
  if (!runId || !nodeId) return null;
  const { api } = await import("../core/api.js");
  try {
    const payload = await api(`/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(nodeId)}/result`);
    return payload.result || null;
  } catch {
    return null;
  }
}

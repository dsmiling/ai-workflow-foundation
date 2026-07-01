"""AIBridge CLI integration: collect Unity Editor scene/prefab context into run artifacts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

JsonDict = dict[str, Any]

DEFAULT_CLI_REL = Path(".aibridge") / "cli" / (
    "AIBridgeCLI.exe" if sys.platform == "win32" else "AIBridgeCLI"
)
UNITY_CONTEXT_DIR = "unity_context"


@dataclass(slots=True)
class UnityContextRequest:
    required: bool = False
    active_scene: bool = True
    scene_hierarchy_depth: int = 3
    include_inactive: bool = False
    prefab_paths: list[str] = field(default_factory=list)
    prefab_filter: str = ""
    prefab_max: int = 8
    include_prefab_components: bool = True

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> UnityContextRequest | None:
        if not data or not isinstance(data, dict):
            return None
        if data.get("enabled") is False:
            return None
        prefab_paths_raw = data.get("prefab_paths") or data.get("prefabs") or []
        prefab_paths = [str(item).strip() for item in prefab_paths_raw if str(item).strip()]
        depth_raw = data.get("scene_hierarchy_depth", data.get("scene_depth", 3))
        try:
            depth = int(depth_raw)
        except (TypeError, ValueError):
            depth = 3
        max_raw = data.get("prefab_max", 8)
        try:
            prefab_max = int(max_raw)
        except (TypeError, ValueError):
            prefab_max = 8
        return cls(
            required=bool(data.get("required")),
            active_scene=bool(data.get("active_scene", data.get("scene", True))),
            scene_hierarchy_depth=max(1, depth),
            include_inactive=bool(data.get("include_inactive")),
            prefab_paths=prefab_paths,
            prefab_filter=str(data.get("prefab_filter") or "").strip(),
            prefab_max=max(1, prefab_max),
            include_prefab_components=bool(data.get("include_prefab_components", True)),
        )


def resolve_unity_project_root(explicit: str | Path | None = None) -> Path | None:
    raw = str(explicit or os.environ.get("AIWF_UNITY_PROJECT_ROOT") or "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser().resolve()
    return root if root.is_dir() else None


def resolve_aibridge_cli(project_root: Path, explicit: str | Path | None = None) -> Path | None:
    raw = str(explicit or os.environ.get("AIWF_AIBRIDGE_CLI") or "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
        return candidate if candidate.is_file() else None
    bundled = (project_root / DEFAULT_CLI_REL).resolve()
    return bundled if bundled.is_file() else None


def parse_unity_context_request(node_params: JsonDict | None) -> UnityContextRequest | None:
    if not node_params:
        return None
    raw = node_params.get("unity_context")
    if isinstance(raw, dict):
        return UnityContextRequest.from_dict(raw)
    if os.environ.get("AIWF_UNITY_CONTEXT_AUTO", "").strip().lower() in {"1", "true", "yes"}:
        return UnityContextRequest()
    return None


def inspect_aibridge(project_root: Path | None = None) -> JsonDict:
    root = project_root or resolve_unity_project_root()
    if root is None:
        return {
            "configured": False,
            "ready": False,
            "detail": "未设置 AIWF_UNITY_PROJECT_ROOT。",
            "project_root": "",
            "cli_path": "",
        }
    cli = resolve_aibridge_cli(root)
    if cli is None:
        return {
            "configured": True,
            "ready": False,
            "detail": f"未找到 AIBridge CLI（期望 {root / DEFAULT_CLI_REL}）。请在 Unity 工程安装 AIBridge 包。",
            "project_root": str(root),
            "cli_path": "",
        }
    return {
        "configured": True,
        "ready": True,
        "detail": "AIBridge CLI 已就绪（需 Unity Editor 运行中才能采集场景/Prefab）。",
        "project_root": str(root),
        "cli_path": str(cli),
    }


def _run_cli(
    cli: Path,
    project_root: Path,
    args: list[str],
    *,
    timeout: int,
) -> tuple[int, str, str]:
    completed = subprocess.run(
        [str(cli), *args],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        shell=False,
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def _default_timeout() -> int:
    raw = os.environ.get("AIWF_AIBRIDGE_TIMEOUT", "120").strip()
    try:
        return max(10, int(raw))
    except ValueError:
        return 120


def _write_json(path: Path, payload: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cli_json_or_text(stdout: str, stderr: str, code: int, label: str) -> JsonDict:
    text = stdout.strip() or stderr.strip()
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                parsed.setdefault("_aibridge_exit_code", code)
                return parsed
        except json.JSONDecodeError:
            pass
    return {
        "_aibridge_exit_code": code,
        "_aibridge_label": label,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }


def collect_unity_context(
    run_dir: Path,
    request: UnityContextRequest,
    *,
    project_root: Path | None = None,
    cli_path: Path | None = None,
) -> tuple[Path, list[str], list[str]]:
    """Run AIBridge CLI and write snapshots under run_dir/unity_context/."""
    root = project_root or resolve_unity_project_root()
    if root is None:
        raise RuntimeError("AIWF_UNITY_PROJECT_ROOT is not set or does not exist.")
    cli = cli_path or resolve_aibridge_cli(root)
    if cli is None:
        raise RuntimeError(f"AIBridge CLI not found under {root / DEFAULT_CLI_REL}.")

    out_dir = run_dir / UNITY_CONTEXT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    timeout = _default_timeout()
    written: list[str] = []
    errors: list[str] = []
    manifest: JsonDict = {
        "project_root": str(root),
        "cli_path": str(cli),
        "request": {
            "active_scene": request.active_scene,
            "scene_hierarchy_depth": request.scene_hierarchy_depth,
            "prefab_paths": request.prefab_paths,
            "prefab_filter": request.prefab_filter,
        },
        "artifacts": [],
    }

    if request.active_scene:
        code, stdout, stderr = _run_cli(cli, root, ["scene", "get_active"], timeout=timeout)
        rel = f"{UNITY_CONTEXT_DIR}/active_scene.json"
        payload = _cli_json_or_text(stdout, stderr, code, "scene.get_active")
        _write_json(run_dir / rel, payload)
        written.append(rel)
        manifest["artifacts"].append({"kind": "active_scene", "path": rel, "exit_code": code})
        if code != 0:
            errors.append(f"scene get_active failed (exit {code})")

        code, stdout, stderr = _run_cli(
            cli,
            root,
            [
                "scene",
                "get_hierarchy",
                "--depth",
                str(request.scene_hierarchy_depth),
                "--includeInactive",
                "true" if request.include_inactive else "false",
            ],
            timeout=timeout,
        )
        rel = f"{UNITY_CONTEXT_DIR}/scene_hierarchy.json"
        payload = _cli_json_or_text(stdout, stderr, code, "scene.get_hierarchy")
        _write_json(run_dir / rel, payload)
        written.append(rel)
        manifest["artifacts"].append({"kind": "scene_hierarchy", "path": rel, "exit_code": code})
        if code != 0:
            errors.append(f"scene get_hierarchy failed (exit {code})")

    prefab_paths = list(request.prefab_paths)
    if request.prefab_filter and not prefab_paths:
        code, stdout, stderr = _run_cli(
            cli,
            root,
            [
                "asset",
                "find",
                "--filter",
                request.prefab_filter,
                "--format",
                "paths",
            ],
            timeout=timeout,
        )
        rel = f"{UNITY_CONTEXT_DIR}/prefab_find.txt"
        (run_dir / rel).write_text(stdout.strip() + ("\n" if stdout.strip() else ""), encoding="utf-8")
        written.append(rel)
        manifest["artifacts"].append({"kind": "prefab_find", "path": rel, "exit_code": code})
        if code != 0:
            errors.append(f"asset find failed (exit {code})")
        else:
            prefab_paths = [line.strip() for line in stdout.splitlines() if line.strip()][: request.prefab_max]

    for index, prefab_path in enumerate(prefab_paths[: request.prefab_max], start=1):
        safe_name = prefab_path.replace("/", "_").replace("\\", "_").strip("_")
        info_code, info_out, info_err = _run_cli(
            cli,
            root,
            ["prefab", "get_info", "--prefabPath", prefab_path],
            timeout=timeout,
        )
        info_rel = f"{UNITY_CONTEXT_DIR}/prefab_{index:02d}_{safe_name}_info.json"
        _write_json(run_dir / info_rel, _cli_json_or_text(info_out, info_err, info_code, "prefab.get_info"))
        written.append(info_rel)
        manifest["artifacts"].append(
            {"kind": "prefab_info", "prefab": prefab_path, "path": info_rel, "exit_code": info_code}
        )
        if info_code != 0:
            errors.append(f"prefab get_info failed for {prefab_path} (exit {info_code})")
            continue

        hier_args = ["prefab", "get_hierarchy", "--prefabPath", prefab_path]
        if request.include_prefab_components:
            hier_args.extend(["--includeComponents", "true"])
        hier_code, hier_out, hier_err = _run_cli(cli, root, hier_args, timeout=timeout)
        hier_rel = f"{UNITY_CONTEXT_DIR}/prefab_{index:02d}_{safe_name}_hierarchy.json"
        _write_json(
            run_dir / hier_rel,
            _cli_json_or_text(hier_out, hier_err, hier_code, "prefab.get_hierarchy"),
        )
        written.append(hier_rel)
        manifest["artifacts"].append(
            {"kind": "prefab_hierarchy", "prefab": prefab_path, "path": hier_rel, "exit_code": hier_code}
        )
        if hier_code != 0:
            errors.append(f"prefab get_hierarchy failed for {prefab_path} (exit {hier_code})")

    manifest["errors"] = errors
    manifest_rel = f"{UNITY_CONTEXT_DIR}/manifest.json"
    _write_json(run_dir / manifest_rel, manifest)
    written.append(manifest_rel)
    return out_dir, written, errors


def maybe_collect_unity_context(
    run_dir: Path,
    node_params: JsonDict | None,
) -> tuple[list[str], list[str]]:
    """Collect Unity context when configured; return (written_paths, errors)."""
    request = parse_unity_context_request(node_params)
    if request is None:
        return [], []
    inspection = inspect_aibridge()
    if not inspection.get("ready"):
        message = str(inspection.get("detail") or "AIBridge is not ready.")
        if request.required:
            raise RuntimeError(message)
        return [], [message]
    try:
        _, written, errors = collect_unity_context(run_dir, request)
        if errors and request.required:
            raise RuntimeError("; ".join(errors))
        return written, errors
    except Exception as exc:
        if request.required:
            raise
        return [], [str(exc)]


def unity_context_task_section(written: list[str], errors: list[str]) -> list[str]:
    lines = ["## Unity Context (AIBridge)", ""]
    if written:
        lines.append("Pre-collected Editor snapshots (read before editing artifact):")
        lines.append("")
        for rel in written:
            lines.append(f"- `{rel}`")
        lines.append("")
    if errors:
        lines.append("Collection warnings:")
        lines.append("")
        for item in errors:
            lines.append(f"- {item}")
        lines.append("")
    root = resolve_unity_project_root()
    if root:
        lines.append(f"Unity project root: `{root}`")
        lines.append(
            "For live Editor queries, AIBridge CLI is available under `.aibridge/cli/` in that project."
        )
        lines.append("")
    return lines

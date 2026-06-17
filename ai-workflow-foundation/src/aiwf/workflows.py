from __future__ import annotations

from pathlib import Path

from .storage import WorkflowStore
from .validation import validate_workflow_data, ValidationReport
from .skills import get_skill as get_skill_detail, list_skills


JsonDict = dict[str, object]


def workflow_directories(store: WorkflowStore) -> list[tuple[str, Path]]:
    return [
        ("workspace", store.aiwf / "workflows"),
        ("example", store.project_root / "examples" / "workflows"),
    ]


def list_workflows(store: WorkflowStore) -> list[JsonDict]:
    entries: dict[str, JsonDict] = {}
    for source, directory in workflow_directories(store):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            data = store.read_json(path)
            workflow_id = str(data.get("id", path.stem))
            rel_path = workflow_public_path(store, path)
            entry = {
                "id": workflow_id,
                "name": data.get("name", workflow_id),
                "path": rel_path,
                "source": source,
                "editable": source == "workspace",
            }
            if workflow_id not in entries or source == "workspace":
                entries[workflow_id] = entry
    return sorted(entries.values(), key=lambda item: (item["source"] != "workspace", str(item["id"])))


def find_workflow_path(store: WorkflowStore, workflow_id: str) -> Path:
    for directory in [store.aiwf / "workflows", store.project_root / "examples" / "workflows"]:
        if not directory.exists():
            continue
        direct = directory / f"{workflow_id}.json"
        if direct.exists():
            return direct
        for path in directory.glob("*.json"):
            data = store.read_json(path)
            if data.get("id") == workflow_id:
                return path
    raise FileNotFoundError(f"Workflow not found: {workflow_id}")


def get_workflow(store: WorkflowStore, workflow_id: str) -> JsonDict:
    path = find_workflow_path(store, workflow_id)
    data = store.read_json(path)
    source = "workspace" if store.aiwf / "workflows" in path.parents else "example"
    return {
        "workflow": data,
        "path": workflow_public_path(store, path),
        "source": source,
        "editable": source == "workspace",
    }


def save_workflow(store: WorkflowStore, workflow: JsonDict, skill_dirs: list[Path]) -> JsonDict:
    report = ValidationReport()
    validate_workflow_data(store, workflow, report, skill_dirs)
    if not report.ok:
        raise ValueError("; ".join(report.errors))
    workflow_id = str(workflow["id"])
    store.init()
    target = store.aiwf / "workflows" / f"{workflow_id}.json"
    store.write_json(target, workflow)
    return {
        "workflow": workflow,
        "path": workflow_public_path(store, target),
        "source": "workspace",
        "editable": True,
    }


def delete_workflow(store: WorkflowStore, workflow_id: str) -> None:
    target = store.aiwf / "workflows" / f"{workflow_id}.json"
    if not target.exists():
        raise FileNotFoundError(f"Workspace workflow not found: {workflow_id}")
    target.unlink()


def get_skill(
    store: WorkflowStore,
    skill_id: str,
    skill_dirs: list[Path],
    *,
    source: str | None = None,
) -> JsonDict:
    return get_skill_detail(store, skill_id, skill_dirs, source=source)


def workflow_public_path(store: WorkflowStore, path: Path) -> str:
    for base in (store.root, store.project_root):
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            continue
    return path.as_posix()


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def load_skill_ref_content(root: Path, ref: str) -> str:
    if not ref:
        return ""
    path = (root / ref).resolve()
    if root.resolve() not in path.parents and path != root.resolve():
        raise ValueError(f"Skill ref escapes workspace: {ref}")
    if not path.exists():
        raise FileNotFoundError(f"Skill ref not found: {ref}")
    return path.read_text(encoding="utf-8")

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from .storage import WorkflowStore


JsonDict = dict[str, Any]


def export_workflow_package(
    store: WorkflowStore,
    workflow_path: Path,
    package_path: Path,
    skill_dirs: list[Path] | None = None,
) -> JsonDict:
    skill_dirs = skill_dirs or [store.root / "examples" / "skills", store.aiwf / "skills"]
    workflow_data = store.read_json(workflow_path)
    workflow_id = workflow_data["id"]
    skills = collect_skill_files(store, workflow_data, skill_dirs)
    manifest = {
        "format": "aiwf-package",
        "version": 1,
        "workflow_id": workflow_id,
        "workflow_file": f"workflows/{workflow_id}.json",
        "skills": sorted(skills),
    }
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.write(workflow_path, manifest["workflow_file"])
        for skill_id, skill_path in skills.items():
            archive.write(skill_path, f"skills/{skill_id}.json")
    return manifest


def import_workflow_package(store: WorkflowStore, package_path: Path) -> JsonDict:
    store.init()
    with zipfile.ZipFile(package_path, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        if manifest.get("format") != "aiwf-package":
            raise ValueError("Not an AIWF package.")
        workflow_file = manifest.get("workflow_file")
        if not isinstance(workflow_file, str):
            raise ValueError("Package manifest is missing workflow_file.")
        workflow_target = store.aiwf / "workflows" / Path(workflow_file).name
        workflow_target.parent.mkdir(parents=True, exist_ok=True)
        workflow_target.write_bytes(archive.read(workflow_file))
        imported_skills = []
        for skill_name in archive.namelist():
            if not skill_name.startswith("skills/") or not skill_name.endswith(".json"):
                continue
            target = store.aiwf / "skills" / Path(skill_name).name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(skill_name))
            imported_skills.append(target.name)
    return {
        "workflow": str(workflow_target.relative_to(store.root)),
        "skills": sorted(imported_skills),
        "manifest": manifest,
    }


def collect_skill_files(
    store: WorkflowStore,
    workflow_data: JsonDict,
    skill_dirs: list[Path],
) -> dict[str, Path]:
    skills: dict[str, Path] = {}
    for node in workflow_data.get("nodes", []):
        if not isinstance(node, dict):
            continue
        skill_id = node.get("skill")
        if not isinstance(skill_id, str) or not skill_id:
            continue
        skill = resolve_skill_path(skill_id, skill_dirs)
        if skill is None:
            raise FileNotFoundError(f"Skill not found for export: {skill_id}")
        skills[skill_id] = skill
    return skills


def resolve_skill_path(skill_id: str, skill_dirs: list[Path]) -> Path | None:
    for directory in skill_dirs:
        candidates = [
            directory / f"{skill_id}.json",
            directory / skill_id / "skill.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
    return None


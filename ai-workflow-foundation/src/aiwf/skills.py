from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .models import SkillSpec
from .storage import WorkflowStore
from .validation import ValidationReport, validate_skill_data


JsonDict = dict[str, object]


@dataclass(slots=True)
class SkillLocation:
    skill_id: str
    json_path: Path
    source: str
    editable: bool


def skill_directories(store: WorkflowStore) -> list[tuple[str, Path]]:
    return [
        ("example", store.project_root / "examples" / "skills"),
        ("workspace", store.aiwf / "skills"),
    ]


def skill_search_dirs(store: WorkflowStore, skill_dirs: list[Path] | None = None) -> list[Path]:
    dirs: list[Path] = []
    example = store.project_root / "examples" / "skills"
    workspace = store.aiwf / "skills"
    for candidate in [example, *(skill_dirs or []), workspace]:
        resolved = candidate.resolve()
        if resolved not in {item.resolve() for item in dirs}:
            dirs.append(candidate)
    return dirs


def _skill_source(store: WorkflowStore, directory: Path) -> str:
    workspace_root = (store.aiwf / "skills").resolve()
    resolved = directory.resolve()
    if resolved == workspace_root or workspace_root in resolved.parents:
        return "workspace"
    return "example"


def find_skill_location(
    store: WorkflowStore,
    skill_id: str,
    skill_dirs: list[Path] | None = None,
    *,
    source: str | None = None,
) -> SkillLocation:
    dirs = skill_search_dirs(store, skill_dirs)
    if source:
        dirs = [directory for directory in dirs if _skill_source(store, directory) == source]
    else:
        workspace_dirs = [directory for directory in dirs if _skill_source(store, directory) == "workspace"]
        other_dirs = [directory for directory in dirs if _skill_source(store, directory) != "workspace"]
        dirs = workspace_dirs + other_dirs
    for directory in dirs:
        location_source = _skill_source(store, directory)
        for candidate in (directory / skill_id / "skill.json", directory / f"{skill_id}.json"):
            if candidate.exists():
                return SkillLocation(
                    skill_id=skill_id,
                    json_path=candidate.resolve(),
                    source=location_source,
                    editable=location_source == "workspace",
                )
    raise FileNotFoundError(f"Skill not found: {skill_id}")


def colocated_markdown_path(json_path: Path) -> Path | None:
    if json_path.name == "skill.json":
        candidate = json_path.parent / "SKILL.md"
    else:
        candidate = json_path.with_name(f"{json_path.stem}.SKILL.md")
    return candidate if candidate.exists() else None


def read_skill_markdown(json_path: Path, skill: SkillSpec, project_root: Path) -> str:
    colocated = colocated_markdown_path(json_path)
    if colocated:
        return colocated.read_text(encoding="utf-8")
    if skill.ref:
        from .workflows import load_skill_ref_content

        return load_skill_ref_content(project_root, skill.ref)
    return ""


def skill_payload_from_file(store: WorkflowStore, location: SkillLocation) -> JsonDict:
    skill = store.load_skill(location.skill_id, skill_search_dirs(store))
    markdown = read_skill_markdown(location.json_path, skill, store.project_root)
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "goal": skill.goal,
        "output": skill.output,
        "quality": skill.quality,
        "ref": skill.ref,
        "executor": skill.executor,
    }


def list_skills(store: WorkflowStore, skill_dirs: list[Path] | None = None) -> list[JsonDict]:
    entries: dict[tuple[str, str], JsonDict] = {}
    dirs = skill_search_dirs(store, skill_dirs)
    for directory in dirs:
        if not directory.exists():
            continue
        source = _skill_source(store, directory)
        for path in sorted(directory.glob("*.json")):
            data = store.read_json(path)
            skill_id = str(data.get("id", path.stem))
            entries[(source, skill_id)] = _skill_list_entry(store, skill_id, path, source)
        for path in sorted(directory.glob("*/skill.json")):
            data = store.read_json(path)
            skill_id = str(data.get("id", path.parent.name))
            entries[(source, skill_id)] = _skill_list_entry(store, skill_id, path, source)
    return sorted(entries.values(), key=lambda item: (item["source"] != "workspace", str(item["id"])))


def _skill_list_entry(store: WorkflowStore, skill_id: str, json_path: Path, source: str) -> JsonDict:
    data = store.read_json(json_path)
    return {
        "id": skill_id,
        "name": data.get("name", skill_id),
        "path": _relative_path(store.root, json_path),
        "source": source,
        "editable": source == "workspace",
        "executor": data.get("executor", ""),
        "ref": data.get("ref", ""),
        "has_markdown": colocated_markdown_path(json_path) is not None or bool(data.get("ref")),
    }


def get_skill(
    store: WorkflowStore,
    skill_id: str,
    skill_dirs: list[Path] | None = None,
    *,
    source: str | None = None,
) -> JsonDict:
    location = find_skill_location(store, skill_id, skill_dirs, source=source)
    skill = SkillSpec.from_dict(store.read_json(location.json_path))
    markdown = read_skill_markdown(location.json_path, skill, store.project_root)
    return {
        "skill": {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "goal": skill.goal,
            "output": skill.output,
            "quality": skill.quality,
            "ref": skill.ref,
            "executor": skill.executor,
        },
        "markdown": markdown,
        "path": _relative_path(store.root, location.json_path),
        "source": location.source,
        "editable": location.editable,
    }


def save_skill(store: WorkflowStore, skill: JsonDict, markdown: str = "") -> JsonDict:
    report = ValidationReport()
    validate_skill_data(skill, report)
    if not report.ok:
        raise ValueError("; ".join(report.errors))
    store.init()
    skill_id = str(skill["id"]).strip()
    target_dir = store.aiwf / "skills" / skill_id
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "skill.json"
    store.write_json(json_path, skill)
    if markdown.strip():
        (target_dir / "SKILL.md").write_text(markdown.rstrip() + "\n", encoding="utf-8")
    return get_skill(store, skill_id)


def delete_skill(store: WorkflowStore, skill_id: str) -> None:
    location = find_skill_location(store, skill_id)
    if not location.editable:
        raise ValueError(f"Skill is read-only: {skill_id}")
    target_dir = store.aiwf / "skills" / skill_id
    if target_dir.exists() and target_dir.is_dir():
        shutil.rmtree(target_dir)
        return
    if location.json_path.exists():
        location.json_path.unlink()
        sibling_md = colocated_markdown_path(location.json_path)
        if sibling_md and sibling_md.exists():
            sibling_md.unlink()


def clone_skill(store: WorkflowStore, skill_id: str, new_id: str | None = None) -> JsonDict:
    source = find_skill_location(store, skill_id)
    if source.editable and new_id is None:
        raise ValueError("Workspace skill already exists; provide new_id to clone.")
    detail = get_skill(store, skill_id)
    cloned = dict(detail["skill"])
    target_id = new_id or skill_id
    cloned["id"] = target_id
    cloned["name"] = f"{cloned.get('name', target_id)} Copy" if new_id is None else cloned.get("name", target_id)
    return save_skill(store, cloned, str(detail.get("markdown") or ""))


def ensure_skill_ref(skill: SkillSpec, store: WorkflowStore, skill_dirs: list[Path]) -> SkillSpec:
    if skill.ref:
        return skill
    try:
        location = find_skill_location(store, skill.id, skill_dirs)
    except FileNotFoundError:
        return skill
    colocated = colocated_markdown_path(location.json_path)
    if not colocated:
        return skill
    try:
        ref = colocated.resolve().relative_to(store.project_root.resolve()).as_posix()
    except ValueError:
        ref = colocated.as_posix()
    return SkillSpec(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        goal=skill.goal,
        output=skill.output,
        quality=skill.quality,
        ref=ref,
        executor=skill.executor,
    )


def default_wayland_roots() -> list[tuple[str, Path]]:
    roots: list[tuple[str, Path]] = []
    appdata = os.environ.get("APPDATA", "").strip()
    if not appdata:
        return roots
    base = Path(appdata) / "Wayland" / "config"
    roots.append(("wayland-user", base / "skills"))
    roots.append(("wayland-bundled", base / "builtin-skills"))
    roots.append(("wayland-builtin", base / "builtin-skills" / "_builtin"))
    return roots


def list_wayland_skills(store: WorkflowStore | None = None, extra_roots: list[str] | None = None) -> list[JsonDict]:
    entries: dict[str, JsonDict] = {}
    installed: set[str] = set()
    if store is not None:
        installed = {item["id"] for item in list_skills(store)}
    roots = default_wayland_roots()
    for raw in extra_roots or []:
        path = Path(raw).expanduser()
        if path.exists():
            roots.append(("custom", path))
    for source, root in roots:
        if not root.exists():
            continue
        for path in sorted(root.iterdir()):
            if not path.is_dir():
                continue
            skill_md = path / "SKILL.md"
            if not skill_md.exists():
                continue
            skill_id = path.name
            preview = _markdown_preview(skill_md.read_text(encoding="utf-8"))
            entries[skill_id] = {
                "id": skill_id,
                "name": skill_id.replace("-", " ").replace("_", " ").title(),
                "source": source,
                "path": str(path),
                "preview": preview,
                "installed": skill_id in installed,
            }
    return sorted(entries.values(), key=lambda item: str(item["id"]))


def _slugify_skill_id(raw: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw.strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "imported_skill"


def _parse_frontmatter(content: str) -> tuple[JsonDict, str]:
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end < 0:
        return {}, content
    block = content[3:end].strip()
    body = content[end + 4 :].lstrip("\n")
    meta: JsonDict = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key in {"name", "description", "goal"}:
            meta[key] = value
    return meta, body


def _skill_id_from_path(path: Path) -> str:
    name = path.name
    if name.upper() == "SKILL.MD":
        return _slugify_skill_id(path.parent.name)
    stem = path.stem
    if stem.upper().endswith(".SKILL"):
        stem = stem[: -len(".SKILL")]
    return _slugify_skill_id(stem)


def _resolve_markdown_source(
    markdown_path: str | None = None,
    markdown: str | None = None,
) -> tuple[str, Path | None]:
    if markdown is not None and markdown.strip():
        return markdown, None
    if not markdown_path or not markdown_path.strip():
        raise ValueError("Missing markdown content or markdown_path.")
    candidate = Path(markdown_path).expanduser()
    if candidate.is_dir():
        candidate = candidate / "SKILL.md"
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"SKILL markdown not found: {markdown_path}")
    return candidate.read_text(encoding="utf-8"), candidate.resolve()


def build_skill_from_markdown(
    markdown: str,
    skill_id: str | None = None,
    source_path: Path | None = None,
) -> tuple[JsonDict, str]:
    frontmatter, body = _parse_frontmatter(markdown)
    resolved_id = skill_id or str(frontmatter.get("name") or "")
    if not resolved_id and source_path is not None:
        resolved_id = _skill_id_from_path(source_path)
    resolved_id = _slugify_skill_id(resolved_id)
    title = _extract_goal_from_markdown(body) or _extract_goal_from_markdown(markdown)
    description = str(frontmatter.get("description") or "").strip() or _markdown_preview(body or markdown, limit=240)
    goal = str(frontmatter.get("goal") or "").strip() or title or f"Execute the {resolved_id} skill workflow."
    display_name = title or resolved_id.replace("-", " ").replace("_", " ").title()
    payload: JsonDict = {
        "id": resolved_id,
        "name": display_name,
        "description": description,
        "goal": goal,
        "output": {"primary": f"{resolved_id}.md"},
        "quality": ["Follow the attached SKILL.md instructions.", "Make assumptions explicit."],
        "executor": "skill",
        "ref": "",
    }
    stored_markdown = body if frontmatter else markdown
    return payload, stored_markdown.rstrip() + "\n"


def preview_skill_markdown(
    store: WorkflowStore,
    markdown_path: str | None = None,
    markdown: str | None = None,
    skill_id: str | None = None,
) -> JsonDict:
    content, source_path = _resolve_markdown_source(markdown_path, markdown)
    payload, stored_markdown = build_skill_from_markdown(content, skill_id=skill_id, source_path=source_path)
    resolved_id = str(payload["id"])
    conflict = False
    try:
        find_skill_location(store, resolved_id)
        conflict = True
    except FileNotFoundError:
        conflict = False
    return {
        "skill": payload,
        "markdown": stored_markdown,
        "source": "import",
        "editable": True,
        "path": str(source_path) if source_path else "",
        "conflict": conflict,
    }


def import_skill_markdown(
    store: WorkflowStore,
    markdown_path: str | None = None,
    markdown: str | None = None,
    skill_id: str | None = None,
    new_id: str | None = None,
) -> JsonDict:
    preview = preview_skill_markdown(store, markdown_path=markdown_path, markdown=markdown, skill_id=skill_id)
    payload = dict(preview["skill"])
    if new_id:
        payload["id"] = _slugify_skill_id(new_id)
    return save_skill(store, payload, str(preview.get("markdown") or ""))


def import_wayland_skill(store: WorkflowStore, skill_id: str, wayland_path: str | None = None) -> JsonDict:
    source_dir: Path | None = None
    if wayland_path:
        candidate = Path(wayland_path)
        if candidate.is_dir() and (candidate / "SKILL.md").exists():
            source_dir = candidate
    if source_dir is None:
        for _, root in default_wayland_roots():
            candidate = root / skill_id
            if candidate.exists() and (candidate / "SKILL.md").exists():
                source_dir = candidate
                break
    if source_dir is None:
        raise FileNotFoundError(f"Wayland skill not found: {skill_id}")
    markdown = (source_dir / "SKILL.md").read_text(encoding="utf-8")
    goal = _extract_goal_from_markdown(markdown) or f"Execute the {skill_id} skill workflow."
    payload: JsonDict = {
        "id": skill_id,
        "name": skill_id.replace("-", " ").replace("_", " ").title(),
        "description": _markdown_preview(markdown, limit=240),
        "goal": goal,
        "output": {"primary": f"{skill_id}.md"},
        "quality": ["Follow the attached SKILL.md instructions.", "Make assumptions explicit."],
        "executor": "skill",
        "ref": "",
    }
    return save_skill(store, payload, markdown)


def market_catalog_path(store: WorkflowStore) -> Path:
    return store.project_root / "examples" / "market" / "catalog.json"


def list_market_catalog(store: WorkflowStore) -> JsonDict:
    path = market_catalog_path(store)
    if not path.exists():
        return {"skills": [], "catalog_path": str(path)}
    data = store.read_json(path)
    skills = data.get("skills", [])
    if not isinstance(skills, list):
        skills = []
    installed = {item["id"] for item in list_skills(store)}
    enriched = []
    for item in skills:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        entry["installed"] = str(entry.get("id", "")) in installed
        enriched.append(entry)
    return {"skills": enriched, "catalog_path": _relative_path(store.root, path)}


def install_market_skill(store: WorkflowStore, skill_id: str) -> JsonDict:
    catalog = list_market_catalog(store)
    entry = next((item for item in catalog["skills"] if item.get("id") == skill_id), None)
    if entry is None:
        raise FileNotFoundError(f"Market skill not found: {skill_id}")
    clone_from = str(entry.get("clone_from") or skill_id)
    try:
        find_skill_location(store, skill_id)
        return get_skill(store, skill_id)
    except FileNotFoundError:
        return clone_skill(store, clone_from, new_id=skill_id)


def _relative_path(root: Path, path: Path) -> str:
    for base in (root.resolve(), root.parent.resolve()):
        try:
            return path.resolve().relative_to(base).as_posix()
        except ValueError:
            continue
    return path.as_posix()


def _markdown_preview(content: str, limit: int = 120) -> str:
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
    preview = " ".join(lines)[:limit].strip()
    return preview or content.strip()[:limit]


def _extract_goal_from_markdown(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    match = re.search(r"goal:\s*(.+)", content, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""

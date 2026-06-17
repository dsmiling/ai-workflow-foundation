from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

from . import __version__
from .packages import export_workflow_package, import_workflow_package
from .runner import WorkflowRunner
from .server import create_server
from .storage import WorkflowStore
from .validation import validate_workflow_file
from .workflows import get_workflow, list_workflows, save_workflow


@dataclass(slots=True)
class DoctorReport:
    ok: bool = True
    version: str = __version__
    workspace: str = ""
    checks: list[dict[str, str]] = field(default_factory=list)

    def pass_check(self, name: str, detail: str = "") -> None:
        self.checks.append({"name": name, "status": "pass", "detail": detail})

    def fail_check(self, name: str, detail: str) -> None:
        self.ok = False
        self.checks.append({"name": name, "status": "fail", "detail": detail})

    def to_dict(self):
        return {
            "ok": self.ok,
            "version": self.version,
            "workspace": self.workspace,
            "checks": self.checks,
        }


def run_doctor(root: Path) -> DoctorReport:
    report = DoctorReport()
    project = root.resolve()
    workspace = project / ".doctor-workspace"
    report.workspace = str(workspace)
    workflow = project / "examples" / "workflows" / "simple_foundation.json"
    unity_workflow = project / "examples" / "workflows" / "unity_activity_create.json"
    skills = [project / "examples" / "skills"]
    store = WorkflowStore(workspace, project_root=project)
    store.init()

    run_check(report, "validate demo workflow", lambda: check_validation(store, workflow, skills))
    run_check(report, "validate unity workflow", lambda: check_validation(store, unity_workflow, skills))
    run_check(report, "workflow catalog", lambda: check_workflow_catalog(store))
    run_check(report, "workflow save to workspace", lambda: check_workflow_save(store, skills))
    state_holder = {}
    unity_state_holder = {}

    def run_workflow_check() -> str:
        runner = WorkflowRunner(store, skill_dirs=skills)
        state = runner.start(workflow)
        if state.status != "paused" or state.current_node != "review_plan":
            raise AssertionError(f"Expected paused at review_plan, got {state.status}/{state.current_node}")
        state_holder["run_id"] = state.run_id
        return state.run_id

    run_check(report, "run workflow to review pause", run_workflow_check)
    run_check(
        report,
        "run unity workflow to review pause",
        lambda: check_unity_run(store, skills, unity_workflow, unity_state_holder),
    )
    run_check(
        report,
        "skill orchestration marker",
        lambda: check_skill_orchestration(store, unity_state_holder["run_id"]),
    )
    run_check(
        report,
        "artifact edit persists",
        lambda: check_artifact_edit(store, unity_state_holder["run_id"]),
    )
    run_check(report, "review approve and resume", lambda: check_review_resume(store, skills, state_holder["run_id"]))
    run_check(report, "change request and rerun", lambda: check_change_rerun(store, skills, state_holder["run_id"]))
    run_check(report, "revision diff and rollback", lambda: check_revision(store, state_holder["run_id"]))
    run_check(report, "package export/import", lambda: check_package(project, workspace, workflow, skills))
    run_check(report, "local server smoke", lambda: check_server(workspace, skills, workflow))
    run_check(report, "desktop shell scaffold", lambda: check_desktop_scaffold(project))
    return report


def run_check(report: DoctorReport, name: str, fn) -> None:
    try:
        detail = fn()
        report.pass_check(name, str(detail or "ok"))
    except Exception as exc:
        report.fail_check(name, str(exc))


def check_validation(store: WorkflowStore, workflow: Path, skills: list[Path]) -> str:
    validation = validate_workflow_file(store, workflow, skill_dirs=skills)
    if not validation.ok:
        raise AssertionError(validation.errors)
    return "ok"


def check_workflow_catalog(store: WorkflowStore) -> str:
    workflows = list_workflows(store)
    ids = {item["id"] for item in workflows}
    if "unity_activity_create" not in ids:
        raise AssertionError("unity_activity_create missing from workflow catalog.")
    return str(len(workflows))


def check_workflow_save(store: WorkflowStore, skills: list[Path]) -> str:
    source = get_workflow(store, "simple_foundation")
    workflow = source["workflow"]
    workflow["id"] = "doctor_saved_workflow"
    workflow["name"] = "Doctor Saved Workflow"
    saved = save_workflow(store, workflow, skills)
    if not saved["path"].endswith(".aiwf/workflows/doctor_saved_workflow.json"):
        raise AssertionError(f"Unexpected saved workflow path: {saved['path']}")
    return saved["path"]


def check_skill_orchestration(store: WorkflowStore, run_id: str) -> str:
    run_dir = store.get_run_dir(run_id)
    state = store.load_state(run_dir)
    artifact_ref = state.nodes["requirement_analysis"].artifact
    if not artifact_ref:
        raise AssertionError("requirement_analysis artifact ref is missing.")
    content = store.read_artifact_ref(run_dir, artifact_ref)
    if "Skill Orchestration" not in content:
        raise AssertionError("Skill executor marker missing from artifact.")
    return "skill"


def check_unity_run(
    store: WorkflowStore,
    skills: list[Path],
    workflow: Path,
    holder: dict[str, str],
) -> str:
    runner = WorkflowRunner(store, skill_dirs=skills)
    state = runner.start(workflow)
    if state.status != "paused" or state.current_node != "review_mapping":
        raise AssertionError(f"Expected paused at review_mapping, got {state.status}/{state.current_node}")
    run_dir = store.get_run_dir(state.run_id)
    structured = run_dir / "artifacts" / "module_mapping.json"
    if not structured.exists():
        raise AssertionError("Expected module_mapping.json sidecar artifact.")
    holder["run_id"] = state.run_id
    return state.run_id


def check_artifact_edit(store: WorkflowStore, run_id: str) -> str:
    run_dir = store.get_run_dir(run_id)
    state = store.load_state(run_dir)
    artifact_ref = state.nodes["module_mapping"].artifact
    if not artifact_ref:
        raise AssertionError("module_mapping artifact ref is missing.")
    original = store.read_artifact_ref(run_dir, artifact_ref)
    marker = "Doctor artifact edit marker."
    store.write_artifact_ref(run_dir, artifact_ref, original + f"\n{marker}\n")
    if marker not in store.read_artifact_ref(run_dir, artifact_ref):
        raise AssertionError("Artifact edit did not persist.")
    updated = store.load_state(run_dir)
    if updated.nodes["module_mapping"].message != "Artifact manually edited.":
        raise AssertionError("Artifact edit did not update node state.")
    return artifact_ref


def check_review_resume(store: WorkflowStore, skills: list[Path], run_id: str) -> str:
    run_dir = store.get_run_dir(run_id)
    store.write_review(run_dir, "review_plan", "approve", "doctor approval")
    state = WorkflowRunner(store, skill_dirs=skills).resume(run_id)
    if state.status != "completed":
        raise AssertionError(f"Expected completed, got {state.status}")
    return "completed"


def check_change_rerun(store: WorkflowStore, skills: list[Path], run_id: str) -> str:
    run_dir = store.get_run_dir(run_id)
    feedback = "Doctor feedback: split reward modules."
    change_id = store.create_change_request(run_dir, "module_breakdown", feedback, source="doctor")
    store.apply_change_request(run_dir, change_id)
    state = WorkflowRunner(store, skill_dirs=skills).rerun_from(run_id, "module_breakdown")
    if state.status != "paused":
        raise AssertionError(f"Expected paused after rerun, got {state.status}")
    artifact = run_dir / state.nodes["module_breakdown"].artifact
    if feedback not in artifact.read_text(encoding="utf-8"):
        raise AssertionError("Rerun artifact does not contain applied feedback.")
    return change_id


def check_revision(store: WorkflowStore, run_id: str) -> str:
    run_dir = store.get_run_dir(run_id)
    state = store.load_state(run_dir)
    artifact = run_dir / state.nodes["module_breakdown"].artifact
    original = artifact.read_text(encoding="utf-8")
    first = store.create_revision(run_dir, "doctor baseline")
    artifact.write_text(original + "\nDoctor diff marker.\n", encoding="utf-8")
    second = store.create_revision(run_dir, "doctor edited")
    diff = store.diff_revisions(run_dir, first, second)
    if "Doctor diff marker" not in diff:
        raise AssertionError("Revision diff did not contain marker.")
    store.rollback_revision(run_dir, first)
    if artifact.read_text(encoding="utf-8") != original:
        raise AssertionError("Rollback did not restore artifact.")
    return second


def check_package(project: Path, workspace: Path, workflow: Path, skills: list[Path]) -> str:
    source_store = WorkflowStore(project)
    package_path = workspace / "doctor.aiwf.zip"
    export_workflow_package(source_store, workflow, package_path, skill_dirs=skills)
    target_store = WorkflowStore(workspace / "package-target")
    result = import_workflow_package(target_store, package_path)
    validation = validate_workflow_file(
        target_store,
        target_store.root / result["workflow"],
        skill_dirs=[target_store.aiwf / "skills"],
    )
    if not validation.ok:
        raise AssertionError(validation.errors)
    return str(package_path)


def check_desktop_scaffold(project: Path) -> str:
    required = [
        project / "Launch-AIWF.ps1",
        project / "desktop" / "package.json",
        project / "desktop" / "src-tauri" / "tauri.conf.json",
        project / "desktop" / "src-tauri" / "src" / "lib.rs",
        project / "desktop" / "src-tauri" / "icons" / "icon.ico",
    ]
    missing = [str(path.relative_to(project)) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"Missing desktop files: {missing}")
    return "ok"


def check_server(workspace: Path, skills: list[Path], workflow: Path) -> str:
    server = create_server(workspace / "server", port=0, skill_dirs=skills, project_root=workspace.parent)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        health = api_get(base, "/health")
        if health.get("status") != "ok":
            raise AssertionError(f"Bad health response: {health}")
        html = http_get_text(base, "/")
        if "AI Workflow Foundation" not in html:
            raise AssertionError("Web panel did not render expected title.")
        catalog = api_get(base, "/workflows")
        if not any(item["id"] == "unity_activity_create" for item in catalog.get("workflows", [])):
            raise AssertionError("Workflow catalog missing unity_activity_create.")
        run = api_post(
            base,
            "/runs",
            {"workflow_id": "unity_activity_create", "executor": "mock"},
        )
        if run["state"]["status"] != "paused":
            raise AssertionError("Server run did not pause at review.")
        if "workflowSelect" not in html or "editorNodes" not in html:
            raise AssertionError("Web panel missing workflow editor.")
        if "Skill 助手" not in html:
            raise AssertionError("Web panel missing skill assistant.")
        return f"port={server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def api_get(base: str, path: str):
    with urlopen(base + path, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def api_post(base: str, path: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        base + path,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def http_get_text(base: str, path: str) -> str:
    with urlopen(base + path, timeout=5) as response:
        return response.read().decode("utf-8")

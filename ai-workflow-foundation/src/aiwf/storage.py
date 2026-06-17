from __future__ import annotations

import json
import shutil
import difflib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datetime import datetime, timezone

from .models import ExecutionResult, RunState, SkillSpec, WorkflowSpec


JsonDict = dict[str, Any]


class WorkflowStore:
    def __init__(self, root: Path, project_root: Path | None = None) -> None:
        self.root = root
        self.project_root = (project_root or root).resolve()
        self.aiwf = root / ".aiwf"
        self.runs = self.aiwf / "runs"
        self.revisions = self.aiwf / "revisions"

    def init(self) -> None:
        for path in [
            self.aiwf,
            self.aiwf / "workflows",
            self.aiwf / "skills",
            self.runs,
            self.revisions,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def load_workflow(self, path: Path) -> WorkflowSpec:
        return WorkflowSpec.from_dict(self.read_json(path))

    def load_skill(self, skill_id: str, search_dirs: list[Path]) -> SkillSpec:
        candidates = []
        for directory in search_dirs:
            candidates.append(directory / f"{skill_id}.json")
            candidates.append(directory / skill_id / "skill.json")
        for candidate in candidates:
            if candidate.exists():
                return SkillSpec.from_dict(self.read_json(candidate))
        raise FileNotFoundError(f"Skill not found: {skill_id}")

    def create_run(self, workflow_path: Path, workflow: WorkflowSpec) -> Path:
        run_id = self.new_id("run")
        run_dir = self.runs / run_id
        for child in ["artifacts", "reviews", "changes", "revisions", "node_results", "node_sessions"]:
            (run_dir / child).mkdir(parents=True, exist_ok=True)
        shutil.copy2(workflow_path, run_dir / "workflow.lock.json")
        state = RunState(
            run_id=run_id,
            workflow_id=workflow.id,
            status="pending",
            current_node=None,
            nodes={},
            started_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.save_state(run_dir, state)
        return run_dir

    def get_run_dir(self, run_id: str) -> Path:
        run_dir = self.runs / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")
        return run_dir

    def load_locked_workflow(self, run_dir: Path) -> WorkflowSpec:
        return self.load_workflow(run_dir / "workflow.lock.json")

    def load_state(self, run_dir: Path) -> RunState:
        return RunState.from_dict(self.read_json(run_dir / "state.json"))

    def save_state(self, run_dir: Path, state: RunState) -> None:
        state.updated_at = datetime.now(timezone.utc).isoformat()
        self.write_json(run_dir / "state.json", state.to_dict())

    def write_artifact(self, run_dir: Path, node_id: str, filename: str, content: str) -> str:
        artifact_path = run_dir / "artifacts" / filename
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(content, encoding="utf-8")
        return artifact_path.relative_to(run_dir).as_posix()

    def read_artifact_ref(self, run_dir: Path, artifact_ref: str) -> str:
        path = self.resolve_run_artifact_path(run_dir, artifact_ref)
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_ref}")
        return path.read_text(encoding="utf-8")

    def write_artifact_ref(self, run_dir: Path, artifact_ref: str, content: str) -> str:
        normalized = self.normalize_artifact_ref(artifact_ref)
        path = self.resolve_run_artifact_path(run_dir, normalized)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        state = self.load_state(run_dir)
        updated = False
        for node in state.nodes.values():
            if node.artifact in {artifact_ref, normalized}:
                node.message = "Artifact manually edited."
                updated = True
        if updated:
            self.save_state(run_dir, state)
        return normalized

    @staticmethod
    def normalize_artifact_ref(artifact_ref: str) -> str:
        ref = Path(artifact_ref.replace("\\", "/"))
        if ref.is_absolute() or ".." in ref.parts:
            raise ValueError(f"Invalid artifact ref: {artifact_ref}")
        normalized = ref.as_posix()
        if not normalized.startswith("artifacts/"):
            raise ValueError(f"Artifact ref must be under artifacts/: {artifact_ref}")
        return normalized

    @staticmethod
    def resolve_run_artifact_path(run_dir: Path, artifact_ref: str) -> Path:
        normalized = WorkflowStore.normalize_artifact_ref(artifact_ref)
        ref = Path(normalized)
        path = (run_dir / ref).resolve()
        run_root = run_dir.resolve()
        if run_root not in path.parents:
            raise ValueError(f"Artifact ref escapes run directory: {artifact_ref}")
        return path

    def write_node_result(self, run_dir: Path, node_id: str, result: ExecutionResult) -> Path:
        path = run_dir / "node_results" / f"{node_id}.json"
        self.write_json(path, result.to_dict())
        return path

    def read_node_result(self, run_dir: Path, node_id: str) -> ExecutionResult | None:
        path = run_dir / "node_results" / f"{node_id}.json"
        if not path.exists():
            return None
        return ExecutionResult.from_dict(self.read_json(path))

    def list_node_assets(self, run_dir: Path, node_id: str) -> list[JsonDict]:
        result = self.read_node_result(run_dir, node_id)
        if result:
            return [asset.to_dict() for asset in result.assets]
        state = self.load_state(run_dir)
        node = state.nodes.get(node_id)
        if node and node.artifact:
            from .execution_result import synthesize_from_artifact

            synthesized = synthesize_from_artifact(node_id, node.artifact, run_dir=run_dir)
            if synthesized:
                return [asset.to_dict() for asset in synthesized.assets]
        return []

    def write_review(self, run_dir: Path, node_id: str, decision: str, feedback: str) -> Path:
        path = run_dir / "reviews" / f"{node_id}.json"
        payload = {
            "node_id": node_id,
            "decision": decision,
            "feedback": feedback,
            "created_at": self.now(),
        }
        self.write_json(path, payload)
        return path

    def load_review(self, run_dir: Path, node_id: str) -> JsonDict | None:
        path = run_dir / "reviews" / f"{node_id}.json"
        if not path.exists():
            return None
        review = self.read_json(path)
        if review.get("decision") == "pending":
            return None
        return review

    def invalidate_review(self, run_dir: Path, node_id: str) -> None:
        path = run_dir / "reviews" / f"{node_id}.json"
        payload = {
            "node_id": node_id,
            "decision": "pending",
            "feedback": "Invalidated by rerun.",
            "created_at": self.now(),
        }
        self.write_json(path, payload)

    def create_revision(self, run_dir: Path, message: str) -> str:
        revision_id = self.new_id("rev")
        target = run_dir / "revisions" / revision_id
        target.mkdir(parents=True, exist_ok=True)
        for name in ["artifacts", "reviews", "changes"]:
            source = run_dir / name
            if source.exists():
                shutil.copytree(source, target / name, dirs_exist_ok=True)
        for name in ["state.json", "workflow.lock.json"]:
            source = run_dir / name
            if source.exists():
                shutil.copy2(source, target / name)
        self.write_json(
            target / "manifest.json",
            {
                "revision_id": revision_id,
                "run_id": run_dir.name,
                "message": message,
                "created_at": self.now(),
            },
        )
        return revision_id

    def create_change_request(
        self,
        run_dir: Path,
        node_id: str,
        feedback: str,
        source: str = "manual",
    ) -> str:
        change_id = self.new_id("chg")
        payload = {
            "change_id": change_id,
            "node_id": node_id,
            "status": "proposed",
            "source": source,
            "feedback": feedback,
            "created_at": self.now(),
            "operations": [
                {
                    "target": "workflow.node.params.feedback_history",
                    "operation": "append",
                    "value": {
                        "feedback": feedback,
                        "created_at": self.now(),
                    },
                },
                {
                    "target": "workflow.node.params.last_feedback",
                    "operation": "set",
                    "value": feedback,
                },
            ],
        }
        self.write_json(run_dir / "changes" / f"{change_id}.json", payload)
        return change_id

    def list_change_requests(self, run_dir: Path) -> list[JsonDict]:
        changes_dir = run_dir / "changes"
        if not changes_dir.exists():
            return []
        changes = []
        for path in sorted(changes_dir.glob("*.json")):
            changes.append(self.read_json(path))
        return changes

    def load_change_request(self, run_dir: Path, change_id: str) -> JsonDict:
        path = run_dir / "changes" / f"{change_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Change request not found: {change_id}")
        return self.read_json(path)

    def apply_change_request(self, run_dir: Path, change_id: str) -> JsonDict:
        change = self.load_change_request(run_dir, change_id)
        if change.get("status") == "applied":
            return change
        workflow_path = run_dir / "workflow.lock.json"
        workflow = self.read_json(workflow_path)
        node = self.find_workflow_node(workflow, change["node_id"])
        params = node.setdefault("params", {})
        for operation in change.get("operations", []):
            target = operation.get("target")
            op = operation.get("operation")
            value = operation.get("value")
            if target == "workflow.node.params.feedback_history" and op == "append":
                params.setdefault("feedback_history", []).append(value)
            elif target == "workflow.node.params.last_feedback" and op == "set":
                params["last_feedback"] = value
            elif target == "workflow.node.params.extra_prompt" and op == "set":
                params["extra_prompt"] = value
            elif target == "workflow.node.params.extra_prompt" and op == "append":
                existing = str(params.get("extra_prompt", ""))
                addition = str(value)
                params["extra_prompt"] = f"{existing}\n{addition}".strip() if existing else addition
            elif target == "workflow.node.inputs" and op == "merge":
                if not isinstance(value, dict):
                    raise ValueError("inputs merge requires object value")
                inputs = node.setdefault("inputs", {})
                inputs.update(value)
            else:
                raise ValueError(f"Unsupported change operation: {operation}")
        change["status"] = "applied"
        change["applied_at"] = self.now()
        self.write_json(workflow_path, workflow)
        self.write_json(run_dir / "changes" / f"{change_id}.json", change)
        return change

    def list_revisions(self, run_dir: Path) -> list[JsonDict]:
        revisions_dir = run_dir / "revisions"
        if not revisions_dir.exists():
            return []
        revisions = []
        for revision_dir in sorted(revisions_dir.iterdir()):
            manifest = revision_dir / "manifest.json"
            if revision_dir.is_dir() and manifest.exists():
                revisions.append(self.read_json(manifest))
        return revisions

    def diff_revisions(self, run_dir: Path, left_id: str, right_id: str) -> str:
        left = self.get_revision_dir(run_dir, left_id)
        right = self.get_revision_dir(run_dir, right_id)
        return self.diff_snapshot_paths(left, right, self.snapshot_files(left), self.snapshot_files(right))

    def diff_revision_to_worktree(self, run_dir: Path, revision_id: str) -> str:
        revision = self.get_revision_dir(run_dir, revision_id)
        return self.diff_snapshot_paths(
            revision,
            run_dir,
            self.snapshot_files(revision),
            self.run_files(run_dir),
        )

    def diff_snapshot_paths(
        self,
        left: Path,
        right: Path,
        left_files: set[Path],
        right_files: set[Path],
    ) -> str:
        all_files = sorted(set(left_files) | set(right_files))
        sections = []
        for rel_path in all_files:
            left_path = left / rel_path
            right_path = right / rel_path
            if left_path.exists() and right_path.exists():
                if left_path.read_bytes() == right_path.read_bytes():
                    continue
                if self.is_text_file(left_path) and self.is_text_file(right_path):
                    sections.extend(self.unified_diff(left_path, right_path, rel_path))
                else:
                    sections.append(f"Binary changed: {rel_path}")
            elif left_path.exists():
                sections.append(f"Deleted: {rel_path}")
            else:
                sections.append(f"Added: {rel_path}")
        return "\n".join(sections) if sections else "No differences."

    def rollback_revision(self, run_dir: Path, revision_id: str) -> None:
        revision = self.get_revision_dir(run_dir, revision_id)
        for name in ["artifacts", "reviews", "changes"]:
            target = run_dir / name
            source = revision / name
            if source.exists():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                target.mkdir(parents=True, exist_ok=True)
        for name in ["state.json", "workflow.lock.json"]:
            source = revision / name
            if source.exists():
                shutil.copy2(source, run_dir / name)

    def get_revision_dir(self, run_dir: Path, revision_id: str) -> Path:
        revision_dir = run_dir / "revisions" / revision_id
        if not revision_dir.exists():
            raise FileNotFoundError(f"Revision not found: {revision_id}")
        return revision_dir

    @staticmethod
    def find_workflow_node(workflow: JsonDict, node_id: str) -> JsonDict:
        for node in workflow.get("nodes", []):
            if node.get("id") == node_id:
                return node
        raise ValueError(f"Node not found in workflow lock: {node_id}")

    @staticmethod
    def snapshot_files(snapshot_dir: Path) -> set[Path]:
        ignored = {"manifest.json"}
        return {
            path.relative_to(snapshot_dir)
            for path in snapshot_dir.rglob("*")
            if path.is_file() and path.name not in ignored
        }

    @staticmethod
    def run_files(run_dir: Path) -> set[Path]:
        files: set[Path] = set()
        for name in ["artifacts", "reviews", "changes"]:
            root = run_dir / name
            if root.exists():
                files.update(path.relative_to(run_dir) for path in root.rglob("*") if path.is_file())
        for name in ["state.json", "workflow.lock.json"]:
            if (run_dir / name).exists():
                files.add(Path(name))
        return files

    @staticmethod
    def is_text_file(path: Path) -> bool:
        try:
            path.read_text(encoding="utf-8")
            return True
        except UnicodeDecodeError:
            return False

    @staticmethod
    def unified_diff(left: Path, right: Path, rel_path: Path) -> list[str]:
        left_lines = left.read_text(encoding="utf-8").splitlines(keepends=True)
        right_lines = right.read_text(encoding="utf-8").splitlines(keepends=True)
        return list(
            difflib.unified_diff(
                left_lines,
                right_lines,
                fromfile=f"a/{rel_path.as_posix()}",
                tofile=f"b/{rel_path.as_posix()}",
            )
        )

    @staticmethod
    def read_json(path: Path) -> JsonDict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def write_json(path: Path, data: JsonDict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def new_id(cls, prefix: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        return f"{prefix}_{stamp}"

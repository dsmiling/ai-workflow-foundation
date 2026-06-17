from __future__ import annotations

import argparse
from pathlib import Path

from .packages import export_workflow_package, import_workflow_package
from .doctor import run_doctor
from .runner import WorkflowRunner
from .server import create_server
from .storage import WorkflowStore
from .validation import validate_workflow_file
from .workflows import delete_workflow, get_workflow, list_workflows, save_workflow


def main() -> int:
    try:
        return run_main()
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


def run_main() -> int:
    parser = argparse.ArgumentParser(prog="aiwf")
    parser.add_argument("--root", default=".", help="Workspace root. Defaults to current directory.")
    parser.add_argument(
        "--project-root",
        default="",
        help="Project root containing examples/ and src/. Defaults to --root.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create the local .aiwf workspace.")

    run_parser = subparsers.add_parser("run", help="Start a workflow run.")
    run_parser.add_argument("workflow", help="Path to workflow JSON.")
    run_parser.add_argument("--executor", help="Executor name: mock, agent, or skill.")
    run_parser.add_argument("--agent-provider", help="Agent sub-executor when --executor=agent.")

    validate_parser = subparsers.add_parser("validate", help="Validate a workflow and referenced skills.")
    validate_parser.add_argument("workflow", help="Path to workflow JSON.")

    resume_parser = subparsers.add_parser("resume", help="Resume a paused run.")
    resume_parser.add_argument("run_id")
    resume_parser.add_argument("--executor", help="Executor name: mock or agent.")
    resume_parser.add_argument("--agent-provider", help="Agent sub-executor when --executor=agent.")

    rerun_parser = subparsers.add_parser("rerun", help="Rerun from a node and reset downstream node state.")
    rerun_parser.add_argument("run_id")
    rerun_parser.add_argument("node_id")
    rerun_parser.add_argument("--executor", help="Executor name: mock or agent.")
    rerun_parser.add_argument("--agent-provider", help="Agent sub-executor when --executor=agent.")

    status_parser = subparsers.add_parser("status", help="Show run status.")
    status_parser.add_argument("run_id")

    review_parser = subparsers.add_parser("review", help="Record a review decision.")
    review_parser.add_argument("run_id")
    review_parser.add_argument("node_id")
    review_parser.add_argument("decision", choices=["approve", "reject"])
    review_parser.add_argument("--feedback", default="")
    review_parser.add_argument("--target-node", help="Node to tune when rejection feedback targets upstream output.")

    changes_parser = subparsers.add_parser("changes", help="List run change requests.")
    changes_parser.add_argument("run_id")

    show_change_parser = subparsers.add_parser("show-change", help="Show a change request JSON.")
    show_change_parser.add_argument("run_id")
    show_change_parser.add_argument("change_id")

    apply_change_parser = subparsers.add_parser("apply-change", help="Apply a change request to workflow.lock.json.")
    apply_change_parser.add_argument("run_id")
    apply_change_parser.add_argument("change_id")
    apply_change_parser.add_argument("--rerun", action="store_true", help="Rerun from the change request node after applying.")

    commit_parser = subparsers.add_parser("commit", help="Create a revision snapshot.")
    commit_parser.add_argument("run_id")
    commit_parser.add_argument("--message", default="")

    revisions_parser = subparsers.add_parser("revisions", help="List run revisions.")
    revisions_parser.add_argument("run_id")

    diff_parser = subparsers.add_parser("diff", help="Diff revisions or a revision against current run files.")
    diff_parser.add_argument("run_id")
    diff_parser.add_argument("left_revision")
    diff_parser.add_argument("right_revision", nargs="?")

    rollback_parser = subparsers.add_parser("rollback", help="Restore run files from a revision snapshot.")
    rollback_parser.add_argument("run_id")
    rollback_parser.add_argument("revision_id")

    edit_artifact_parser = subparsers.add_parser("edit-artifact", help="Edit a run artifact in place.")
    edit_artifact_parser.add_argument("run_id")
    edit_artifact_parser.add_argument("artifact_ref", help="Artifact path relative to run dir, e.g. artifacts/build_plan.md")
    edit_artifact_parser.add_argument("--content", help="New artifact content.")
    edit_artifact_parser.add_argument("--file", help="Read new artifact content from a file.")

    serve_parser = subparsers.add_parser("serve", help="Start the local HTTP API server.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--executor", help="Default executor name: mock, agent, or skill.")
    serve_parser.add_argument("--agent-provider", help="Default agent sub-executor when --executor=agent.")

    subparsers.add_parser("workflows", help="List available workflows.")

    workflow_parser = subparsers.add_parser("workflow", help="Show a workflow by id.")
    workflow_parser.add_argument("workflow_id")

    save_workflow_parser = subparsers.add_parser("save-workflow", help="Save a workflow JSON into .aiwf/workflows.")
    save_workflow_parser.add_argument("workflow", help="Path to workflow JSON.")

    delete_workflow_parser = subparsers.add_parser("delete-workflow", help="Delete a workspace workflow.")
    delete_workflow_parser.add_argument("workflow_id")

    export_parser = subparsers.add_parser("export-package", help="Export a workflow and referenced skills as a zip package.")
    export_parser.add_argument("workflow", help="Path to workflow JSON.")
    export_parser.add_argument("package", help="Output package zip path.")

    import_parser = subparsers.add_parser("import-package", help="Import a workflow package into .aiwf.")
    import_parser.add_argument("package", help="Package zip path.")

    subparsers.add_parser("doctor", help="Run the local delivery acceptance checks.")

    args = parser.parse_args()
    root = Path(args.root).resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else root
    store = WorkflowStore(root, project_root=project_root)

    if args.command == "init":
        store.init()
        print(f"Initialized {store.aiwf}")
        return 0
    if args.command == "run":
        store.init()
        runner = WorkflowRunner(store, executor_name=args.executor, agent_provider=getattr(args, "agent_provider", None))
        state = runner.start((root / args.workflow).resolve())
        print_state(state)
        return 0
    if args.command == "validate":
        report = validate_workflow_file(store, (root / args.workflow).resolve())
        print_json(report.to_dict())
        return 0 if report.ok else 1
    if args.command == "resume":
        runner = WorkflowRunner(store, executor_name=args.executor, agent_provider=getattr(args, "agent_provider", None))
        state = runner.resume(args.run_id)
        print_state(state)
        return 0
    if args.command == "rerun":
        runner = WorkflowRunner(store, executor_name=args.executor, agent_provider=getattr(args, "agent_provider", None))
        state = runner.rerun_from(args.run_id, args.node_id)
        print_state(state)
        return 0
    if args.command == "status":
        run_dir = store.get_run_dir(args.run_id)
        print_state(store.load_state(run_dir))
        return 0
    if args.command == "review":
        run_dir = store.get_run_dir(args.run_id)
        store.write_review(run_dir, args.node_id, args.decision, args.feedback)
        print(f"Recorded {args.decision} for {args.node_id}")
        if args.decision == "reject":
            target_node = args.target_node or args.node_id
            change_id = store.create_change_request(
                run_dir,
                target_node,
                args.feedback,
                source="review_reject",
            )
            print(f"Proposed change request {change_id}")
        return 0
    if args.command == "changes":
        run_dir = store.get_run_dir(args.run_id)
        changes = store.list_change_requests(run_dir)
        if not changes:
            print("No change requests.")
            return 0
        for change in changes:
            feedback = change.get("feedback", "").replace("\r\n", " ").replace("\n", " ")
            print(f"{change['change_id']} {change['status']} node={change['node_id']} feedback={feedback}")
        return 0
    if args.command == "show-change":
        run_dir = store.get_run_dir(args.run_id)
        print_json(store.load_change_request(run_dir, args.change_id))
        return 0
    if args.command == "apply-change":
        run_dir = store.get_run_dir(args.run_id)
        change = store.apply_change_request(run_dir, args.change_id)
        print(f"Applied change request {args.change_id}")
        if args.rerun:
            runner = WorkflowRunner(store)
            state = runner.rerun_from(args.run_id, change["node_id"])
            print_state(state)
        return 0
    if args.command == "commit":
        run_dir = store.get_run_dir(args.run_id)
        revision_id = store.create_revision(run_dir, args.message)
        print(f"Created revision {revision_id}")
        return 0
    if args.command == "revisions":
        run_dir = store.get_run_dir(args.run_id)
        revisions = store.list_revisions(run_dir)
        if not revisions:
            print("No revisions.")
            return 0
        for revision in revisions:
            message = revision.get("message", "")
            created_at = revision.get("created_at", "")
            print(f"{revision['revision_id']} {created_at} {message}")
        return 0
    if args.command == "diff":
        run_dir = store.get_run_dir(args.run_id)
        if args.right_revision:
            print(store.diff_revisions(run_dir, args.left_revision, args.right_revision))
        else:
            print(store.diff_revision_to_worktree(run_dir, args.left_revision))
        return 0
    if args.command == "rollback":
        run_dir = store.get_run_dir(args.run_id)
        store.rollback_revision(run_dir, args.revision_id)
        print(f"Rolled back {args.run_id} to {args.revision_id}")
        return 0
    if args.command == "edit-artifact":
        run_dir = store.get_run_dir(args.run_id)
        if args.file:
            content = (root / args.file).resolve().read_text(encoding="utf-8")
        elif args.content is not None:
            content = args.content
        else:
            print("Error: edit-artifact requires --content or --file")
            return 1
        try:
            store.write_artifact_ref(run_dir, args.artifact_ref, content)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1
        print(f"Updated {args.artifact_ref}")
        return 0
    if args.command == "serve":
        store.init()
        httpd = create_server(
            root,
            args.host,
            args.port,
            executor_name=args.executor,
            agent_provider=getattr(args, "agent_provider", None),
            project_root=project_root,
        )
        print(f"Serving AIWF API on http://{args.host}:{args.port}")
        httpd.serve_forever()
    if args.command == "export-package":
        manifest = export_workflow_package(store, (root / args.workflow).resolve(), (root / args.package).resolve())
        print_json(manifest)
        return 0
    if args.command == "import-package":
        result = import_workflow_package(store, (root / args.package).resolve())
        print_json(result)
        return 0
    if args.command == "doctor":
        report = run_doctor(root)
        print_json(report.to_dict())
        return 0 if report.ok else 1
    if args.command == "workflows":
        store.init()
        workflows = list_workflows(store)
        if not workflows:
            print("No workflows.")
            return 0
        for item in workflows:
            editable = "editable" if item["editable"] else "readonly"
            print(f"{item['id']} [{item['source']}/{editable}] {item['path']}")
        return 0
    if args.command == "workflow":
        store.init()
        print_json(get_workflow(store, args.workflow_id))
        return 0
    if args.command == "save-workflow":
        store.init()
        data = store.read_json((root / args.workflow).resolve())
        skill_dirs = [root / "examples" / "skills", store.aiwf / "skills"]
        try:
            result = save_workflow(store, data, skill_dirs)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1
        print_json(result)
        return 0
    if args.command == "delete-workflow":
        store.init()
        try:
            delete_workflow(store, args.workflow_id)
        except FileNotFoundError as exc:
            print(f"Error: {exc}")
            return 1
        print(f"Deleted workflow {args.workflow_id}")
        return 0
    raise AssertionError(args.command)


def print_state(state) -> None:
    print(f"run_id: {state.run_id}")
    print(f"workflow_id: {state.workflow_id}")
    print(f"status: {state.status}")
    print(f"current_node: {state.current_node}")
    print("nodes:")
    for node in state.nodes.values():
        artifact = f" artifact={node.artifact}" if node.artifact else ""
        message = f" message={node.message}" if node.message else ""
        print(f"  - {node.id}: {node.status}{artifact}{message}")


def print_json(data) -> None:
    import json

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())

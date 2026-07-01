from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .agents import (
    delete_agent,
    generate_agent_draft,
    get_agent,
    list_agent_templates,
    list_agents,
    list_role_agents,
    rename_agent,
    run_agent_test,
    save_agent,
    stream_agent_generate,
)
from .executor import list_executor_catalog, normalize_executor_name
from .packages import export_workflow_package, import_workflow_package
from .runner import WorkflowRunner
from .storage import WorkflowStore
from .validation import validate_workflow_file
from .workflow_assist import stream_workflow_assist
from .assist_workspace import clear_workflow_assist_session
from .workflows import (
    delete_workflow,
    find_workflow_path,
    get_workflow,
    list_skills,
    list_workflows,
    save_workflow,
)
from .skills import (
    clone_skill,
    delete_skill,
    get_skill,
    import_skill_markdown,
    import_wayland_skill,
    install_market_skill,
    list_market_catalog,
    list_wayland_skills,
    preview_skill_markdown,
    save_skill,
)


JsonDict = dict[str, object]
SKILL_API_VERSION = 2


def create_server(
    root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    skill_dirs: list[Path] | None = None,
    executor_name: str | None = None,
    agent_provider: str | None = None,
    project_root: Path | None = None,
) -> ThreadingHTTPServer:
    resolved_root = root.resolve()
    store = WorkflowStore(resolved_root, project_root=(project_root or resolved_root).resolve())
    runner = WorkflowRunner(
        store,
        skill_dirs=skill_dirs,
        executor_name=executor_name,
        agent_provider=agent_provider,
    )
    web_root = Path(__file__).resolve().parents[2] / "web"

    class AIWFHandler(BaseHTTPRequestHandler):
        server_version = "AIWF/0.1"

        def do_GET(self) -> None:
            if self.try_static():
                return
            self.dispatch("GET")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
            if parts == ["agents", "generate", "stream"]:
                self.handle_agent_generate_stream()
                return
            if parts == ["workflows", "assist", "stream"]:
                self.handle_workflow_assist_stream()
                return
            self.dispatch("POST")

        def handle_workflow_assist_stream(self) -> None:
            try:
                body = self.read_json_body()
                description = body.get("description")
                if not isinstance(description, str) or not description.strip():
                    raise ApiError(HTTPStatus.BAD_REQUEST, "description is required.")
                provider = body.get("provider")
                if provider is not None and not isinstance(provider, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "provider must be a string.")
                draft = body.get("draft")
                if draft is not None and not isinstance(draft, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "draft must be an object.")
                messages = body.get("messages")
                if messages is not None and not isinstance(messages, list):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "messages must be an array.")
                selected_node_id = body.get("selected_node_id")
                if selected_node_id is not None and not isinstance(selected_node_id, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "selected_node_id must be a string.")
                focus_node_ids = body.get("focus_node_ids")
                if focus_node_ids is not None and not isinstance(focus_node_ids, list):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "focus_node_ids must be an array.")
                workflow_id = body.get("workflow_id")
                if workflow_id is not None and not isinstance(workflow_id, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "workflow_id must be a string.")
                session_id = body.get("session_id")
                if session_id is not None and not isinstance(session_id, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "session_id must be a string.")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
                self.end_headers()
                try:
                    for event in stream_workflow_assist(
                        store,
                        runner.skill_dirs,
                        description=description,
                        provider_id=provider,
                        draft=draft,
                        messages=messages,
                        selected_node_id=selected_node_id,
                        focus_node_ids=focus_node_ids,
                        workflow_id=workflow_id if isinstance(workflow_id, str) else None,
                        session_id=session_id if isinstance(session_id, str) else None,
                    ):
                        payload = json.dumps(event, ensure_ascii=False).encode("utf-8")
                        self.wfile.write(b"event: message\ndata: ")
                        self.wfile.write(payload)
                        self.wfile.write(b"\n\n")
                        self.wfile.flush()
                except Exception as exc:
                    payload = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False).encode("utf-8")
                    self.wfile.write(b"event: message\ndata: ")
                    self.wfile.write(payload)
                    self.wfile.write(b"\n\n")
                    self.wfile.flush()
            except ApiError as exc:
                self.write_json(exc.status, {"error": exc.message})
            except Exception as exc:
                self.write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def handle_agent_generate_stream(self) -> None:
            try:
                body = self.read_json_body()
                description = body.get("description")
                if not isinstance(description, str) or not description.strip():
                    raise ApiError(HTTPStatus.BAD_REQUEST, "description is required.")
                provider = body.get("provider")
                if provider is not None and not isinstance(provider, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "provider must be a string.")
                draft = body.get("draft")
                if draft is not None and not isinstance(draft, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "draft must be an object.")
                messages = body.get("messages")
                if messages is not None and not isinstance(messages, list):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "messages must be an array.")
                agent_id = body.get("agent_id")
                if agent_id is not None and not isinstance(agent_id, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "agent_id must be a string.")
                session_id = body.get("session_id")
                if session_id is not None and not isinstance(session_id, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "session_id must be a string.")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
                self.end_headers()
                try:
                    for event in stream_agent_generate(
                        store,
                        description=description,
                        provider_id=provider,
                        draft=draft,
                        messages=messages,
                        agent_id=agent_id if isinstance(agent_id, str) else None,
                        session_id=session_id if isinstance(session_id, str) else None,
                    ):
                        payload = json.dumps(event, ensure_ascii=False).encode("utf-8")
                        self.wfile.write(b"event: message\ndata: ")
                        self.wfile.write(payload)
                        self.wfile.write(b"\n\n")
                        self.wfile.flush()
                except Exception as exc:
                    payload = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False).encode("utf-8")
                    self.wfile.write(b"event: message\ndata: ")
                    self.wfile.write(payload)
                    self.wfile.write(b"\n\n")
                    self.wfile.flush()
            except ApiError as exc:
                self.write_json(exc.status, {"error": exc.message})
            except Exception as exc:
                self.write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def do_PUT(self) -> None:
            self.dispatch("PUT")

        def do_DELETE(self) -> None:
            self.dispatch("DELETE")

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

        def try_static(self) -> bool:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                return self.write_static(web_root / "index.html")
            if parsed.path.startswith("/web/"):
                relative = Path(*[part for part in parsed.path.removeprefix("/web/").split("/") if part])
                target = (web_root / relative).resolve()
                if web_root.resolve() not in target.parents and target != web_root.resolve():
                    self.write_json(HTTPStatus.FORBIDDEN, {"error": "Forbidden."})
                    return True
                return self.write_static(target)
            return False

        def write_static(self, path: Path) -> bool:
            if not path.exists() or not path.is_file():
                self.write_json(HTTPStatus.NOT_FOUND, {"error": "Static file not found."})
                return True
            data = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if path.suffix == ".html":
                content_type = "text/html; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return True

        def dispatch(self, method: str) -> None:
            try:
                parsed = urlparse(self.path)
                parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
                query = parse_qs(parsed.query)
                body = self.read_json_body()
                result = self.route(method, parts, query, body)
                self.write_json(HTTPStatus.OK, result)
            except ApiError as exc:
                self.write_json(exc.status, {"error": exc.message})
            except Exception as exc:
                self.write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def route(
            self,
            method: str,
            parts: list[str],
            query: dict[str, list[str]],
            body: JsonDict,
        ) -> JsonDict:
            if method == "GET" and parts == ["health"]:
                return {"status": "ok", "skill_api": SKILL_API_VERSION}
            if method == "GET" and parts == ["executors"]:
                catalog = list_executor_catalog()
                providers = list(catalog.get("agent_providers", []))
                role_agents = list_role_agents(store)
                catalog["providers"] = providers
                catalog["role_agents"] = role_agents
                merged = list(providers)
                provider_ids = {item["id"] for item in merged if isinstance(item, dict)}
                for agent in role_agents:
                    if agent["id"] in provider_ids:
                        continue
                    merged.append(
                        {
                            "id": agent["id"],
                            "label": agent.get("label") or agent["id"],
                            "kind": agent.get("kind", "api"),
                            "provider": agent.get("provider"),
                            "ident": agent.get("ident", {}),
                            "soul": agent.get("soul", ""),
                            "requires": agent.get("requires", []),
                            "status": agent.get("status"),
                            "ready": agent.get("ready"),
                            "missing": agent.get("missing"),
                            "status_detail": agent.get("status_detail"),
                            "source": "workspace",
                            "tier": "role",
                        }
                    )
                catalog["agent_providers"] = merged
                return catalog
            if parts == ["agents", "generate"] and method == "POST":
                description = body.get("description")
                if not isinstance(description, str) or not description.strip():
                    raise ApiError(HTTPStatus.BAD_REQUEST, "description is required.")
                provider = body.get("provider")
                if provider is not None and not isinstance(provider, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "provider must be a string.")
                draft = body.get("draft")
                if draft is not None and not isinstance(draft, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "draft must be an object.")
                messages = body.get("messages")
                if messages is not None and not isinstance(messages, list):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "messages must be an array.")
                try:
                    return generate_agent_draft(
                        store,
                        description=description,
                        provider_id=provider,
                        draft=draft,
                        messages=messages,
                    )
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            if parts == ["agents", "templates"] and method == "GET":
                return {"templates": list_agent_templates(store.project_root)}
            if parts == ["agents"] and method == "GET":
                return {"agents": list_agents(store)}
            if parts == ["agents"] and method == "POST":
                agent = body.get("agent")
                if not isinstance(agent, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Missing agent object.")
                try:
                    return save_agent(store, agent)
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            if len(parts) == 2 and parts[0] == "agents" and method == "GET":
                try:
                    return {"agent": get_agent(store, parts[1])}
                except FileNotFoundError as exc:
                    raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from exc
            if len(parts) == 2 and parts[0] == "agents" and method == "PUT":
                agent = body.get("agent")
                if not isinstance(agent, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Missing agent object.")
                agent_id = parts[1]
                new_id = str(agent.get("id") or "").strip()
                if not new_id:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Agent id is required.")
                try:
                    if new_id == agent_id:
                        get_agent(store, agent_id)
                        return save_agent(store, agent)
                    return rename_agent(store, agent_id, agent)
                except FileNotFoundError as exc:
                    raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from exc
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            if len(parts) == 2 and parts[0] == "agents" and method == "DELETE":
                try:
                    delete_agent(store, parts[1])
                except FileNotFoundError as exc:
                    raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from exc
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
                return {"status": "deleted", "agent_id": parts[1]}
            if len(parts) == 3 and parts[0] == "agents" and parts[2] == "test" and method == "POST":
                prompt = body.get("prompt")
                if prompt is not None and not isinstance(prompt, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "prompt must be a string.")
                try:
                    return run_agent_test(store, parts[1], prompt=prompt)
                except (FileNotFoundError, ValueError) as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            if method == "POST" and parts == ["init"]:
                store.init()
                return {"status": "initialized", "workspace": str(store.aiwf)}
            if parts == ["workflows"]:
                if method == "GET":
                    return {"workflows": list_workflows(store)}
                if method == "POST":
                    workflow = body.get("workflow")
                    if not isinstance(workflow, dict):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Missing workflow object.")
                    try:
                        return save_workflow(store, workflow, runner.skill_dirs)
                    except ValueError as exc:
                        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            if len(parts) == 4 and parts[0] == "workflows" and parts[2] == "assist" and parts[3] == "session":
                workflow_id = parts[1]
                if method == "GET":
                    from .assist_workspace import load_workflow_assist_session

                    try:
                        return load_workflow_assist_session(store, workflow_id)
                    except ValueError as exc:
                        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
                if method == "DELETE":
                    try:
                        return clear_workflow_assist_session(store, workflow_id)
                    except ValueError as exc:
                        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            if len(parts) == 2 and parts[0] == "workflows":
                workflow_id = parts[1]
                if method == "GET":
                    try:
                        return get_workflow(store, workflow_id)
                    except FileNotFoundError as exc:
                        raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from exc
                if method == "PUT":
                    workflow = body.get("workflow")
                    if not isinstance(workflow, dict):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Missing workflow object.")
                    if workflow.get("id") != workflow_id:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Workflow id mismatch.")
                    try:
                        return save_workflow(store, workflow, runner.skill_dirs)
                    except ValueError as exc:
                        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
                if method == "DELETE":
                    try:
                        delete_workflow(store, workflow_id)
                    except FileNotFoundError as exc:
                        raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from exc
                    return {"status": "deleted", "workflow_id": workflow_id}
            if parts == ["skills"] and method == "GET":
                return {"skills": list_skills(store, runner.skill_dirs)}
            if parts == ["skills"] and method == "POST":
                skill = body.get("skill")
                if not isinstance(skill, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Missing skill object.")
                markdown = body.get("markdown", "")
                if markdown is not None and not isinstance(markdown, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "markdown must be a string.")
                try:
                    return save_skill(store, skill, markdown or "")
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            if len(parts) == 2 and parts[0] == "skills" and method == "GET":
                try:
                    source = first_query(query, "source")
                    return get_skill(store, parts[1], runner.skill_dirs, source=source)
                except FileNotFoundError as exc:
                    raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from exc
            if len(parts) == 2 and parts[0] == "skills" and method == "PUT":
                skill = body.get("skill")
                if not isinstance(skill, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Missing skill object.")
                if skill.get("id") != parts[1]:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Skill id mismatch.")
                markdown = body.get("markdown", "")
                if markdown is not None and not isinstance(markdown, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "markdown must be a string.")
                try:
                    return save_skill(store, skill, markdown or "")
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            if len(parts) == 2 and parts[0] == "skills" and method == "DELETE":
                try:
                    delete_skill(store, parts[1])
                except FileNotFoundError as exc:
                    raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from exc
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
                return {"status": "deleted", "skill_id": parts[1]}
            if len(parts) == 3 and parts[0] == "skills" and parts[2] == "clone" and method == "POST":
                new_id = body.get("new_id")
                if new_id is not None and not isinstance(new_id, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "new_id must be a string.")
                try:
                    return clone_skill(store, parts[1], new_id=new_id or None)
                except (FileNotFoundError, ValueError) as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            if parts == ["skills", "sources", "wayland"] and method == "GET":
                extra = query.get("roots", [])
                return {"skills": list_wayland_skills(store, extra)}
            if parts == ["skills", "import", "wayland"] and method == "POST":
                skill_id = body.get("skill_id")
                if not isinstance(skill_id, str) or not skill_id.strip():
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Missing skill_id.")
                wayland_path = body.get("wayland_path")
                if wayland_path is not None and not isinstance(wayland_path, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "wayland_path must be a string.")
                try:
                    return import_wayland_skill(store, skill_id, wayland_path=wayland_path)
                except FileNotFoundError as exc:
                    raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from exc
            if parts == ["skills", "import", "markdown", "preview"] and method == "POST":
                markdown_path = body.get("markdown_path")
                markdown = body.get("markdown")
                skill_id = body.get("skill_id")
                if markdown_path is not None and not isinstance(markdown_path, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "markdown_path must be a string.")
                if markdown is not None and not isinstance(markdown, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "markdown must be a string.")
                if skill_id is not None and not isinstance(skill_id, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "skill_id must be a string.")
                try:
                    return preview_skill_markdown(
                        store,
                        markdown_path=markdown_path,
                        markdown=markdown,
                        skill_id=skill_id,
                    )
                except FileNotFoundError as exc:
                    raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from exc
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            if parts == ["skills", "import", "markdown"] and method == "POST":
                markdown_path = body.get("markdown_path")
                markdown = body.get("markdown")
                skill_id = body.get("skill_id")
                new_id = body.get("new_id")
                if markdown_path is not None and not isinstance(markdown_path, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "markdown_path must be a string.")
                if markdown is not None and not isinstance(markdown, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "markdown must be a string.")
                if skill_id is not None and not isinstance(skill_id, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "skill_id must be a string.")
                if new_id is not None and not isinstance(new_id, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "new_id must be a string.")
                try:
                    return import_skill_markdown(
                        store,
                        markdown_path=markdown_path,
                        markdown=markdown,
                        skill_id=skill_id,
                        new_id=new_id,
                    )
                except FileNotFoundError as exc:
                    raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from exc
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            if parts == ["skills", "market", "catalog"] and method == "GET":
                return list_market_catalog(store)
            if parts == ["skills", "market", "install"] and method == "POST":
                skill_id = body.get("skill_id")
                if not isinstance(skill_id, str) or not skill_id.strip():
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Missing skill_id.")
                try:
                    return install_market_skill(store, skill_id)
                except FileNotFoundError as exc:
                    raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from exc
            if method == "POST" and parts == ["validate"]:
                workflow_path = self.resolve_workflow_path(body)
                report = validate_workflow_file(store, workflow_path, skill_dirs=runner.skill_dirs)
                return {"report": report.to_dict()}
            if method == "POST" and parts == ["packages", "export"]:
                workflow = body.get("workflow")
                package = body.get("package")
                if not isinstance(workflow, str) or not isinstance(package, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Package export requires workflow and package.")
                manifest = export_workflow_package(
                    store,
                    (store.root / workflow).resolve(),
                    (store.root / package).resolve(),
                    skill_dirs=runner.skill_dirs,
                )
                return {"manifest": manifest}
            if method == "POST" and parts == ["packages", "import"]:
                package = body.get("package")
                if not isinstance(package, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Package import requires package.")
                return {"result": import_workflow_package(store, (store.root / package).resolve())}
            if method == "POST" and parts == ["runs"]:
                workflow_path = self.resolve_workflow_path(body)
                store.init()
                active_runner = self.runner_for_body(body)
                until_node = body.get("until_node")
                if until_node is not None and not isinstance(until_node, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "until_node must be a string.")
                state = active_runner.start(workflow_path, until_node=until_node)
                return {"state": state.to_dict()}
            if len(parts) >= 2 and parts[0] == "runs":
                run_id = parts[1]
                run_dir = store.get_run_dir(run_id)
                if method == "GET" and len(parts) == 2:
                    return {"state": store.load_state(run_dir).to_dict()}
                if method == "POST" and parts[2:] == ["resume"]:
                    return {"state": self.runner_for_body(body).resume(run_id).to_dict()}
                if method == "POST" and parts[2:] == ["rerun"]:
                    node_id = body.get("node_id")
                    if not isinstance(node_id, str):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Missing node_id.")
                    return {"state": self.runner_for_body(body).rerun_from(run_id, node_id).to_dict()}
                if method == "POST" and len(parts) == 5 and parts[2] == "nodes" and parts[4] == "run":
                    node_id = parts[3]
                    ensure_upstream = body.get("ensure_upstream", True)
                    if not isinstance(ensure_upstream, bool):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "ensure_upstream must be a boolean.")
                    return {
                        "state": self.runner_for_body(body).run_single_node(
                            run_id,
                            node_id,
                            ensure_upstream=ensure_upstream,
                        ).to_dict()
                    }
                if method == "POST" and parts[2:] == ["reviews"]:
                    return self.handle_review(run_id, run_dir, body)
                if method == "GET" and parts[2:] == ["changes"]:
                    return {"changes": store.list_change_requests(run_dir)}
                if len(parts) == 4 and parts[2] == "changes":
                    change_id = parts[3]
                    if method == "GET":
                        return {"change": store.load_change_request(run_dir, change_id)}
                if len(parts) == 5 and parts[2] == "changes" and parts[4] == "apply":
                    if method == "POST":
                        change = store.apply_change_request(run_dir, parts[3])
                        response: JsonDict = {"change": change}
                        if body.get("rerun"):
                            response["state"] = self.runner_for_body(body).rerun_from(
                                run_id,
                                str(change["node_id"]),
                            ).to_dict()
                        return response
                if method == "GET" and parts[2:] == ["revisions"]:
                    return {"revisions": store.list_revisions(run_dir)}
                if method == "POST" and parts[2:] == ["revisions"]:
                    message = body.get("message", "")
                    revision_id = store.create_revision(run_dir, str(message))
                    return {"revision_id": revision_id}
                if method == "GET" and parts[2:] == ["diff"]:
                    left = first_query(query, "left")
                    right = first_query(query, "right")
                    if not left:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Missing left revision.")
                    diff = (
                        store.diff_revisions(run_dir, left, right)
                        if right
                        else store.diff_revision_to_worktree(run_dir, left)
                    )
                    return {"diff": diff}
                if method == "POST" and parts[2:] == ["rollback"]:
                    revision_id = body.get("revision_id")
                    if not isinstance(revision_id, str):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Missing revision_id.")
                    store.rollback_revision(run_dir, revision_id)
                    return {"state": store.load_state(run_dir).to_dict()}
                if method == "GET" and len(parts) == 5 and parts[2] == "nodes" and parts[4] == "result":
                    node_id = parts[3]
                    result = store.read_node_result(run_dir, node_id)
                    if result is None:
                        state = store.load_state(run_dir)
                        node_state = state.nodes.get(node_id)
                        if node_state and node_state.result:
                            result = node_state.result
                        elif node_state and node_state.artifact:
                            from .execution_result import synthesize_from_artifact

                            result = synthesize_from_artifact(node_id, node_state.artifact, run_dir=run_dir)
                    if result is None:
                        raise ApiError(HTTPStatus.NOT_FOUND, f"No result for node: {node_id}")
                    return {"result": result.to_dict()}
                if method == "GET" and len(parts) == 5 and parts[2] == "nodes" and parts[4] == "assets":
                    node_id = parts[3]
                    return {"assets": store.list_node_assets(run_dir, node_id)}
                if method == "GET" and len(parts) == 5 and parts[2] == "nodes" and parts[4] == "session":
                    node_id = parts[3]
                    from .session import NodeSessionStore

                    sessions = NodeSessionStore(store)
                    session = sessions.load_session(run_dir, node_id)
                    if session is None:
                        raise ApiError(HTTPStatus.NOT_FOUND, f"No session for node: {node_id}")
                    turns = sessions.list_turns(run_dir, node_id)
                    return {
                        "session": session.to_dict(),
                        "current_turn": turns[-1].to_dict() if turns else None,
                    }
                if method == "GET" and len(parts) == 6 and parts[2] == "nodes" and parts[4] == "session" and parts[5] == "turns":
                    node_id = parts[3]
                    from .session import NodeSessionStore

                    sessions = NodeSessionStore(store)
                    return {"turns": [turn.to_dict() for turn in sessions.list_turns(run_dir, node_id)]}
                if method == "POST" and len(parts) == 5 and parts[2] == "nodes" and parts[4] == "iterate":
                    node_id = parts[3]
                    feedback = body.get("feedback", "")
                    if not isinstance(feedback, str) or not feedback.strip():
                        raise ApiError(HTTPStatus.BAD_REQUEST, "iterate requires feedback.")
                    return {
                        "state": self.runner_for_body(body).iterate_node(run_id, node_id, feedback.strip()).to_dict()
                    }
                if method == "POST" and len(parts) == 6 and parts[2] == "nodes" and parts[4] == "session" and parts[5] == "commit":
                    node_id = parts[3]
                    return {
                        "state": self.runner_for_body(body).commit_session(run_id, node_id).to_dict()
                    }
                if method == "POST" and len(parts) == 6 and parts[2] == "nodes" and parts[4] == "session" and parts[5] == "revert":
                    node_id = parts[3]
                    turn_raw = body.get("turn")
                    try:
                        turn = int(turn_raw)
                    except (TypeError, ValueError) as exc:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "revert requires integer turn.") from exc
                    if turn < 1:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "revert turn must be >= 1.")
                    return {
                        "state": self.runner_for_body(body).revert_session_turn(run_id, node_id, turn).to_dict()
                    }
                if method == "GET" and parts[2:] == ["artifacts"]:
                    artifacts_dir = run_dir / "artifacts"
                    refs: list[str] = []
                    if artifacts_dir.exists():
                        for path in sorted(artifacts_dir.rglob("*")):
                            if path.is_file():
                                refs.append(path.relative_to(run_dir).as_posix())
                    return {"artifacts": refs}
                if parts[2:] == ["artifact"]:
                    if method == "GET":
                        artifact_ref = first_query(query, "ref")
                        if not artifact_ref:
                            raise ApiError(HTTPStatus.BAD_REQUEST, "Missing artifact ref.")
                        return {"ref": artifact_ref, "content": store.read_artifact_ref(run_dir, artifact_ref)}
                    if method == "PUT":
                        artifact_ref = body.get("ref")
                        content = body.get("content")
                        if not isinstance(artifact_ref, str) or not artifact_ref.strip():
                            raise ApiError(HTTPStatus.BAD_REQUEST, "Missing artifact ref.")
                        if not isinstance(content, str):
                            raise ApiError(HTTPStatus.BAD_REQUEST, "Missing artifact content.")
                        try:
                            store.write_artifact_ref(run_dir, artifact_ref, content)
                        except ValueError as exc:
                            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
                        return {
                            "ref": artifact_ref,
                            "content": content,
                            "state": store.load_state(run_dir).to_dict(),
                        }
            raise ApiError(HTTPStatus.NOT_FOUND, "Route not found.")

        def resolve_workflow_path(self, body: JsonDict) -> Path:
            workflow = body.get("workflow")
            workflow_id = body.get("workflow_id")
            if isinstance(workflow, str) and workflow.strip():
                for base in (store.root, store.project_root):
                    candidate = (base / workflow).resolve()
                    if candidate.exists():
                        return candidate
                raise ApiError(HTTPStatus.BAD_REQUEST, f"Workflow not found: {workflow}")
            if isinstance(workflow_id, str) and workflow_id.strip():
                return find_workflow_path(store, workflow_id)
            raise ApiError(HTTPStatus.BAD_REQUEST, "Missing workflow path or workflow_id.")

        def runner_for_body(self, body: JsonDict) -> WorkflowRunner:
            requested = body.get("executor")
            agent_provider = body.get("agent_provider")
            if requested is None and agent_provider is None:
                return runner
            if requested is not None and not isinstance(requested, str):
                raise ApiError(HTTPStatus.BAD_REQUEST, "executor must be a string.")
            if agent_provider is not None and not isinstance(agent_provider, str):
                raise ApiError(HTTPStatus.BAD_REQUEST, "agent_provider must be a string.")
            executor_name = normalize_executor_name(requested or runner.executor_name)
            agent_ref = agent_provider if isinstance(agent_provider, str) and agent_provider.strip() else runner.agent_ref
            return WorkflowRunner(
                store,
                skill_dirs=runner.skill_dirs,
                executor_name=executor_name,
                agent_provider=agent_ref,
            )

        def handle_review(self, run_id: str, run_dir: Path, body: JsonDict) -> JsonDict:
            node_id = body.get("node_id")
            decision = body.get("decision")
            feedback = body.get("feedback", "")
            if not isinstance(node_id, str) or decision not in {"approve", "reject"}:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Review requires node_id and decision.")
            store.write_review(run_dir, node_id, str(decision), str(feedback))
            response: JsonDict = {"status": "recorded"}
            if decision == "reject":
                target_node = body.get("target_node") or node_id
                if not isinstance(target_node, str):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "target_node must be a string.")
                change_id = store.create_change_request(
                    run_dir,
                    target_node,
                    str(feedback),
                    source="review_reject",
                )
                response["change_id"] = change_id
                response["target_node"] = target_node
            return response

        def read_json_body(self) -> JsonDict:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length == 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            if not raw.strip():
                return {}
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ApiError(HTTPStatus.BAD_REQUEST, "JSON body must be an object.")
            return data

        def write_json(self, status: HTTPStatus, payload: JsonDict) -> None:
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
            self.end_headers()
            self.wfile.write(data)

    return ThreadingHTTPServer((host, port), AIWFHandler)


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


def first_query(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]

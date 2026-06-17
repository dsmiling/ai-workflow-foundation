from pathlib import Path

def trim_file(path: str, marker: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    idx = text.find(marker)
    if idx == -1:
        raise SystemExit(f"marker not found in {path}")
    file_path.write_text(text[:idx].rstrip() + "\n", encoding="utf-8")
    print(f"trimmed {path}")


trim_file("web/js/workflow/catalog.js", '\n$("workflowSelect").addEventListener')
trim_file("web/js/workflow/run.js", '\n$("artifactBtn").addEventListener')

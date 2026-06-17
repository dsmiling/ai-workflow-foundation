from pathlib import Path

html = Path("web/index.html").read_text(encoding="utf-8")
main_end = html.index("</main>") + len("</main>")
body = html[html.index("<body>") : main_end] + "\n  </body>"
head = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>AI Workflow Foundation</title>
    <link rel="stylesheet" href="/web/styles/tokens.css" />
    <link rel="stylesheet" href="/web/styles/base.css" />
    <link rel="stylesheet" href="/web/styles/layout.css" />
    <link rel="stylesheet" href="/web/styles/workflow.css" />
    <link rel="stylesheet" href="/web/styles/settings.css" />
  </head>
"""
new_html = head + body + '\n    <script type="module" src="/web/js/main.js"></script>\n</html>\n'
Path("web/index.html").write_text(new_html, encoding="utf-8")
print("index.html lines:", len(new_html.splitlines()))

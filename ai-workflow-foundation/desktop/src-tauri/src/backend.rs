use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use reqwest::blocking::Client;
use tauri::{AppHandle, Manager};

pub struct BackendState {
    pub child: Mutex<Option<Child>>,
    pub port: u16,
}

impl Drop for BackendState {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

pub fn resolve_workspace_root(app: &AppHandle, project_root: &Path) -> Result<PathBuf, String> {
    if cfg!(debug_assertions) {
        return Ok(project_root.to_path_buf());
    }

    app.path()
        .app_data_dir()
        .map(|path| path.join("workspace"))
        .map_err(|error| error.to_string())
}

pub fn resolve_project_root(app: &AppHandle) -> Result<PathBuf, String> {
    if cfg!(debug_assertions) {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        return manifest_dir
            .parent()
            .and_then(|desktop| desktop.parent())
            .map(Path::to_path_buf)
            .ok_or_else(|| "Failed to resolve development project root.".to_string());
    }

    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|error| error.to_string())?;
    Ok(resource_dir.join("app"))
}

pub fn start_backend(app: &AppHandle) -> Result<BackendState, String> {
    let project_root = resolve_project_root(app)?;
    let cli_path = project_root.join("aiwf_cli.py");
    if !cli_path.exists() {
        return Err(format!(
            "Backend entry not found: {}",
            cli_path.display()
        ));
    }

    let workspace_root = resolve_workspace_root(app, &project_root)?;
    std::fs::create_dir_all(&workspace_root)
        .map_err(|error| format!("Failed to create workspace directory: {error}"))?;

    let port = pick_port(8765)?;
    let python = resolve_python_command()?;
    let mut command = Command::new(python);
    command
        .current_dir(&project_root)
        .env("PYTHONPATH", project_root.join("src"))
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .arg("-B")
        .arg("aiwf_cli.py")
        .arg("--root")
        .arg(workspace_root.to_string_lossy().to_string())
        .arg("--project-root")
        .arg(project_root.to_string_lossy().to_string())
        .arg("serve")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string())
        .arg("--executor")
        .arg("skill")
        .stdout(Stdio::null())
        .stderr(if cfg!(debug_assertions) {
            Stdio::inherit()
        } else {
            Stdio::null()
        });

    let child = command
        .spawn()
        .map_err(|error| format!("Failed to start Python backend: {error}"))?;

    wait_for_health(port)?;
    Ok(BackendState {
        child: Mutex::new(Some(child)),
        port,
    })
}

fn resolve_python_command() -> Result<String, String> {
    for candidate in ["py", "python3", "python"] {
        let mut command = Command::new(candidate);
        command.arg("--version").stdout(Stdio::null()).stderr(Stdio::null());
        if command.status().is_ok() {
            return Ok(candidate.to_string());
        }
    }
    Err("Python 3 is required. Install Python 3.11+ and ensure `py` is available.".to_string())
}

fn pick_port(preferred: u16) -> Result<u16, String> {
    for port in preferred..preferred.saturating_add(20) {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return Ok(port);
        }
    }
    Err("No free localhost port found for AIWF backend.".to_string())
}

fn wait_for_health(port: u16) -> Result<(), String> {
    let client = Client::builder()
        .timeout(Duration::from_millis(800))
        .build()
        .map_err(|error| error.to_string())?;
    let url = format!("http://127.0.0.1:{port}/health");
    let deadline = Instant::now() + Duration::from_secs(30);

    while Instant::now() < deadline {
        if let Ok(response) = client.get(&url).send() {
            if response.status().is_success() {
                if let Ok(payload) = response.json::<serde_json::Value>() {
                    if payload.get("status").and_then(|value| value.as_str()) == Some("ok") {
                        return Ok(());
                    }
                }
            }
        }
        std::thread::sleep(Duration::from_millis(250));
    }

    Err(format!("Backend did not become healthy on port {port}."))
}

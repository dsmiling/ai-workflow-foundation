mod backend;

use backend::start_backend;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let backend = start_backend(app.handle())?;
            let url = format!("http://127.0.0.1:{}/", backend.port);
            let parsed = url
                .parse()
                .map_err(|error| format!("Invalid backend URL: {error}"))?;

            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(parsed))
                .title("AI Workflow Foundation")
                .inner_size(1440.0, 900.0)
                .min_inner_size(1100.0, 700.0)
                .resizable(true)
                .center()
                .build()?;

            app.manage(backend);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running AI Workflow Foundation");
}

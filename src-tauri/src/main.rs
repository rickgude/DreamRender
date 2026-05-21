#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    env,
    io::Write,
    net::TcpStream,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};

struct BackendProcess(Arc<Mutex<Option<Child>>>);

fn main() {
    let backend = BackendProcess(Arc::new(Mutex::new(None)));
    let backend_for_setup = backend.0.clone();
    let backend_for_exit = backend.0.clone();

    tauri::Builder::default()
        .setup(move |_app| {
            let child = start_python_backend().map_err(|error| error.to_string())?;
            *backend_for_setup.lock().map_err(|error| error.to_string())? = Some(child);
            wait_for_backend(Duration::from_secs(8));
            Ok(())
        })
        .on_window_event(move |_window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                stop_backend_services();
                if let Ok(mut guard) = backend_for_exit.lock() {
                    if let Some(child) = guard.as_mut() {
                        let _ = child.kill();
                    }
                    *guard = None;
                }
            }
        })
        .manage(backend)
        .run(tauri::generate_context!())
        .expect("error while running DreamRender");
}

fn start_python_backend() -> Result<Child, std::io::Error> {
    let repo_root = repo_root();
    let python = find_python(&repo_root).unwrap_or_else(|| "python".to_string());
    let mut command = Command::new(python);
    command
        .arg("-m")
        .arg("dreamrender")
        .arg("app-v2")
        .arg("--no-browser")
        .env("PYTHONPATH", repo_root.join("src"))
        .current_dir(repo_root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    command.spawn()
}

fn repo_root() -> PathBuf {
    env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|parent| parent.to_path_buf()))
        .and_then(|path| find_repo_from(path))
        .or_else(|| env::current_dir().ok().and_then(find_repo_from))
        .unwrap_or_else(|| env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
}

fn find_repo_from(mut path: PathBuf) -> Option<PathBuf> {
    loop {
        if path.join("src").join("dreamrender").exists() {
            return Some(path);
        }
        if !path.pop() {
            return None;
        }
    }
}

fn find_python(repo_root: &PathBuf) -> Option<String> {
    let local_pythonw = repo_root.join(".venv").join("Scripts").join("pythonw.exe");
    if local_pythonw.exists() {
        return Some(local_pythonw.to_string_lossy().to_string());
    }
    let local_python = repo_root.join(".venv").join("Scripts").join("python.exe");
    if local_python.exists() {
        return Some(local_python.to_string_lossy().to_string());
    }
    for candidate in [
        r"C:\Python314\pythonw.exe",
        r"C:\Python314\python.exe",
        "pythonw",
        "python",
    ] {
        if Command::new(candidate).arg("--version").stdout(Stdio::null()).stderr(Stdio::null()).status().is_ok() {
            return Some(candidate.to_string());
        }
    }
    None
}

fn wait_for_backend(timeout: Duration) {
    let started = Instant::now();
    while started.elapsed() < timeout {
        if std::net::TcpStream::connect("127.0.0.1:8777").is_ok() {
            return;
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn stop_backend_services() {
    if let Ok(mut stream) = TcpStream::connect("127.0.0.1:8777") {
        let body = r#"{"action":"stop"}"#;
        let request = format!(
            "POST /api/action HTTP/1.1\r\nHost: 127.0.0.1:8777\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            body.len(),
            body
        );
        let _ = stream.write_all(request.as_bytes());
    }
    thread::sleep(Duration::from_millis(250));
}

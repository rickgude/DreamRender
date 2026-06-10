#![windows_subsystem = "windows"]

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
use tauri::{Manager, Url};

struct BackendProcess(Arc<Mutex<Option<Child>>>);

impl Drop for BackendProcess {
    fn drop(&mut self) {
        stop_backend_process(&self.0);
    }
}

fn main() {
    let backend = BackendProcess(Arc::new(Mutex::new(None)));
    let backend_for_setup = backend.0.clone();
    let backend_for_exit = backend.0.clone();

    tauri::Builder::default()
        .setup(move |app| {
            let resource_dir = app.path().resource_dir().ok();
            stop_stale_backend();
            let child = start_python_backend(resource_dir.as_ref())
                .map_err(|error| error.to_string())?;
            *backend_for_setup
                .lock()
                .map_err(|error| error.to_string())? = Some(child);
            if wait_for_backend(Duration::from_secs(12)) {
                if let Some(window) = app.get_webview_window("main") {
                    let url =
                        Url::parse("http://127.0.0.1:8777").map_err(|error| error.to_string())?;
                    window.navigate(url).map_err(|error| error.to_string())?;
                }
            }
            Ok(())
        })
        .on_window_event(move |_window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                stop_backend_process(&backend_for_exit);
            }
        })
        .manage(backend)
        .run(tauri::generate_context!())
        .expect("error while running DreamRender");
}

fn start_python_backend(resource_dir: Option<&PathBuf>) -> Result<Child, std::io::Error> {
    if let Some(backend) = resource_dir
        .map(|path| path.join("dreamrender-backend.exe"))
        .filter(|path| path.exists())
    {
        let mut command = Command::new(backend);
        command
            .arg("--app-parent-pid")
            .arg(std::process::id().to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        return command.spawn();
    }

    let repo_root = repo_root(resource_dir);
    let python = find_python(&repo_root).unwrap_or_else(|| "python".to_string());
    let mut command = Command::new(python);
    command
        .arg("-m")
        .arg("dreamrender")
        .arg("app-v2")
        .arg("--no-browser")
        .arg("--parent-pid")
        .arg(std::process::id().to_string())
        .env("PYTHONPATH", repo_root.join("src"))
        .current_dir(repo_root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    command.spawn()
}

fn repo_root(resource_dir: Option<&PathBuf>) -> PathBuf {
    if let Some(path) = resource_dir.and_then(|path| find_repo_from(path.clone())) {
        return path;
    }
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
    for candidate in ["pythonw", "python"] {
        if Command::new(candidate)
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok()
        {
            return Some(candidate.to_string());
        }
    }
    None
}

fn wait_for_backend(timeout: Duration) -> bool {
    let started = Instant::now();
    while started.elapsed() < timeout {
        if backend_is_ready() {
            return true;
        }
        thread::sleep(Duration::from_millis(100));
    }
    false
}

fn backend_is_ready() -> bool {
    std::net::TcpStream::connect("127.0.0.1:8777").is_ok()
}

fn stop_backend_services() {
    if let Ok(mut stream) = TcpStream::connect("127.0.0.1:8777") {
        let body = r#"{"action":"shutdown"}"#;
        let request = format!(
            "POST /api/action HTTP/1.1\r\nHost: 127.0.0.1:8777\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            body.len(),
            body
        );
        let _ = stream.write_all(request.as_bytes());
    }
    thread::sleep(Duration::from_millis(250));
}


#[cfg(target_os = "windows")]
fn kill_backend_executables() {
    let _ = Command::new("taskkill")
        .args(["/IM", "dreamrender-backend.exe", "/T", "/F"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

#[cfg(not(target_os = "windows"))]
fn kill_backend_executables() {}

fn stop_stale_backend() {
    if backend_is_ready() {
        stop_backend_services();
        let started = Instant::now();
        while started.elapsed() < Duration::from_secs(5) && backend_is_ready() {
            thread::sleep(Duration::from_millis(100));
        }
        if backend_is_ready() {
            kill_backend_executables();
            thread::sleep(Duration::from_millis(500));
        }
    }
}

fn stop_backend_process(backend: &Arc<Mutex<Option<Child>>>) {
    stop_backend_services();
    if let Ok(mut guard) = backend.lock() {
        if let Some(child) = guard.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
        *guard = None;
    }
}

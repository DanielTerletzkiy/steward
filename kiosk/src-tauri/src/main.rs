//! Steward kitchen terminal: Steward's kiosk page full screen on a Raspberry Pi, with what a web page
//! can't do itself: pairing Bluetooth scanners and turning the screen off.
//!
//! The binary runs twice: a small supervisor (what the desktop starts) and, as its child, the app with
//! the window. The supervisor starts the app again when it crashes or is closed, and switches to a new
//! version after a package upgrade (the app exits with RESTART when it notices one).

mod bluetooth;
mod commands;
mod config;
mod screen;
mod steward;
mod window;

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::os::unix::io::AsRawFd;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
/// Exit code of the app that asks the supervisor to start the (possibly new) binary again.
pub const RESTART: i32 = 75;
const CHILD: &str = "STEWARD_KIOSK_CHILD";
const LOG_LIMIT: u64 = 1024 * 1024;

#[macro_export]
macro_rules! log {
    ($($arg:tt)*) => {
        eprintln!("{} {}", humantime::format_rfc3339_seconds(std::time::SystemTime::now()), format!($($arg)*))
    };
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.iter().any(|a| a == "--version" || a == "-V") {
        println!("steward-kiosk {VERSION}");
        return;
    }
    if args.iter().any(|a| a == "--help" || a == "-h") {
        println!(
            "steward-kiosk {VERSION}: Steward's kiosk page full screen.\n\n\
             Settings: {}\nLog: {}\n\n\
             --no-supervisor  run the window directly (no restart on crash or update)",
            config::dir().join("config.toml").display(),
            log_path().display()
        );
        return;
    }
    if std::env::var_os(CHILD).is_some() || args.iter().any(|a| a == "--no-supervisor") {
        window::run();
        return;
    }
    supervise();
}

pub fn log_path() -> PathBuf {
    let state =
        std::env::var_os("XDG_STATE_HOME").map(PathBuf::from).unwrap_or_else(|| config::home().join(".local/state"));
    state.join("steward-kiosk/kiosk.log")
}

/// Keep the log small: the old half goes to kiosk.log.1.
pub fn rotate_log(path: &Path) {
    if fs::metadata(path).map(|m| m.len() > LOG_LIMIT).unwrap_or(false) {
        let _ = fs::copy(path, path.with_extension("log.1"));
        // Truncate in place: the app keeps writing to the same (appending) file.
        let _ = OpenOptions::new().write(true).open(path).and_then(|f| f.set_len(0));
    }
}

fn open_log() -> Option<File> {
    let path = log_path();
    fs::create_dir_all(path.parent()?).ok()?;
    rotate_log(&path);
    OpenOptions::new().create(true).append(true).open(&path).ok()
}

/// Only one kiosk per desktop session: a second start (e.g. from the menu) just ends.
fn single_instance() -> Option<File> {
    let dir = std::env::var_os("XDG_RUNTIME_DIR").map(PathBuf::from).unwrap_or_else(std::env::temp_dir);
    let file = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(dir.join(format!("steward-kiosk-{}.lock", unsafe { libc::getuid() })))
        .ok()?;
    let locked = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0;
    locked.then_some(file)
}

fn supervise() {
    let Some(_lock) = single_instance() else {
        eprintln!("steward-kiosk is already running");
        return;
    };
    // The installed path, so that a restart after an upgrade starts the new binary.
    let exe = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("/usr/bin/steward-kiosk"));
    let log = open_log();
    if let Some(log) = &log {
        if let Ok(fd) = log.try_clone() {
            // Our own messages go to the log too.
            unsafe { libc::dup2(fd.as_raw_fd(), 2) };
        }
    }
    log!("steward-kiosk {VERSION} starting");

    let stop = Arc::new(AtomicBool::new(false));
    for signal in [signal_hook::consts::SIGTERM, signal_hook::consts::SIGINT, signal_hook::consts::SIGHUP] {
        let _ = signal_hook::flag::register(signal, Arc::clone(&stop));
    }

    let mut crashes: Vec<Instant> = Vec::new();
    loop {
        let output = || log.as_ref().and_then(|f| f.try_clone().ok()).map(Stdio::from).unwrap_or_else(Stdio::inherit);
        let mut child = match Command::new(&exe).env(CHILD, "1").stdout(output()).stderr(output()).spawn() {
            Ok(child) => child,
            Err(err) => {
                log!("can't start the app: {err}");
                std::thread::sleep(Duration::from_secs(10));
                continue;
            }
        };
        let status = loop {
            if stop.load(Ordering::Relaxed) {
                unsafe { libc::kill(child.id() as i32, libc::SIGTERM) };
                let end = Instant::now() + Duration::from_secs(3);
                while Instant::now() < end && matches!(child.try_wait(), Ok(None)) {
                    std::thread::sleep(Duration::from_millis(100));
                }
                let _ = child.kill();
                log!("stopped");
                return;
            }
            match child.try_wait() {
                Ok(Some(status)) => break status,
                Ok(None) => std::thread::sleep(Duration::from_millis(200)),
                Err(_) => break std::process::ExitStatus::default(),
            }
        };
        if status.code() == Some(RESTART) {
            log!("starting again");
            let _ = std::io::stderr().flush();
            // Replaces this process; only returns if that failed.
            let err = Command::new(&exe).exec();
            log!("can't start {}: {err}", exe.display());
            continue;
        }
        // A kiosk is never closed for good: start it again, slower if it keeps failing.
        log!("the app ended ({status}); starting it again");
        let now = Instant::now();
        crashes.retain(|t| now.duration_since(*t) < Duration::from_secs(60));
        crashes.push(now);
        std::thread::sleep(Duration::from_secs(if crashes.len() > 5 { 30 } else { 2 }));
    }
}

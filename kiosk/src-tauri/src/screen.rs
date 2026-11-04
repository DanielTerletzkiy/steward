//! Turning the display off and on: wlopm on a Wayland desktop (labwc, Raspberry Pi OS's default),
//! xset on X11. The kiosk page says when it is idle; the app then switches the display off, and on
//! again at the next key press, scan or touch.

use std::path::PathBuf;
use std::process::Command;
use std::sync::Mutex;

pub struct Screen {
    off: Mutex<bool>,
}

enum Tool {
    Wayland(PathBuf),
    X11(PathBuf),
}

fn find(program: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path).map(|dir| dir.join(program)).find(|p| p.is_file())
}

fn tool() -> Option<Tool> {
    if std::env::var_os("WAYLAND_DISPLAY").is_some() {
        find("wlopm").map(Tool::Wayland)
    } else if std::env::var_os("DISPLAY").is_some() {
        find("xset").map(Tool::X11)
    } else {
        None
    }
}

fn run(program: &PathBuf, args: &[&str]) {
    match Command::new(program).args(args).output() {
        Ok(out) if out.status.success() => {}
        Ok(out) => {
            crate::log!("{} {}: {}", program.display(), args.join(" "), String::from_utf8_lossy(&out.stderr).trim())
        }
        Err(err) => crate::log!("{}: {err}", program.display()),
    }
}

impl Screen {
    pub fn new() -> Self {
        // On X11 the desktop's own screen saver would blank the screen in the middle of a recipe;
        // the kiosk decides instead. (On labwc the kiosk session starts no swayidle.)
        if let Some(Tool::X11(xset)) = tool() {
            run(&xset, &["s", "off"]);
            run(&xset, &["+dpms"]);
            run(&xset, &["dpms", "0", "0", "0"]);
        }
        Screen { off: Mutex::new(false) }
    }

    /// Whether this desktop lets the app switch the display.
    pub fn available() -> bool {
        tool().is_some()
    }

    pub fn set_on(&self, on: bool) {
        let mut off = self.off.lock().unwrap();
        if *off == !on {
            return;
        }
        match tool() {
            Some(Tool::Wayland(wlopm)) => run(&wlopm, &[if on { "--on" } else { "--off" }, "*"]),
            Some(Tool::X11(xset)) => run(&xset, &["dpms", "force", if on { "on" } else { "off" }]),
            None => return,
        }
        *off = !on;
        crate::log!("screen {}", if on { "on" } else { "off" });
    }
}

//! Settings in ~/.config/steward-kiosk: config.toml (written by the setup screen or by Ansible) and
//! key, the terminal's key from pairing (only readable by the user). 0.4.0's setup script kept the
//! address in a file named url; that is taken over once.

use std::fs;
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

use crate::steward;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Config {
    /// Steward's address as this device reaches it, e.g. http://homeassistant.local:8095
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
    /// Turn the screen off when the kiosk page goes dark.
    #[serde(default = "yes")]
    pub screen_off: bool,
    /// Page zoom, e.g. 1.25 on a small screen with a high resolution.
    #[serde(default = "one")]
    pub zoom: f64,
    /// Set by Ansible: the setup screen then says that its changes are overwritten on the next run.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub managed_by: Option<String>,
}

fn yes() -> bool {
    true
}

fn one() -> f64 {
    1.0
}

impl Default for Config {
    fn default() -> Self {
        Config { url: None, screen_off: true, zoom: 1.0, managed_by: None }
    }
}

impl Config {
    /// Steward's address without anything after it (no /#/kiosk), or None before the setup.
    pub fn origin(&self) -> Option<String> {
        self.url.as_deref().map(steward::origin).filter(|o| !o.is_empty())
    }

    pub fn zoom(&self) -> f64 {
        if self.zoom.is_finite() {
            self.zoom.clamp(0.5, 3.0)
        } else {
            1.0
        }
    }
}

pub fn home() -> PathBuf {
    std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("/tmp"))
}

pub fn dir() -> PathBuf {
    if let Some(dir) = std::env::var_os("STEWARD_KIOSK_CONFIG") {
        return PathBuf::from(dir);
    }
    let base = std::env::var_os("XDG_CONFIG_HOME").map(PathBuf::from).unwrap_or_else(|| home().join(".config"));
    base.join("steward-kiosk")
}

fn config_path() -> PathBuf {
    dir().join("config.toml")
}

fn key_path() -> PathBuf {
    dir().join("key")
}

/// The settings, or the defaults when there are none yet (or they can't be read: the log says why).
pub fn load() -> Config {
    let path = config_path();
    match fs::read_to_string(&path) {
        Ok(text) => toml::from_str(&text).unwrap_or_else(|err| {
            crate::log!("{} can't be read, using the defaults: {err}", path.display());
            Config::default()
        }),
        Err(_) => migrate().unwrap_or_default(),
    }
}

/// 0.4.0's setup script: the kiosk address in ~/.config/steward-kiosk/url.
fn migrate() -> Option<Config> {
    let old = dir().join("url");
    let url = fs::read_to_string(&old).ok()?;
    let config = Config { url: Some(steward::origin(url.trim())), ..Config::default() };
    if save(&config).is_ok() {
        let _ = fs::remove_file(&old);
        crate::log!("took over the address from {}", old.display());
    }
    Some(config)
}

pub fn save(config: &Config) -> std::io::Result<()> {
    fs::create_dir_all(dir())?;
    let body = toml::to_string(config).map_err(std::io::Error::other)?;
    let text = format!(
        "# Steward kitchen terminal (steward-kiosk). Changes apply within a few seconds.\n\
         # url: Steward's address; screen_off: screen off when the kiosk page goes dark; zoom: page zoom.\n{body}"
    );
    write_atomic(&config_path(), text.as_bytes(), 0o644)
}

pub fn load_key() -> Option<String> {
    fs::read_to_string(key_path()).ok().map(|k| k.trim().to_string()).filter(|k| !k.is_empty())
}

pub fn save_key(key: &str) -> std::io::Result<()> {
    fs::create_dir_all(dir())?;
    write_atomic(&key_path(), format!("{key}\n").as_bytes(), 0o600)
}

pub fn forget_key() {
    let _ = fs::remove_file(key_path());
}

/// Write to a temporary file and rename it, so the app never reads half a file.
fn write_atomic(path: &PathBuf, data: &[u8], mode: u32) -> std::io::Result<()> {
    let tmp = path.with_extension("tmp");
    let mut file = fs::OpenOptions::new().create(true).truncate(true).write(true).mode(mode).open(&tmp)?;
    file.write_all(data)?;
    file.sync_all()?;
    fs::rename(&tmp, path)
}

// --- starting with the desktop (for installations without Ansible) ----------------------------

fn autostart_path() -> PathBuf {
    let base = std::env::var_os("XDG_CONFIG_HOME").map(PathBuf::from).unwrap_or_else(|| home().join(".config"));
    base.join("autostart/steward-kiosk.desktop")
}

pub fn autostart() -> bool {
    autostart_path().exists()
}

pub fn set_autostart(on: bool) -> std::io::Result<()> {
    let path = autostart_path();
    if !on {
        return match fs::remove_file(&path) {
            Err(err) if err.kind() != std::io::ErrorKind::NotFound => Err(err),
            _ => Ok(()),
        };
    }
    fs::create_dir_all(path.parent().expect("autostart dir"))?;
    write_atomic(
        &path,
        b"[Desktop Entry]\nType=Application\nName=Steward Kiosk\nExec=steward-kiosk\nX-GNOME-Autostart-enabled=true\n",
        0o644,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_partial_settings() {
        let config: Config = toml::from_str("url = \"http://pi:8095\"").unwrap();
        assert_eq!(config.url.as_deref(), Some("http://pi:8095"));
        assert!(config.screen_off);
        assert_eq!(config.zoom, 1.0);
    }

    #[test]
    fn zoom_stays_sensible() {
        let config = Config { zoom: 20.0, ..Config::default() };
        assert_eq!(config.zoom(), 3.0);
    }
}

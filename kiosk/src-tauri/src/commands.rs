//! What the app's setup screen and Steward's kiosk page can ask the app (see build.rs for who may call
//! which). Errors the screens show are codes they translate.

use serde::Serialize;
use tauri::{AppHandle, State, Url};

use crate::bluetooth::{self, Device, Failure, Status};
use crate::config;
use crate::screen::Screen;
use crate::window::{self, Kiosk, Phase};
use crate::{log, steward, VERSION};

pub fn handler() -> impl Fn(tauri::ipc::Invoke) -> bool + Send + Sync + 'static {
    tauri::generate_handler![
        setup_state,
        save_setup,
        leave_setup,
        open_setup,
        kiosk_info,
        remember_key,
        forget_key,
        set_screen,
        bt_status,
        bt_scan,
        bt_pair,
        bt_remove
    ]
}

// --- the setup and waiting screens ---------------------------------------------------------

#[derive(Serialize)]
pub struct SetupState {
    version: &'static str,
    url: Option<String>,
    paired: bool,
    autostart: bool,
    managed: bool,
    waiting: bool,
    problem: Option<String>,
}

#[tauri::command]
fn setup_state(state: State<'_, Kiosk>) -> SetupState {
    let config = state.config.lock().unwrap();
    SetupState {
        version: VERSION,
        url: config.origin(),
        paired: state.key.lock().unwrap().is_some(),
        autostart: config::autostart(),
        managed: config.managed_by.is_some(),
        waiting: *state.phase.lock().unwrap() == Phase::Waiting,
        problem: state.problem.lock().unwrap().clone(),
    }
}

/// Save the address (and pair with the code, if given), then start again with it.
/// Errors: "address", "unreachable: …", "code", or a message.
#[tauri::command]
async fn save_setup(url: String, code: Option<String>, autostart: Option<bool>) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let origin = steward::origin(&url);
        if Url::parse(&origin).map(|u| u.host_str().is_none()).unwrap_or(true) {
            return Err("address".to_string());
        }
        steward::reachable(&origin).map_err(|problem| format!("unreachable: {problem}"))?;
        let mut config = config::load();
        let moved = config.origin().as_deref() != Some(origin.as_str());
        let key = match code.as_deref().map(str::trim).filter(|c| !c.is_empty()) {
            Some(code) => Some(steward::redeem(&origin, code)?),
            None => None,
        };
        config.url = Some(origin.clone());
        config::save(&config).map_err(|err| err.to_string())?;
        match key {
            Some(key) => config::save_key(&key).map_err(|err| err.to_string())?,
            // A key from another Steward is no use here.
            None if moved => config::forget_key(),
            None => {}
        }
        if let Some(on) = autostart {
            config::set_autostart(on).map_err(|err| err.to_string())?;
        }
        log!("set up for {origin}");
        window::restart_soon();
        Ok(())
    })
    .await
    .map_err(|err| err.to_string())?
}

/// Back from the setup screen without changes.
#[tauri::command]
fn leave_setup(app: AppHandle) {
    window::connect(&app);
}

#[tauri::command]
fn open_setup(app: AppHandle) {
    window::show_setup(&app);
}

// --- Steward's kiosk page ---------------------------------------------------------------

#[derive(Serialize)]
pub struct KioskInfo {
    version: &'static str,
    bluetooth: bool,
    screen: bool,
}

#[tauri::command]
async fn kiosk_info(state: State<'_, Kiosk>) -> Result<KioskInfo, ()> {
    let screen = state.config.lock().unwrap().screen_off && Screen::available();
    Ok(KioskInfo { version: VERSION, bluetooth: bluetooth::available().await, screen })
}

/// The page paired itself (the code typed on its pairing screen): keep the key for the next start.
#[tauri::command]
fn remember_key(state: State<'_, Kiosk>, key: String) -> Result<(), String> {
    let key = key.trim().to_string();
    let mut current = state.key.lock().unwrap();
    if current.as_deref() != Some(key.as_str()) {
        config::save_key(&key).map_err(|err| err.to_string())?;
        *current = Some(key);
        log!("kept the terminal's new key");
    }
    Ok(())
}

/// Steward says this terminal was removed: the page shows its pairing screen.
#[tauri::command]
fn forget_key(state: State<'_, Kiosk>) {
    let mut current = state.key.lock().unwrap();
    if current.take().is_some() {
        config::forget_key();
        log!("the terminal was removed in Steward; forgot its key");
    }
}

/// The page went dark (idle) or someone is using it again.
#[tauri::command]
fn set_screen(state: State<'_, Kiosk>, idle: bool) {
    if state.config.lock().unwrap().screen_off || !idle {
        state.screen.set_on(!idle);
    }
}

#[tauri::command]
async fn bt_status() -> Result<Status, Failure> {
    bluetooth::status().await
}

#[tauri::command]
async fn bt_scan(seconds: Option<u64>) -> Result<Vec<Device>, Failure> {
    bluetooth::scan(seconds.unwrap_or(12)).await
}

#[tauri::command]
async fn bt_pair(address: String) -> Result<Device, Failure> {
    let device = bluetooth::pair(&address).await;
    match &device {
        Ok(d) => log!("paired {} ({})", d.name.as_deref().unwrap_or("?"), d.address),
        Err(f) => log!("pairing {address} failed: {} {}", f.code, f.detail),
    }
    device
}

#[tauri::command]
async fn bt_remove(address: String) -> Result<(), Failure> {
    bluetooth::remove(&address).await
}

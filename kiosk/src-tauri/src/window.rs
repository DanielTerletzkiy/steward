//! The window: Steward's kiosk page full screen, or the app's own setup and waiting screens (ui/).
//! Only Steward's address may be shown, and only it may call the app's commands (see build.rs).

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use tauri::ipc::CapabilityBuilder;
use tauri::{AppHandle, Manager, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

use crate::config::{self, Config};
use crate::screen::Screen;
use crate::{commands, log, steward, RESTART};

/// What Steward's kiosk page may ask the app.
const PAGE_COMMANDS: &[&str] = &[
    "kiosk_info",
    "remember_key",
    "forget_key",
    "set_screen",
    "open_setup",
    "bt_status",
    "bt_scan",
    "bt_pair",
    "bt_remove",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Phase {
    Starting,
    Setup,
    Waiting,
    Kiosk,
}

pub struct Kiosk {
    pub config: Mutex<Config>,
    pub key: Mutex<Option<String>>,
    pub screen: Screen,
    pub phase: Mutex<Phase>,
    /// Why Steward can't be reached, for the waiting screen.
    pub problem: Mutex<Option<String>>,
    /// Each connect() counts up, so an older attempt still running gives up.
    attempt: AtomicU64,
}

pub fn run() {
    let config = config::load();
    let key = config::load_key();
    log!("app {} for {}", crate::VERSION, config.origin().as_deref().unwrap_or("(not set up yet)"));
    tauri::Builder::default()
        .manage(Kiosk {
            config: Mutex::new(config),
            key: Mutex::new(key),
            screen: Screen::new(),
            phase: Mutex::new(Phase::Starting),
            problem: Mutex::new(None),
            attempt: AtomicU64::new(0),
        })
        .invoke_handler(commands::handler())
        .setup(|app| {
            open(app.handle())?;
            watch(app.handle().clone());
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("the window couldn't be opened");
}

fn local(page: &str) -> Url {
    Url::parse(&format!("tauri://localhost/index.html#{page}")).expect("local page")
}

fn kiosk_url(origin: &str, key: Option<&str>) -> Url {
    let url = match key {
        // The key goes in the fragment, which never reaches a server; the page signs in with it
        // whenever it has no cookie.
        Some(key) => format!("{origin}/#/kiosk?key={key}"),
        None => format!("{origin}/#/kiosk"),
    };
    Url::parse(&url).unwrap_or_else(|_| local("setup"))
}

fn same_origin(url: &Url, origin: &str) -> bool {
    Url::parse(origin).map(|o| o.origin() == url.origin()).unwrap_or(false)
}

fn window(app: &AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window("main")
}

fn open(app: &AppHandle) -> tauri::Result<()> {
    let state = app.state::<Kiosk>();
    let (origin, zoom) = {
        let config = state.config.lock().unwrap();
        (config.origin(), config.zoom())
    };
    if let Some(origin) = &origin {
        let mut capability =
            CapabilityBuilder::new("steward").remote(format!("{origin}/*")).window("main").local(false);
        for command in PAGE_COMMANDS {
            capability = capability.permission(format!("allow-{}", command.replace('_', "-")));
        }
        app.add_capability(capability)?;
    }

    let allowed = origin.clone();
    let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
        .title("Steward")
        .fullscreen(true)
        .decorations(false)
        .focused(true)
        .zoom_hotkeys_enabled(false)
        // Nothing but Steward and the app's own screens: a link elsewhere would strand the kiosk.
        .on_navigation(move |url| {
            let ok = url.scheme() == "tauri"
                || url.host_str() == Some("tauri.localhost")
                || allowed.as_deref().is_some_and(|o| same_origin(url, o));
            if !ok {
                log!("blocked a link to {url}");
            }
            ok
        })
        .build()?;
    // Without a window manager (a bare X server) "full screen" does nothing: cover the screen anyway.
    let monitor = app.primary_monitor().ok().flatten().or_else(|| app.available_monitors().ok()?.into_iter().next());
    if let Some(monitor) = monitor {
        let _ = window.set_position(*monitor.position());
        let _ = window.set_size(*monitor.size());
    }
    let _ = window.set_zoom(zoom);
    #[cfg(target_os = "linux")]
    configure_webview(app, &window, origin.clone());
    connect(app);
    Ok(())
}

/// WebKitGTK settings a web page can't get by itself: the camera for Steward (WebKit only allows it on
/// secure pages, and a Pi reaches Steward over http://), no right-click menu, recovery after crashes.
#[cfg(target_os = "linux")]
fn configure_webview(app: &AppHandle, window: &WebviewWindow, origin: Option<String>) {
    use glib::Cast;
    use gtk::prelude::WidgetExt;
    use webkit2gtk::{
        NetworkError, PermissionRequestExt, PolicyError, SecurityManagerExt, SettingsExt, UserMediaPermissionRequest,
        WebContextExt, WebViewExt,
    };

    let app = app.clone();
    let _ = window.with_webview(move |webview| {
        let view = webview.inner();
        if let Some(settings) = WebViewExt::settings(&view) {
            settings.set_enable_media_stream(true);
            settings.set_media_playback_requires_user_gesture(false);
            // For tests without a camera: WebKit's own test picture.
            settings.set_enable_mock_capture_devices(std::env::var_os("STEWARD_KIOSK_MOCK_CAMERA").is_some());
            // For finding out what goes wrong on the page: its console in the log, and the inspector.
            if std::env::var_os("STEWARD_KIOSK_DEBUG").is_some() {
                settings.set_enable_write_console_messages_to_stdout(true);
                settings.set_enable_developer_extras(true);
            }
        }
        if let Some(security) = view.context().and_then(|c| c.security_manager()) {
            // Navigation is limited to Steward's address (above), so this only makes Steward's page
            // a secure context.
            security.register_uri_scheme_as_secure("http");
        }

        let camera_origin = origin.clone();
        view.connect_permission_request(move |view, request| {
            let on_steward = match (view.uri(), &camera_origin) {
                (Some(uri), Some(origin)) => Url::parse(&uri).map(|u| same_origin(&u, origin)).unwrap_or(false),
                _ => false,
            };
            if request.dynamic_cast_ref::<UserMediaPermissionRequest>().is_some() {
                if on_steward {
                    request.allow();
                } else {
                    request.deny();
                }
                return true;
            }
            false
        });

        view.connect_context_menu(|_, _, _, _| true);

        let crashed = app.clone();
        view.connect_web_process_terminated(move |view, reason| {
            log!("the page's process ended ({reason:?}); loading it again");
            if *crashed.state::<Kiosk>().phase.lock().unwrap() == Phase::Kiosk {
                view.reload();
            } else {
                connect(&crashed);
            }
        });

        let failed = app.clone();
        view.connect_load_failed(move |_, _, uri, error| {
            // Leaving a page half-loaded (or a blocked link) isn't a failure.
            if error.kind::<NetworkError>() == Some(NetworkError::Cancelled)
                || error.kind::<PolicyError>() == Some(PolicyError::FrameLoadInterruptedByPolicyChange)
                || uri.starts_with("tauri:")
            {
                return false;
            }
            log!("couldn't load {}: {error}", uri.split('#').next().unwrap_or(uri));
            connect(&failed);
            true
        });

        view.grab_focus();
    });
}

pub fn set_phase(app: &AppHandle, phase: Phase) {
    *app.state::<Kiosk>().phase.lock().unwrap() = phase;
}

fn navigate(app: &AppHandle, url: Url) {
    if let Some(window) = window(app) {
        if let Err(err) = window.navigate(url) {
            log!("navigation failed: {err}");
        }
    }
}

pub fn show_setup(app: &AppHandle) {
    app.state::<Kiosk>().attempt.fetch_add(1, Ordering::SeqCst);
    set_phase(app, Phase::Setup);
    navigate(app, local("setup"));
}

/// Open Steward's kiosk page as soon as Steward answers; until then the waiting screen says why not.
pub fn connect(app: &AppHandle) {
    let state = app.state::<Kiosk>();
    let attempt = state.attempt.fetch_add(1, Ordering::SeqCst) + 1;
    let Some(origin) = state.config.lock().unwrap().origin() else {
        show_setup(app);
        return;
    };
    let app = app.clone();
    std::thread::spawn(move || {
        let state = app.state::<Kiosk>();
        let mut waiting = false;
        loop {
            if state.attempt.load(Ordering::SeqCst) != attempt {
                return;
            }
            match steward::reachable(&origin) {
                Ok(()) => {
                    if state.attempt.load(Ordering::SeqCst) != attempt {
                        return;
                    }
                    *state.problem.lock().unwrap() = None;
                    set_phase(&app, Phase::Kiosk);
                    let key = state.key.lock().unwrap().clone();
                    navigate(&app, kiosk_url(&origin, key.as_deref()));
                    state.screen.set_on(true);
                    if waiting {
                        log!("Steward answers again");
                    }
                    return;
                }
                Err(problem) => {
                    if !waiting {
                        log!("waiting for Steward at {origin}: {problem}");
                        waiting = true;
                        set_phase(&app, Phase::Waiting);
                        navigate(&app, local("wait"));
                        state.screen.set_on(true);
                    }
                    *state.problem.lock().unwrap() = Some(problem);
                    std::thread::sleep(Duration::from_secs(3));
                }
            }
        }
    });
}

/// Restart (through the supervisor) soon, after the current command has answered.
pub fn restart_soon() {
    std::thread::spawn(|| {
        std::thread::sleep(Duration::from_millis(400));
        std::process::exit(RESTART);
    });
}

/// Every two seconds: settings changed (by Ansible, or by hand)? A new version installed?
fn watch(app: AppHandle) {
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_secs(2));
        crate::rotate_log(&crate::log_path());
        if std::fs::read_link("/proc/self/exe").is_ok_and(|exe| exe.to_string_lossy().ends_with(" (deleted)")) {
            log!("a new version was installed; switching to it");
            std::process::exit(RESTART);
        }
        let state = app.state::<Kiosk>();
        let fresh = config::load();
        let key = config::load_key();
        {
            let mut config = state.config.lock().unwrap();
            if fresh.origin() != config.origin() {
                log!("Steward's address changed to {}", fresh.origin().as_deref().unwrap_or("nothing"));
                std::process::exit(RESTART);
            }
            if fresh.zoom() != config.zoom() {
                if let Some(window) = window(&app) {
                    let _ = window.set_zoom(fresh.zoom());
                }
            }
            if !fresh.screen_off && config.screen_off {
                state.screen.set_on(true);
            }
            *config = fresh;
        }
        let changed = {
            let mut current = state.key.lock().unwrap();
            let changed = *current != key;
            *current = key;
            changed
        };
        if changed && *state.phase.lock().unwrap() != Phase::Setup {
            log!("the terminal's key changed; signing in again");
            connect(&app);
        }
    });
}

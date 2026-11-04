fn main() {
    // The app's own commands get permissions (allow-<command>), so capabilities decide which page may
    // call which: the setup screen its two, Steward's kiosk page the rest (see window.rs).
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(tauri_build::AppManifest::new().commands(&[
        "setup_state",
        "save_setup",
        "leave_setup",
        "kiosk_info",
        "remember_key",
        "forget_key",
        "set_screen",
        "open_setup",
        "bt_status",
        "bt_scan",
        "bt_pair",
        "bt_remove",
    ])))
    .expect("failed to run tauri-build");
}

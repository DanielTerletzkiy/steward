// The Steward Kiosk app (kiosk/ in this repository) shows the kiosk page on the Raspberry Pi and lets it
// do what a web page can't: pair Bluetooth scanners, switch the screen off and keep the terminal's key
// on the device. In any other browser the kiosk page works without these.

interface TauriInternals {
  invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T>
}

const internals = (window as unknown as { __TAURI_INTERNALS__?: TauriInternals }).__TAURI_INTERNALS__

export const inApp = !!internals

/** Ask the app; rejects with what the command returned as its error. */
export function appCall<T = void>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  if (!internals) return Promise.reject(new Error('Not in the Steward Kiosk app'))
  return internals.invoke<T>(cmd, args)
}

export interface AppInfo {
  version: string
  bluetooth: boolean
  screen: boolean
}

/** A failed Bluetooth command: code is one of no_adapter, blocked, not_found, pair_failed, busy, failed. */
export interface AppFailure {
  code: string
  detail: string
}

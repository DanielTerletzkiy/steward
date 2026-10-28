// Sign-in: a 401 from the API or the WebSocket sends the browser to the server's sign-in page.
// A loop guard stops repeated redirects; the app shows an error state instead.
import { reactive } from 'vue'

const GUARD_KEY = 'steward.loginRedirectAt'
const GUARD_MS = 15000

export const auth = reactive({
  /** Set when sign-in is needed but redirecting again would loop. */
  failed: false,
})

export function loginUrl(): string {
  const next = window.location.hash && window.location.hash.startsWith('#/') ? window.location.hash : '#/'
  return `auth/login?next=${encodeURIComponent(next)}`
}

function lastRedirect(): number {
  try {
    return Number(window.sessionStorage.getItem(GUARD_KEY)) || 0
  } catch {
    return 0
  }
}

/** Go to the sign-in page, unless we just came back from it (then show the error state). */
export function requireLogin(): void {
  if (auth.failed) return
  if (Date.now() - lastRedirect() < GUARD_MS) {
    auth.failed = true
    return
  }
  try {
    window.sessionStorage.setItem(GUARD_KEY, String(Date.now()))
  } catch {
    // Without storage there is no loop guard across reloads; a failed sign-in shows HA's own error page.
  }
  window.location.href = loginUrl()
}

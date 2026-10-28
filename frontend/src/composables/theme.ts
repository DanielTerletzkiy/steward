// Light/dark from prefers-color-scheme. Inside a same-origin Home Assistant page, borrow HA's colors.
import type { ThemeInstance } from 'vuetify'

let ctx: CanvasRenderingContext2D | null = null

/** Normalise any CSS color to #rrggbb (Vuetify needs hex). Returns null for unknown/transparent values. */
function toHex(value: string): string | null {
  const v = value.trim()
  if (!v) return null
  ctx ??= document.createElement('canvas').getContext('2d')
  if (!ctx) return null
  ctx.fillStyle = '#010203'
  ctx.fillStyle = v
  const out = String(ctx.fillStyle)
  if (out === '#010203' && v.toLowerCase() !== '#010203') return null
  if (out.startsWith('#')) return out
  const m = out.match(/rgba?\(([^)]+)\)/)
  if (!m) return null
  const [r, g, b, a] = m[1].split(',').map((s) => parseFloat(s))
  if (a !== undefined && a < 0.5) return null
  return '#' + [r, g, b].map((n) => Math.round(n).toString(16).padStart(2, '0')).join('')
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function parentRoot(): HTMLElement | null {
  try {
    if (window.parent === window) return null
    const doc = window.parent.document // throws for cross-origin parents
    return doc?.documentElement ?? null
  } catch {
    return null
  }
}

const DEFAULTS = {
  light: {} as Record<string, string>,
  dark: {} as Record<string, string>,
}

function applyHa(theme: ThemeInstance, root: HTMLElement): boolean {
  let style: CSSStyleDeclaration
  try {
    style = window.parent.getComputedStyle(root)
  } catch {
    return false
  }
  const read = (...names: string[]) => {
    for (const n of names) {
      const hex = toHex(style.getPropertyValue(n))
      if (hex) return hex
    }
    return null
  }
  const primary = read('--primary-color')
  if (!primary) return false
  const background = read('--primary-background-color')
  const surface = read('--card-background-color', '--ha-card-background', '--secondary-background-color')
  const accent = read('--accent-color')
  const errorColor = read('--error-color')
  const warning = read('--warning-color')
  const success = read('--success-color')
  const dark = background ? luminance(background) < 0.4 : matchMedia('(prefers-color-scheme: dark)').matches
  const name = dark ? 'dark' : 'light'
  const colors = theme.themes.value[name].colors
  const set = (key: string, value: string | null) => {
    if (value) colors[key] = value
    else if (DEFAULTS[name][key]) colors[key] = DEFAULTS[name][key]
  }
  set('primary', primary)
  set('secondary', accent)
  set('background', background)
  set('surface', surface)
  set('error', errorColor)
  set('warning', warning)
  set('success', success)
  theme.change(name)
  return true
}

export function initTheme(theme: ThemeInstance) {
  for (const name of ['light', 'dark'] as const) DEFAULTS[name] = { ...theme.themes.value[name].colors }
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const root = parentRoot()

  const sync = () => {
    if (root && applyHa(theme, root)) return
    theme.change(media.matches ? 'dark' : 'light')
  }
  sync()
  media.addEventListener?.('change', sync)

  if (root) {
    // HA swaps themes by rewriting inline styles on <html>; follow along.
    try {
      const Observer = (window.parent as typeof window).MutationObserver ?? MutationObserver
      new Observer(() => sync()).observe(root, { attributes: true, attributeFilter: ['style', 'class'] })
    } catch {
      /* ignore */
    }
  }
}

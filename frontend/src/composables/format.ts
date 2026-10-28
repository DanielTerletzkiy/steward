import { LOCALE, t } from '@/i18n'
import type { Chore } from '@/types'

const euro = new Intl.NumberFormat(LOCALE, { style: 'currency', currency: 'EUR' })
const num = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 })
const dateFmt = new Intl.DateTimeFormat(LOCALE, { day: '2-digit', month: '2-digit', year: 'numeric' })
const shortDateFmt = new Intl.DateTimeFormat(LOCALE, { weekday: 'short', day: 'numeric', month: 'short' })
const dateTimeFmt = new Intl.DateTimeFormat(LOCALE, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })

export const formatEuro = (v: number | null | undefined) => (v == null ? '–' : euro.format(v))
export const formatNumber = (v: number) => num.format(v)
export const formatAmount = (amount: number, unit?: string | null) => (unit ? `${num.format(amount)} ${unit}` : num.format(amount))

/** The server sometimes sends naive datetimes; they are UTC. */
export function parseDateTime(s: string): Date {
  return /[zZ]|[+-]\d\d:?\d\d$/.test(s) ? new Date(s) : new Date(`${s}Z`)
}

/** "YYYY-MM-DD" as a local date (no UTC shift). */
export function parseDay(s: string): Date {
  const [y, m, d] = s.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function toIsoDay(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export function todayIso(): string {
  return toIsoDay(new Date())
}

export function addDays(iso: string, days: number): string {
  const d = parseDay(iso)
  d.setDate(d.getDate() + days)
  return toIsoDay(d)
}

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

/** Whole calendar days from today to the given date (negative = past). */
export function daysFromToday(d: Date): number {
  return Math.round((startOfDay(d).getTime() - startOfDay(new Date()).getTime()) / 86400000)
}

export const formatDate = (s: string | null | undefined) => (s ? dateFmt.format(s.length <= 10 ? parseDay(s) : parseDateTime(s)) : '–')
export const formatShortDate = (d: Date) => shortDateFmt.format(d)
export const formatDateTime = (s: string) => dateTimeFmt.format(parseDateTime(s))

export function relativeDay(n: number): string {
  if (n === 0) return t.rel.today
  if (n === 1) return t.rel.tomorrow
  if (n === -1) return t.rel.yesterday
  return n > 0 ? t.rel.inDays(n) : t.rel.daysAgo(-n)
}

/** For due dates of things to do: "today", "tomorrow", "overdue by 2 days". */
export function relativeDue(d: Date): string {
  const n = daysFromToday(d)
  if (n < 0) return t.rel.overdueDays(-n)
  return relativeDay(n)
}

/** For best-before dates: "expires today", "expired 3 days ago". */
export function relativeExpiry(iso: string | null): string {
  if (!iso) return t.rel.noDue
  const n = daysFromToday(parseDay(iso))
  if (n < 0) return t.rel.expiredDays(-n)
  if (n === 0) return t.rel.expiresToday
  return t.rel.expiresIn(n)
}

export function relativePast(s: string): string {
  return relativeDay(daysFromToday(parseDateTime(s)))
}

export function describeSchedule(c: Pick<Chore, 'schedule' | 'interval' | 'weekdays'>): string {
  const n = Math.max(1, c.interval)
  switch (c.schedule) {
    case 'manual':
      return t.chores.describe.manual
    case 'daily':
      return t.chores.describe.daily(n)
    case 'weekly': {
      const base = t.chores.describe.weekly(n)
      const days = [...c.weekdays].sort().map((d) => t.chores.weekdayShort[d]).join(', ')
      return days ? `${base} · ${days}` : base
    }
    case 'monthly':
      return t.chores.describe.monthly(n)
    case 'dynamic':
      return t.chores.describe.dynamic(n)
    default:
      return c.schedule
  }
}

/** "mdi:shower" (HA style) -> "mdi-shower" (MDI font class). */
export function mdiIcon(icon: string | null | undefined, fallback = 'mdi-broom'): string {
  if (!icon) return fallback
  return icon.replace(/^mdi:/, 'mdi-')
}

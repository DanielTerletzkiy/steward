// The kitchen terminal's shared state: the mode, the scans booked this session and how to book more.
// KioskView creates it once and provides it; the tabs (scan, stock, recipes, photo) inject it.
import { computed, inject, provide, ref, shallowRef, type InjectionKey, type Ref } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { beepError, beepOk } from './sound'
import { connected } from './live'
import { hasBatchChoice, sortBatches } from './batches'
import type { Product, ScanLookup, StockEntry, StockItem } from '@/types'

export type KioskMode = 'consume' | 'purchase' | 'open' | 'spoil' | 'shopping'
export type KioskTab = 'scan' | 'stock' | 'recipes' | 'photo'
export const MODES: KioskMode[] = ['consume', 'purchase', 'open', 'spoil', 'shopping']
export const MODE_STYLE: Record<KioskMode, { color: string; icon: string }> = {
  consume: { color: 'primary', icon: 'mdi-silverware-fork-knife' },
  purchase: { color: 'success', icon: 'mdi-cart-arrow-down' },
  open: { color: 'info', icon: 'mdi-package-variant' },
  spoil: { color: 'deep-orange', icon: 'mdi-delete-variant' },
  shopping: { color: 'secondary', icon: 'mdi-cart-plus' },
}
const NEEDS_STOCK: KioskMode[] = ['consume', 'open', 'spoil']
const MERGE_MS = 15_000 // the same product again within this adds to the card
const BANNER_MS = 6_000 // outside the scan tab, a booking shows this long

export interface Booking {
  txnIds: number[]
  entryIds: number[]
  shoppingItemId?: number
  amount: number
}
export interface Card {
  key: number
  productId: number
  name: string
  unit: string
  mode: KioskMode
  bookings: Booking[]
  at: number
  onList: boolean
  undone: boolean
  /** The product's batches when it was booked, if there was a choice (use or throw away only). */
  batches: StockEntry[]
}
type ProductRef = { id: number; name: string; unit: string }

export function createKiosk(stockById: Ref<Map<number, StockItem>>, productsById: Ref<Map<number, Product>>) {
  const mode = ref<KioskMode>('consume')
  const tab = ref<KioskTab>('scan')
  const current = ref<Card | null>(null)
  const earlier = ref<Card[]>([])
  const flash = ref<'ok' | 'error' | null>(null)
  const message = ref<string | null>(null)
  const problem = ref<ProductRef | null>(null)
  const unknown = ref<ScanLookup | null>(null)
  const busy = ref(false)
  const bannerUntil = ref(0)
  /** True while something should keep the screen on (a recipe is open, the camera is running). */
  const keepAwake = ref(false)
  /** The field that typing goes into when nothing has focus (set by the active tab). */
  const focusTarget = shallowRef<HTMLInputElement | null>(null)
  /** Increments on every scan, so the active tab's field drops the scanned characters. */
  const scanSeq = ref(0)
  let lastModeUse = Date.now()
  let nextKey = 1

  const inStock = (productId: number) => stockById.value.get(productId)?.amount ?? 0
  const total = (c: Card) => c.bookings.reduce((sum, b) => sum + b.amount, 0)

  let flashTimer: number | undefined
  function signal(kind: 'ok' | 'error', text: string | null = null) {
    flash.value = kind
    message.value = text
    if (kind === 'ok') beepOk()
    else beepError()
    window.clearTimeout(flashTimer)
    flashTimer = window.setTimeout(() => (flash.value = null), 700)
    if (tab.value !== 'scan') bannerUntil.value = Date.now() + BANNER_MS
  }
  const errorText = (e: unknown) => (!connected.value ? t.kiosk.offline : e instanceof Error ? e.message : t.kiosk.failed)
  async function guarded(fn: () => Promise<void>) {
    try {
      await fn()
    } catch (e) {
      signal('error', errorText(e))
    }
  }

  function setMode(m: KioskMode) {
    mode.value = m
    lastModeUse = Date.now()
  }
  /** Other modes fall back to Use after a minute without scanning. */
  function tick(now: number) {
    if (mode.value !== 'consume' && now - lastModeUse > 60_000) mode.value = 'consume'
  }

  function batchesFor(productId: number, m: KioskMode): StockEntry[] {
    if (m !== 'consume' && m !== 'spoil') return []
    const entries = stockById.value.get(productId)?.entries ?? []
    return hasBatchChoice(entries) ? sortBatches(entries) : []
  }

  async function bookDirect(productId: number, m: KioskMode, amount: number, entryId: number | null = null): Promise<Booking> {
    switch (m) {
      case 'purchase': {
        const res = await api.purchase({ product_id: productId, amount })
        return { txnIds: res.txn_ids, entryIds: [res.entry_id], amount }
      }
      case 'consume':
      case 'spoil': {
        const res = await api.consume(productId, amount, m === 'spoil', entryId)
        return { txnIds: res.txn_ids, entryIds: res.entry_ids, amount: res.consumed }
      }
      case 'open': {
        const res = await api.open(productId, amount, entryId)
        return { txnIds: res.txn_ids, entryIds: res.entry_ids, amount }
      }
      case 'shopping': {
        const lists = await api.shoppingLists()
        const item = await api.addShoppingItem(lists[0].id, { product_id: productId, amount })
        return { txnIds: [], entryIds: [], shoppingItemId: item.id, amount }
      }
    }
  }

  async function unbook(b: Booking) {
    for (const id of [...b.txnIds].reverse()) await api.undo(id)
    if (b.shoppingItemId) await api.deleteShoppingItem(b.shoppingItemId)
  }

  function record(product: ProductRef, m: KioskMode, booking: Booking, onList: boolean, batches: StockEntry[]) {
    const cur = current.value
    if (cur && !cur.undone && cur.productId === product.id && cur.mode === m && Date.now() - cur.at < MERGE_MS) {
      cur.bookings.push(booking)
      cur.at = Date.now()
      cur.onList = onList
    } else {
      if (cur) earlier.value = [cur, ...earlier.value].slice(0, 8)
      current.value = { key: nextKey++, productId: product.id, name: product.name, unit: product.unit, mode: m, bookings: [booking], at: Date.now(), onList, undone: false, batches }
    }
    if (m !== 'consume') lastModeUse = Date.now()
    signal('ok')
  }

  function notInStock(product: ProductRef) {
    problem.value = product
    signal('error', t.kiosk.notInStock(product.name))
  }

  /** Book one product in the current mode (a tile, a search hit, a batch button). */
  async function book(p: ProductRef, amount = 1, opts: { mode?: KioskMode; entryId?: number | null } = {}) {
    const m = opts.mode ?? mode.value
    problem.value = null
    if (NEEDS_STOCK.includes(m) && inStock(p.id) <= 0) return notInStock(p)
    const batches = opts.entryId == null ? batchesFor(p.id, m) : []
    await guarded(async () => record(p, m, await bookDirect(p.id, m, amount, opts.entryId ?? null), false, batches))
  }

  // Scans are handled one at a time, in order, even when they come in fast.
  let queue: Promise<void> = Promise.resolve()
  function onScan(raw: string) {
    scanSeq.value++
    const code = raw.trim()
    queue = queue.then(() => handleCode(code))
  }

  async function handleCode(code: string) {
    if (!code || unknown.value) return
    busy.value = true
    problem.value = null
    const m = mode.value
    try {
      const known = [...productsById.value.values()].find((p) => p.barcodes?.some((b) => b.code === code))
      const batches = known ? batchesFor(known.id, m) : []
      const res = await api.scan(code, m)
      if (res.mode_switch && MODES.includes(res.mode_switch as KioskMode)) {
        setMode(res.mode_switch as KioskMode)
        signal('ok', t.kiosk.modeSwitched(t.kiosk.modes[res.mode_switch]))
      } else if (res.product_id == null) {
        unknown.value = res
        signal('error', t.kiosk.unknown)
      } else if (res.not_in_stock) {
        const p = productsById.value.get(res.product_id)
        notInStock({ id: res.product_id, name: res.product_name ?? p?.name ?? code, unit: res.unit ?? p?.unit ?? '' })
      } else if (res.done) {
        const booking = { txnIds: res.txn_ids ?? [], entryIds: res.entry_ids ?? [], shoppingItemId: res.shopping_item_id, amount: res.amount ?? 1 }
        record({ id: res.product_id, name: res.product_name ?? code, unit: res.unit ?? '' }, m, booking, !!res.on_shopping_list, batches)
      } else {
        signal('error', t.kiosk.failed)
      }
    } catch (e) {
      signal('error', errorText(e))
    } finally {
      busy.value = false
    }
  }

  function unknownDone() {
    const code = unknown.value?.code
    unknown.value = null
    if (code) queue = queue.then(() => handleCode(code))
  }

  const plus = (card: Card) =>
    guarded(async () => {
      if (NEEDS_STOCK.includes(card.mode) && inStock(card.productId) <= 0) return signal('error', t.kiosk.noneLeft)
      card.bookings.push(await bookDirect(card.productId, card.mode, card.bookings.at(-1)?.amount || 1))
      card.at = Date.now()
      signal('ok')
    })

  const minus = (card: Card) =>
    guarded(async () => {
      const last = card.bookings.at(-1)
      if (!last) return
      await unbook(last)
      card.bookings.pop()
      if (!card.bookings.length) card.undone = true
      signal('ok')
    })

  const useAll = (card: Card) =>
    guarded(async () => {
      const left = inStock(card.productId)
      if (left <= 0) return
      card.bookings.push(await bookDirect(card.productId, 'consume', left))
      card.at = Date.now()
      signal('ok')
    })

  const undoCard = (card: Card) =>
    guarded(async () => {
      while (card.bookings.length) {
        await unbook(card.bookings.at(-1)!)
        card.bookings.pop()
      }
      card.undone = true
      signal('ok', t.kiosk.undone)
    })

  /** Take the card's amount from another batch instead: undo it, then book it again on that one. */
  const moveToBatch = (card: Card, entryId: number) =>
    guarded(async () => {
      const amount = total(card)
      while (card.bookings.length) {
        await unbook(card.bookings.at(-1)!)
        card.bookings.pop()
      }
      card.bookings.push(await bookDirect(card.productId, card.mode, amount, entryId))
      card.at = Date.now()
      signal('ok', t.kiosk.batchMoved)
    })

  /** Stock was wrong: there is still some. Book what is there now. */
  async function correctStock(amount: number) {
    const p = problem.value
    if (!p || !(amount > 0)) return false
    try {
      await api.purchase({ product_id: p.id, amount })
      problem.value = null
      signal('ok', t.kiosk.corrected)
      return true
    } catch (e) {
      signal('error', errorText(e))
      return false
    }
  }

  const usedEntryIds = (c: Card) => new Set(c.bookings.flatMap((b) => b.entryIds))

  return {
    mode, tab, current, earlier, flash, message, problem, unknown, busy, bannerUntil, keepAwake, focusTarget, scanSeq,
    inStock, total, signal, setMode, tick, book, onScan, unknownDone, plus, minus, useAll, undoCard, moveToBatch,
    correctStock, usedEntryIds, style: computed(() => MODE_STYLE[mode.value]),
  }
}

export type Kiosk = ReturnType<typeof createKiosk>
const KEY: InjectionKey<Kiosk> = Symbol('kiosk')
export const provideKiosk = (kiosk: Kiosk) => provide(KEY, kiosk)
export function useKiosk(): Kiosk {
  const kiosk = inject(KEY)
  if (!kiosk) throw new Error('useKiosk() outside the kiosk page')
  return kiosk
}

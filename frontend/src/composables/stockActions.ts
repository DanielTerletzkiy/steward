// Stock actions with an Undo snackbar. The API returns the transaction ids each action created,
// so Undo reverts exactly those.
import { api } from '@/api'
import { t } from '@/i18n'
import { formatAmount } from './format'
import { attempt, notify, notifyError } from './notify'
import type { Product } from '@/types'

export type Undo = () => Promise<void>

/** Undo for the given transactions (newest first, so a split purchase unwinds cleanly). */
export function undoTxns(txnIds: number[]): Undo {
  let done = false
  return async () => {
    if (done || !txnIds.length) return
    try {
      for (const id of [...txnIds].reverse()) await api.undo(id)
      done = true
      notify(t.common.undone)
    } catch (e) {
      notifyError(e)
    }
  }
}

function offerUndo(text: string, txnIds: number[]): Undo {
  const run = undoTxns(txnIds)
  notify(text, txnIds.length ? { action: { label: t.common.undo, run } } : {})
  return run
}

export async function purchase(
  product: Product,
  amount = 1,
  extra: { due_date?: string | null; location_id?: number | null; unit_price?: number | null } = {},
) {
  const res = await attempt(() => api.purchase({ product_id: product.id, amount, ...extra }))
  if (!res) return false
  return offerUndo(t.stock.purchased(product.name, formatAmount(amount, product.unit)), res.txn_ids ?? [])
}

export async function consume(product: Product, amount = 1, spoiled = false) {
  const res = await attempt(() => api.consume(product.id, amount, spoiled))
  if (!res) return false
  const text = spoiled ? t.stock.spoiled(product.name) : t.stock.consumed(product.name, formatAmount(res.consumed, product.unit))
  return offerUndo(text, res.txn_ids ?? [])
}

export async function openProduct(product: Product, amount = 1) {
  const res = await attempt(() => api.open(product.id, amount))
  if (!res) return false
  return offerUndo(t.stock.openedMsg(product.name), res.txn_ids ?? [])
}


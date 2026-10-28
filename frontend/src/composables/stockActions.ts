// Stock actions with an Undo snackbar. The API returns no transaction ids, so after an action we
// look at the newest journal rows for that product to find what to undo.
import { api } from '@/api'
import { t } from '@/i18n'
import { formatAmount } from './format'
import { attempt, notify, notifyError } from './notify'
import type { Product, StockTxn } from '@/types'

async function latestTxns(productId: number, type: string, amount: number): Promise<StockTxn[]> {
  const journal = await api.journal(20)
  const picked: StockTxn[] = []
  let sum = 0
  for (const txn of journal) {
    if (txn.product_id !== productId || txn.type !== type || txn.undone) break
    picked.push(txn)
    sum += txn.amount
    if (sum >= amount - 1e-6) break
  }
  return picked
}

function offerUndo(text: string, productId: number, type: string, amount: number) {
  // Resolve the ids right away, before anything else lands in the journal.
  const pending = latestTxns(productId, type, amount).catch(() => [] as StockTxn[])
  notify(text, {
    action: {
      label: t.common.undo,
      run: async () => {
        const txns = await pending
        if (!txns.length) return
        try {
          for (const txn of txns) await api.undo(txn.id)
          notify(t.common.undone)
        } catch (e) {
          notifyError(e)
        }
      },
    },
  })
}

export async function purchase(
  product: Product,
  amount = 1,
  extra: { due_date?: string | null; location_id?: number | null; unit_price?: number | null } = {},
) {
  const res = await attempt(() => api.purchase({ product_id: product.id, amount, ...extra }))
  if (res) offerUndo(t.stock.purchased(product.name, formatAmount(amount, product.unit)), product.id, 'purchase', amount)
  return !!res
}

export async function consume(product: Product, amount = 1, spoiled = false) {
  const res = await attempt(() => api.consume(product.id, amount, spoiled))
  if (!res) return false
  const text = spoiled ? t.stock.spoiled(product.name) : t.stock.consumed(product.name, formatAmount(res.consumed, product.unit))
  offerUndo(text, product.id, spoiled ? 'spoil' : 'consume', res.consumed)
  return true
}

export async function openProduct(product: Product, amount = 1) {
  const ok = await attempt(async () => {
    await api.open(product.id, amount)
    return true
  })
  if (ok) notify(t.stock.openedMsg(product.name))
  return !!ok
}

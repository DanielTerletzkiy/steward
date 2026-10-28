// All URLs are relative ("api/...") so the app works under any ingress path prefix.
import type {
  Chore, ChoreIn, Location, Person, Product, ProductIn, Receipt, ReceiptLine, ReceiptSummary,
  ShoppingItem, ShoppingList, StockItem, StockTxn, Summary, Task, TaskIn,
} from './types'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {}, credentials: 'same-origin' }
  if (body instanceof FormData) {
    init.body = body
  } else if (body !== undefined) {
    init.body = JSON.stringify(body)
    ;(init.headers as Record<string, string>)['Content-Type'] = 'application/json'
  }
  const res = await fetch(`api/${path}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') detail = data.detail
      else if (Array.isArray(data.detail)) detail = data.detail.map((d: { msg?: string }) => d.msg).join(', ')
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

const get = <T>(p: string) => request<T>('GET', p)
const post = <T>(p: string, b?: unknown) => request<T>('POST', p, b)
const patch = <T>(p: string, b: unknown) => request<T>('PATCH', p, b)
const put = <T>(p: string, b: unknown) => request<T>('PUT', p, b)
const del = (p: string) => request<void>('DELETE', p)

export const api = {
  summary: () => get<Summary>('summary'),
  people: () => get<Person[]>('people'),
  locations: () => get<Location[]>('locations'),
  createLocation: (name: string, is_freezer = false) => post<Location>('locations', { name, is_freezer }),

  products: () => get<Product[]>('products'),
  createProduct: (body: ProductIn) => post<Product>('products', body),
  updateProduct: (id: number, body: Partial<ProductIn>) => patch<Product>(`products/${id}`, body),
  deleteProduct: (id: number) => del(`products/${id}`),

  stock: (includeEmpty = true) => get<StockItem[]>(`stock?include_empty=${includeEmpty}`),
  journal: (limit = 100) => get<StockTxn[]>(`stock/journal?limit=${limit}`),
  purchase: (body: { product_id: number; amount: number; due_date?: string | null; location_id?: number | null; unit_price?: number | null }) =>
    post<{ entry_id: number }>('stock/purchase', body),
  consume: (product_id: number, amount = 1, spoiled = false) =>
    post<{ consumed: number }>('stock/consume', { product_id, amount, spoiled }),
  open: (product_id: number, amount = 1) => post<void>('stock/open', { product_id, amount }),
  undo: (txnId: number) => post<void>(`stock/undo/${txnId}`),

  shoppingLists: () => get<ShoppingList[]>('shopping-lists'),
  shoppingItems: (listId: number) => get<ShoppingItem[]>(`shopping-lists/${listId}/items`),
  addShoppingItem: (listId: number, body: { text?: string; product_id?: number; amount?: number; note?: string }) =>
    post<ShoppingItem>(`shopping-lists/${listId}/items`, body),
  addMissing: (listId: number) => post<{ added: number }>(`shopping-lists/${listId}/add-missing`),
  clearDone: (listId: number) => post<{ removed: number }>(`shopping-lists/${listId}/clear-done`),
  updateShoppingItem: (id: number, body: Partial<Pick<ShoppingItem, 'text' | 'amount' | 'note' | 'done'>>) =>
    patch<ShoppingItem>(`shopping-items/${id}`, body),
  deleteShoppingItem: (id: number) => del(`shopping-items/${id}`),

  chores: () => get<Chore[]>('chores'),
  createChore: (body: ChoreIn) => post<Chore>('chores', body),
  deleteChore: (id: number) => del(`chores/${id}`),
  executeChore: (id: number, opts: { person_id?: string | null; skipped?: boolean } = {}) =>
    post<Chore>(`chores/${id}/execute`, opts),

  tasks: (includeDone = true) => get<Task[]>(`tasks?include_done=${includeDone}`),
  createTask: (body: TaskIn) => post<Task>('tasks', body),
  updateTask: (id: number, body: Partial<TaskIn> & { done?: boolean }) => patch<Task>(`tasks/${id}`, body),
  deleteTask: (id: number) => del(`tasks/${id}`),

  receipts: () => get<ReceiptSummary[]>('receipts'),
  receipt: (id: number) => get<Receipt>(`receipts/${id}`),
  uploadReceipt: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return post<Receipt>('receipts', form)
  },
  matchLine: (receiptId: number, lineId: number, body: { product_id: number } | { new_product: ProductIn }) =>
    put<ReceiptLine>(`receipts/${receiptId}/lines/${lineId}`, body),
  stockReceipt: (id: number) => post<{ stocked: number }>(`receipts/${id}/stock`),
}

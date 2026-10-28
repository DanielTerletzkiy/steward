// Mirrors server/steward_server/schemas.py

export interface Person {
  id: string
  name: string
  user_id: string | null
  picture: string | null
  state: string | null
  active: boolean
}

export interface Location {
  id: number
  name: string
  is_freezer: boolean
}

export interface Product {
  id: number
  name: string
  brand: string | null
  category: string | null
  location_id: number | null
  unit: string
  min_stock: number
  due_days: number | null
  due_type: string
  image_url: string | null
}

export interface ProductIn {
  name: string
  brand?: string | null
  category?: string | null
  location_id?: number | null
  unit?: string
  min_stock?: number
  due_days?: number | null
  due_type?: string
  image_url?: string | null
  barcodes?: string[]
  receipt_aliases?: string[]
}

export type StockStatus = 'ok' | 'due_soon' | 'expired' | 'out'

export interface StockEntry {
  id: number
  amount: number
  location_id: number | null
  due_date: string | null
  opened_at: string | null
  purchased_at: string
  unit_price: number | null
}

export interface StockItem {
  product: Product
  amount: number
  opened: number
  next_due: string | null
  status: StockStatus
  below_min: boolean
  value: number
  entries: StockEntry[]
}

export interface StockTxn {
  id: number
  type: 'purchase' | 'consume' | 'spoil' | 'open' | string
  product_id: number
  product_name: string
  amount: number
  unit_price: number | null
  at: string
  actor: string | null
  source: string
  undone: boolean
}

export interface ShoppingList {
  id: number
  name: string
}

export interface ShoppingItem {
  id: number
  list_id: number
  product_id: number | null
  text: string
  amount: number
  note: string | null
  done: boolean
  created_at: string
}

export type ChoreStatus = 'overdue' | 'due_today' | 'due_soon' | 'scheduled' | 'manual'
export type Schedule = 'manual' | 'daily' | 'weekly' | 'monthly' | 'dynamic'
export type Assignment = 'none' | 'fixed' | 'least_done' | 'rotation'

export interface Chore {
  id: number
  name: string
  description: string | null
  icon: string | null
  schedule: Schedule
  interval: number
  weekdays: number[]
  assignment: Assignment
  assignees: string[]
  next_assignee: string | null
  next_due: string | null
  status: ChoreStatus
  last_done: string | null
  last_done_by: string | null
  points: number
}

export interface ChoreIn {
  name: string
  description?: string | null
  icon?: string | null
  schedule: Schedule
  interval: number
  weekdays: number[]
  assignment: Assignment
  assignees: string[]
  points?: number
  first_due?: string | null
}

export interface Task {
  id: number
  name: string
  notes: string | null
  category: string
  due_date: string | null
  assignee: string | null
  done_at: string | null
}

export interface TaskIn {
  name: string
  notes?: string | null
  category?: string
  due_date?: string | null
  assignee?: string | null
}

export type LineKind = 'item' | 'deposit' | 'deposit_return' | 'bag' | string

export interface ReceiptLine {
  id: number
  idx: number
  raw_text: string
  qty: number
  unit: string | null
  unit_price: number | null
  total: number
  tax: string | null
  kind: LineKind
  product_id: number | null
  confidence: number
  method: 'alias' | 'fuzzy' | 'manual' | string | null
  confirmed: boolean
}

export interface Receipt {
  id: number
  chain: string
  store: string | null
  at: string
  total: number
  payment: string | null
  loyalty: string | null
  source: string
  stocked: boolean
  lines: ReceiptLine[]
}

export interface ReceiptSummary {
  id: number
  chain: string
  store: string | null
  at: string
  total: number
  stocked: boolean
  line_count: number
  matched: number
  unmatched: number
}

export interface ItemBrief {
  product_id: number
  name: string
  amount: number
  unit: string
  due: string | null
}

export interface Summary {
  stock: {
    products_in_stock: number
    value: number
    expired: ItemBrief[]
    due_soon: ItemBrief[]
    below_min: ItemBrief[]
  }
  chores: { overdue: Chore[]; due_today: Chore[] }
  tasks: { open: number; due: { id: number; name: string; due: string }[] }
  spending: {
    month_total: number
    month_trips: number
    total_spent: number
    deposit_balance: number
    last_trip: { receipt_id: number; store: string | null; at: string; total: number; items: number } | null
  }
  people: Record<string, { name: string; chores_due: string[] }>
}

export type Topic = 'stock' | 'shopping' | 'chores' | 'tasks' | 'receipts' | 'people' | 'catalog'

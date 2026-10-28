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
  equipment: {
    count: number
    warranty_ending: { id: number; name: string; warranty_until: string }[]
    running: { id: number; name: string; kind: string; state: string | null; remaining_minutes: number | null; battery: number | null }[]
  }
  meals_today: { id: number; slot: MealSlot; recipe_id: number | null; name: string | null; note: string | null; servings: number | null; done: boolean }[]
  wardrobe: {
    garments: number
    clean: number
    laundry: number
    /** Keyed by owner id, '' = household. */
    outfits_today: Record<string, { id: number; garment_ids: number[]; worn: boolean; source: OutfitSource; reason: string | null }>
    laundry_prompt: LaundryPrompt | null
  }
}

export type Topic =
  | 'stock' | 'shopping' | 'chores' | 'tasks' | 'receipts' | 'people' | 'catalog'
  | 'equipment' | 'wardrobe' | 'settings' | 'recipes' | 'mealplan'

export interface Me {
  user: { id: string; name: string } | null
  can_sign_out: boolean
  app: boolean
}

// --- files

export interface StoredFile {
  id: string
  kind: string
  filename: string | null
  content_type: string
  size: number
  pages: number | null
  created_at: string
}

// --- equipment

export type WarrantyStatus = 'none' | 'active' | 'ending' | 'expired'
export type DocumentKind = 'manual' | 'invoice' | 'other'

export interface EquipmentDocument {
  id: number
  kind: DocumentKind | string
  title: string
  file: StoredFile
}

export interface EquipmentIn {
  name: string
  kind?: string
  ha_entities?: string[]
  automation?: { chores?: ChoreAutomation; laundry?: LaundryAutomation }
  brand?: string | null
  model?: string | null
  serial?: string | null
  room?: string | null
  ha_device_id?: string | null
  purchased_on?: string | null
  price?: number | null
  shop?: string | null
  warranty_until?: string | null
  notes?: string | null
  consumable_ids?: number[]
  chore_ids?: number[]
}

export type ApplianceKind = 'washer' | 'dryer' | 'dishwasher' | 'vacuum' | 'other'
export type ChoreAutomation = 'complete' | 'make_due' | 'off'
export type LaundryAutomation = 'ask' | 'auto' | 'off'

export interface ApplianceLive {
  state: string | null
  running: boolean
  remaining_minutes: number | null
  battery: number | null
  commands: string[]
  entities: { entity_id: string; name: string | null; state: string | null; unit?: string | null }[]
}

export interface HaDevice {
  id: string
  name: string
  manufacturer: string | null
  model: string | null
  area: string | null
  kind: ApplianceKind | null
  entities: { entity_id: string; name: string | null; state: string | null }[]
}

export interface HaEntity {
  entity_id: string
  name: string | null
  state: string | null
  domain: string
}

export interface EquipmentRun {
  id: number
  finished_at: string
  source: string | null
  detail: string | null
}

export interface LaundryPrompt {
  equipment_id: number
  name: string
  at: string
  pieces: number
}

export interface Equipment {
  id: number
  kind: ApplianceKind | string
  ha_entities: string[]
  automation: { chores?: ChoreAutomation; laundry?: LaundryAutomation }
  automation_effective: { chores: ChoreAutomation; laundry: LaundryAutomation }
  live: ApplianceLive | null
  live_at: string | null
  run_count: number
  last_run_at: string | null
  name: string
  brand: string | null
  model: string | null
  serial: string | null
  room: string | null
  ha_device_id: string | null
  purchased_on: string | null
  price: number | null
  shop: string | null
  warranty_until: string | null
  warranty_status: WarrantyStatus
  notes: string | null
  photo_id: string | null
  consumable_ids: number[]
  chore_ids: number[]
  documents: EquipmentDocument[]
}

export interface ManualHit {
  equipment_id: number
  equipment_name: string
  document_id: number
  document_title: string
  file_id: string
  page: number
  /** Matches are wrapped in « ». */
  snippet: string
}

// --- wardrobe

export type GarmentState = 'clean' | 'worn' | 'laundry' | 'repair' | 'lent' | 'stored'
export type OutfitSource = 'manual' | 'rules' | 'ai'

export interface WardrobeVocabulary {
  categories: { name: string; layer: string; wears_per_wash: number }[]
  layers: string[]
  states: GarmentState[]
  rain: string[]
  uses: string[]
  seasons: string[]
  patterns: string[]
  colors: string[]
}

export interface GarmentIn {
  owner?: string | null
  name: string
  category: string
  layer?: string | null
  colors?: string[]
  pattern?: string | null
  material?: string | null
  warmth?: number
  temp_min?: number | null
  temp_max?: number | null
  rain?: string
  windproof?: boolean
  formality?: number
  uses?: string[]
  seasons?: string[]
  brand?: string | null
  size?: string | null
  price?: number | null
  favorite?: boolean
  notes?: string | null
  wears_per_wash?: number | null
}

export interface Garment {
  id: number
  owner: string | null
  name: string
  category: string
  layer: string
  colors: string[]
  pattern: string | null
  material: string | null
  warmth: number
  temp_min: number | null
  temp_max: number | null
  rain: string
  windproof: boolean
  formality: number
  uses: string[]
  seasons: string[]
  brand: string | null
  size: string | null
  price: number | null
  favorite: boolean
  notes: string | null
  photo_id: string | null
  state: GarmentState
  wears_per_wash: number
  wears_since_wash: number
  wear_count: number
  last_worn: string | null
  cost_per_wear: number | null
}

export interface Outfit {
  id: number
  owner: string | null
  day: string
  garment_ids: number[]
  source: OutfitSource
  occasion: string | null
  weather: Record<string, unknown> | null
  reason: string | null
  worn: boolean
  rating: -1 | 0 | 1
  feedback: string | null
  created_at: string
}

export interface OutfitIn {
  owner?: string | null
  day?: string | null
  garment_ids: number[]
  occasion?: string | null
  worn?: boolean
}

export interface StyleProfile {
  owner?: string
  description: string | null
  likes: string[]
  dislikes: string[]
  runs_warm: number
}

// --- settings

export type AiJob = 'scan' | 'wardrobe' | 'outfits'
export type AiProviderType = 'home_assistant' | 'anthropic' | 'openai' | 'ollama' | 'openai_compatible' | 'google'

export interface AiProvider {
  id: string
  type: AiProviderType | string
  name: string
  model: string | null
  base_url: string | null
  entity_id: string | null
  api_key_set: boolean
}

export interface AiProviderIn {
  id?: string
  type: string
  name: string
  model?: string | null
  base_url?: string | null
  entity_id?: string | null
  /** Left out = keep the stored key; '' = clear it. */
  api_key?: string
}

/** A provider id, null = automatic, 'off'. */
export type AiJobChoice = string | null

export interface AiSettings {
  providers: AiProvider[]
  jobs: Record<AiJob, AiJobChoice>
  types: { type: string; label: string; model: string | null; base_url: string | null; key: boolean }[]
  home_assistant: { connected: boolean; ai_task: boolean; ai_task_entities: string[] }
  effective: Record<AiJob, { id: string; type: string; name: string; model: string | null } | null>
}

export interface WeatherSettings {
  entity_id?: string | null
  latitude?: number | null
  longitude?: number | null
  home_assistant: { connected: boolean; weather: boolean; entities: string[] }
}

export interface Forecast {
  day: string
  source: string
  temp_min: number
  temp_max: number
  feels_min: number
  feels_max: number
  rain_probability: number
  rain_from: string | null
  wind_max: number
  conditions: string[]
}

export interface GarmentAnalysis {
  name: string | null
  category: string | null
  layer: string | null
  wears_per_wash: number | null
  colors: string[]
  pattern: string | null
  material: string | null
  warmth: number
  temp_min: number | null
  temp_max: number | null
  rain: string
  windproof: boolean
  formality: number
  uses: string[]
  seasons: string[]
  brand: string | null
}

// --- scanning

export type ScanMode = 'purchase' | 'consume' | 'open' | 'spoil' | 'shopping' | 'lookup'

export interface ScanLookup {
  code: string
  gtin: string | null
  due_date: string | null
  due_type?: string | null
  lot: string | null
  product_id: number | null
  suggestion: { name: string; brand: string | null; category: string | null; image_url: string | null; location_id: number | null; source_site: string | null } | null
  similar_product_id?: number | null
  /** The barcode's pack size (e.g. 6 for a six-pack code), or null. */
  pack_amount?: number | null
  source: 'local' | 'openfoodfacts' | 'none'
}

export interface ScanResult extends ScanLookup {
  mode: ScanMode
  done: boolean
  amount?: number
  product_name?: string
}

export interface RecognizedItem {
  name: string
  brand: string | null
  quantity: number
  unit: string
  barcode: string | null
  due_date: string | null
  due_type: string | null
  date_text_seen: string | null
  category: string | null
  location_id: number | null
  shelf_life_days: number | null
  confidence: number | null
  product_id: number | null
  match_score: number
}

// --- recipes and meal plan

export interface Ingredient {
  id: number
  text: string
  name: string
  amount: number | null
  unit: string | null
  product_id: number | null
  stock_amount: number | null
  optional: boolean
  group: string | null
}

export interface IngredientIn {
  text: string
  name?: string | null
  amount?: number | null
  unit?: string | null
  product_id?: number | null
  stock_amount?: number | null
  optional?: boolean
  group?: string | null
}

export interface Recipe {
  id: number
  name: string
  description: string | null
  servings: number
  minutes: number | null
  instructions: string | null
  source_url: string | null
  photo_id: string | null
  tags: string[]
  favorite: boolean
  cooked_count: number
  last_cooked: string | null
  ingredients: Ingredient[]
}

export interface RecipeIn {
  name: string
  description?: string | null
  servings?: number
  minutes?: number | null
  instructions?: string | null
  source_url?: string | null
  tags?: string[]
  favorite?: boolean
  ingredients?: IngredientIn[]
}

export type IngredientStatusKind = 'have' | 'partial' | 'missing' | 'unlinked' | 'optional'

export interface Fulfillment {
  recipe_id: number
  servings: number
  can_cook: boolean
  missing: number
  unlinked: number
  uses_expiring: number
  ingredients: {
    ingredient_id: number
    name: string
    product_id: number | null
    product_name: string | null
    needed: number | null
    in_stock: number | null
    unit: string | null
    status: IngredientStatusKind
    expiring: boolean
  }[]
}

export interface RecipeSuggestion {
  recipe: Recipe
  fulfillment: Fulfillment
  score: number
}

export type MealSlot = 'breakfast' | 'lunch' | 'dinner' | 'snack'

export interface MealPlanEntry {
  id: number
  day: string
  slot: MealSlot
  recipe_id: number | null
  note: string | null
  servings: number | null
  done: boolean
}

export interface MealPlanIn {
  day: string
  slot: MealSlot
  recipe_id?: number | null
  note?: string | null
  servings?: number | null
}

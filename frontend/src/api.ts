// All URLs are relative ("api/...") so the app works under any ingress path prefix.
import { requireLogin } from './composables/auth'
import type {
  AiProviderIn, AiSettings, Chore, ChoreIn, ChorePatch, Equipment, EquipmentDocument, EquipmentIn, Forecast, Garment, GarmentAnalysis,
  GarmentIn, GarmentState, Location, ManualHit, Me, Outfit, OutfitIn, Person, Product, ProductAliases, ProductIn, Receipt, ReceiptAlias, ReceiptLine,
  ReceiptSummary, RecognizedItem, EquipmentRun, HaDevice, HaEntity, ScanLookup, ScanMode, ScanResult, ShoppingItem, ShoppingList, StockItem, StockTxn,
  StyleProfile, Summary, Task, TaskIn, WardrobeVocabulary, WeatherSettings,
  Fulfillment, MealPlanEntry, MealPlanIn, Recipe, RecipeIn, RecipeSuggestion, StockEntry, EmailImportIn, EmailImportRun, EmailImportSettings,
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
  if (res.status === 401) requireLogin()
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

/** Relative URL of a stored photo or document; `thumb` gives the 480 px WebP preview. */
export const fileUrl = (id: string, thumb = false) => `api/files/${encodeURIComponent(id)}${thumb ? '/thumb' : ''}`

function upload(file: Blob, fields: Record<string, string | null | undefined> = {}): FormData {
  const form = new FormData()
  form.append('file', file)
  for (const [k, v] of Object.entries(fields)) if (v != null && v !== '') form.append(k, v)
  return form
}

const query = (params: Record<string, string | number | null | undefined>) => {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v != null && v !== '') q.set(k, String(v))
  const s = q.toString()
  return s ? `?${s}` : ''
}

export const api = {
  summary: () => get<Summary>('summary'),
  me: () => get<Me>('me'),
  people: () => get<Person[]>('people'),
  locations: () => get<Location[]>('locations'),
  createLocation: (name: string, is_freezer = false) => post<Location>('locations', { name, is_freezer }),
  updateLocation: (id: number, body: { name?: string; is_freezer?: boolean }) => patch<Location>(`locations/${id}`, body),
  deleteLocation: (id: number) => del(`locations/${id}`),

  products: () => get<Product[]>('products'),
  createProduct: (body: ProductIn) => post<Product>('products', body),
  updateProduct: (id: number, body: Partial<ProductIn>) => patch<Product>(`products/${id}`, body),
  deleteProduct: (id: number) => del(`products/${id}`),
  receiptAliases: () => get<ReceiptAlias[]>('receipt-aliases'),
  setProductAliases: (id: number, texts: string[]) => put<ProductAliases>(`products/${id}/aliases`, { texts }),

  stock: (includeEmpty = true) => get<StockItem[]>(`stock?include_empty=${includeEmpty}`),
  editEntry: (entryId: number, body: { amount?: number; due_date?: string | null; unit_price?: number | null }) =>
    patch<StockEntry>(`stock/entries/${entryId}`, body),
  moveEntry: (entryId: number, location_id: number | null) => put<StockEntry>(`stock/entries/${entryId}/location`, { location_id }),
  journal: (limit = 100) => get<StockTxn[]>(`stock/journal?limit=${limit}`),
  purchase: (body: { product_id: number; amount: number; due_date?: string | null; location_id?: number | null; unit_price?: number | null }) =>
    post<{ entry_id: number; txn_ids: number[] }>('stock/purchase', body),
  consume: (product_id: number, amount = 1, spoiled = false) =>
    post<{ consumed: number; txn_ids: number[] }>('stock/consume', { product_id, amount, spoiled }),
  open: (product_id: number, amount = 1) => post<{ txn_ids: number[] }>('stock/open', { product_id, amount }),
  undo: (txnId: number) => post<void>(`stock/undo/${txnId}`),

  shoppingLists: () => get<ShoppingList[]>('shopping-lists'),
  shoppingItems: (listId: number) => get<ShoppingItem[]>(`shopping-lists/${listId}/items`),
  addShoppingItem: (listId: number, body: { text?: string; product_id?: number; amount?: number; note?: string }) =>
    post<ShoppingItem>(`shopping-lists/${listId}/items`, body),
  addMissing: (listId: number) => post<{ added: number }>(`shopping-lists/${listId}/add-missing`),
  clearDone: (listId: number) => post<{ removed: number }>(`shopping-lists/${listId}/clear-done`),
  updateShoppingItem: (id: number, body: Partial<Pick<ShoppingItem, 'text' | 'amount' | 'done'>> & { note?: string | null }) =>
    patch<ShoppingItem>(`shopping-items/${id}`, body),
  deleteShoppingItem: (id: number) => del(`shopping-items/${id}`),

  chores: () => get<Chore[]>('chores'),
  createChore: (body: ChoreIn) => post<Chore>('chores', body),
  updateChore: (id: number, body: ChorePatch) => patch<Chore>(`chores/${id}`, body),
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
  setLinePieces: (receiptId: number, lineId: number, pieces: number) =>
    put<ReceiptLine>(`receipts/${receiptId}/lines/${lineId}/pieces`, { pieces }),
  deleteReceipt: (id: number) => del(`receipts/${id}`),
  stockReceipt: (id: number) => post<{ stocked: number }>(`receipts/${id}/stock`),

  equipmentList: () => get<Equipment[]>('equipment'),
  equipment: (id: number) => get<Equipment>(`equipment/${id}`),
  createEquipment: (body: EquipmentIn) => post<Equipment>('equipment', body),
  updateEquipment: (id: number, body: Partial<EquipmentIn>) => patch<Equipment>(`equipment/${id}`, body),
  deleteEquipment: (id: number) => del(`equipment/${id}`),
  setEquipmentPhoto: (id: number, file: Blob) => put<Equipment>(`equipment/${id}/photo`, upload(file)),
  deleteEquipmentPhoto: (id: number) => request<Equipment>('DELETE', `equipment/${id}/photo`),
  addEquipmentDocument: (id: number, file: Blob, kind: string, title?: string | null) =>
    post<EquipmentDocument>(`equipment/${id}/documents`, upload(file, { kind, title })),
  deleteEquipmentDocument: (id: number, docId: number) => del(`equipment/${id}/documents/${docId}`),
  searchManuals: (q: string, equipmentId?: number | null) =>
    get<ManualHit[]>(`equipment/search${query({ q, equipment_id: equipmentId })}`),

  wardrobeVocabulary: () => get<WardrobeVocabulary>('wardrobe/vocabulary'),
  garments: (owner?: string | null) => get<Garment[]>(`wardrobe/garments${query({ owner })}`),
  garment: (id: number) => get<Garment>(`wardrobe/garments/${id}`),
  createGarment: (body: GarmentIn) => post<Garment>('wardrobe/garments', body),
  updateGarment: (id: number, body: Partial<GarmentIn> & { state?: GarmentState; wears_since_wash?: number; extra_wears?: number; dry_until?: string | null }) => patch<Garment>(`wardrobe/garments/${id}`, body),
  deleteGarment: (id: number) => del(`wardrobe/garments/${id}`),
  setGarmentPhoto: (id: number, file: Blob) => put<Garment>(`wardrobe/garments/${id}/photo`, upload(file)),
  deleteGarmentPhoto: (id: number) => request<Garment>('DELETE', `wardrobe/garments/${id}/photo`),
  wear: (garment_ids: number[], day?: string | null) => post<Garment[]>('wardrobe/wear', { garment_ids, day: day ?? null }),
  laundryDone: (garment_ids?: number[]) => post<{ washed: number }>('wardrobe/laundry/done', { garment_ids: garment_ids ?? null }),
  outfits: (opts: { owner?: string | null; day?: string | null; limit?: number } = {}) =>
    get<Outfit[]>(`wardrobe/outfits${query(opts)}`),
  createOutfit: (body: OutfitIn) => post<Outfit>('wardrobe/outfits', body),
  wearOutfit: (id: number) => post<Outfit>(`wardrobe/outfits/${id}/wear`),
  outfitFeedback: (id: number, rating: number, feedback?: string | null) =>
    post<Outfit>(`wardrobe/outfits/${id}/feedback`, { rating, feedback: feedback ?? null }),
  deleteOutfit: (id: number) => del(`wardrobe/outfits/${id}`),
  styleProfile: (owner?: string | null) => get<StyleProfile>(`wardrobe/profile${query({ owner })}`),
  setStyleProfile: (body: StyleProfile, owner?: string | null) =>
    put<StyleProfile>(`wardrobe/profile${query({ owner })}`, { description: body.description, likes: body.likes, dislikes: body.dislikes, runs_warm: body.runs_warm }),

  aiSettings: () => get<AiSettings>('settings/ai'),
  saveAiSettings: (body: { providers: AiProviderIn[]; jobs: Record<string, string | null> }) => put<AiSettings>('settings/ai', body),
  testAi: (providerId: string) => post<{ ok: boolean; answer: unknown }>(`settings/ai/test/${encodeURIComponent(providerId)}`),
  weatherSettings: () => get<WeatherSettings>('settings/weather'),
  saveWeatherSettings: (body: { entity_id?: string | null; latitude?: number | null; longitude?: number | null }) =>
    put<unknown>('settings/weather', body),
  emailSettings: () => get<EmailImportSettings>('settings/email'),
  saveEmailSettings: (body: EmailImportIn) => put<EmailImportSettings>('settings/email', body),
  testEmail: (body: EmailImportIn) => post<{ ok: boolean; folders: string[]; matches: number }>('settings/email/test', body),
  runEmailImport: () => post<EmailImportRun>('settings/email/run'),
  forecast: (day?: string | null) => get<Forecast>(`settings/weather/forecast${query({ day })}`),

  suggestOutfits: (body: { owner?: string | null; occasion: string; count?: number; lang: string }) =>
    post<Outfit[]>('wardrobe/suggest', { count: 3, ...body }),
  outfitImageUrl: (id: number) => `api/wardrobe/outfits/${id}/image`,
  analyzeGarment: (files: Blob[]) => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    return post<GarmentAnalysis>('wardrobe/analyze', form)
  },

  scanLookup: (code: string) => get<ScanLookup>(`scan/lookup${query({ code })}`),
  scan: (code: string, mode: ScanMode, amount?: number | null) => post<ScanResult>('scan', { code, mode, amount: amount ?? null }),
  scanPhoto: (files: Blob[], hint?: string | null) => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    if (hint) form.append('hint', hint)
    return post<{ items: RecognizedItem[] }>('scan/photo', form)
  },
  addBarcode: (productId: number, code: string, amount = 1) => post<Product>(`products/${productId}/barcodes`, { code, amount }),
  removeBarcode: (productId: number, code: string) => request<Product>('DELETE', `products/${productId}/barcodes/${encodeURIComponent(code)}`),

  recipes: () => get<Recipe[]>('recipes'),
  recipe: (id: number) => get<Recipe>(`recipes/${id}`),
  createRecipe: (body: RecipeIn) => post<Recipe>('recipes', body),
  updateRecipe: (id: number, body: Partial<RecipeIn>) => patch<Recipe>(`recipes/${id}`, body),
  deleteRecipe: (id: number) => del(`recipes/${id}`),
  deleteRecipePhoto: (id: number) => request<Recipe>('DELETE', `recipes/${id}/photo`),
  setRecipePhoto: (id: number, file: Blob) => put<Recipe>(`recipes/${id}/photo`, upload(file)),
  importRecipe: (url: string) => post<Recipe>('recipes/import', { url }),
  recipeSuggestions: (limit = 6) => get<RecipeSuggestion[]>(`recipes/suggestions?limit=${limit}`),
  fulfillment: (id: number, servings?: number | null) => get<Fulfillment>(`recipes/${id}/fulfillment${query({ servings })}`),
  cook: (id: number, servings?: number | null) =>
    post<{ used: { product_id: number; name: string; amount: number; unit: string }[] }>(`recipes/${id}/cook`, { servings: servings ?? null }),
  recipeToShopping: (id: number, servings?: number | null) => post<{ added: string[] }>(`recipes/${id}/shopping`, { servings: servings ?? null }),
  parseIngredient: (text: string) =>
    post<{ text: string; name: string; amount: number | null; unit: string | null; optional: boolean }>('recipes/parse-ingredient', { text }),

  mealPlan: (start?: string | null, end?: string | null) => get<MealPlanEntry[]>(`mealplan${query({ start, end })}`),
  addMeal: (body: MealPlanIn) => post<MealPlanEntry>('mealplan', body),
  updateMeal: (id: number, body: Partial<MealPlanIn> & { done?: boolean }) => patch<MealPlanEntry>(`mealplan/${id}`, body),
  deleteMeal: (id: number) => del(`mealplan/${id}`),
  mealDone: (id: number, cook: boolean) => post<MealPlanEntry>(`mealplan/${id}/done?cook=${cook}`),
  mealPlanShopping: (start?: string | null, end?: string | null) => post<{ added: string[] }>(`mealplan/shopping${query({ start, end })}`),

  haDevices: (q?: string | null) => get<HaDevice[]>(`equipment/ha-devices${query({ q })}`),
  haEntities: (q?: string | null) => get<HaEntity[]>(`equipment/ha-entities${query({ q })}`),
  equipmentRuns: (id: number, limit = 10) => get<EquipmentRun[]>(`equipment/${id}/runs?limit=${limit}`),
  equipmentCommand: (id: number, command: string) =>
    post<{ result: { entity_id: string; state: string | null } }>(`equipment/${id}/command`, { command }),
  dismissLaundryPrompt: () => post<void>('wardrobe/laundry/dismiss'),

  laundryAdd: (garment_ids: number[]) => post<{ moved: number }>('wardrobe/laundry/add', { garment_ids }),
  laundryStillFine: (garment_ids: number[], wears?: number | null) => post<{ updated: number }>('wardrobe/laundry/still-fine', { garment_ids, wears: wears ?? null }),
  laundryStart: () => post<{ washing: number }>('wardrobe/laundry/start'),
  laundryDried: (garment_ids?: number[]) => post<{ dried: number }>('wardrobe/laundry/dried', { garment_ids: garment_ids ?? null }),
  wardrobeSettings: () => get<{ drying_hours: number | null }>('wardrobe/settings'),
  saveWardrobeSettings: (body: { drying_hours: number | null }) => put<{ drying_hours: number | null }>('wardrobe/settings', body),
}

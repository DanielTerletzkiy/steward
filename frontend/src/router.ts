import { createRouter, createWebHashHistory } from 'vue-router'

const views = {
  today: () => import('./views/TodayView.vue'),
  stock: () => import('./views/StockView.vue'),
  shopping: () => import('./views/ShoppingView.vue'),
  chores: () => import('./views/ChoresView.vue'),
  receipts: () => import('./views/ReceiptsView.vue'),
  receipt: () => import('./views/ReceiptDetailView.vue'),
  journal: () => import('./views/JournalView.vue'),
  wardrobe: () => import('./views/WardrobeView.vue'),
  equipment: () => import('./views/EquipmentView.vue'),
  equipmentDetail: () => import('./views/EquipmentDetailView.vue'),
  settings: () => import('./views/SettingsView.vue'),
  scan: () => import('./views/ScanView.vue'),
  recipes: () => import('./views/RecipesView.vue'),
  recipe: () => import('./views/RecipeDetailView.vue'),
  mealplan: () => import('./views/MealPlanView.vue'),
}

export const router = createRouter({
  // Hash history: the app lives under an unknown HA ingress prefix.
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'today', component: views.today },
    { path: '/stock', name: 'stock', component: views.stock },
    { path: '/shopping', name: 'shopping', component: views.shopping },
    { path: '/chores', name: 'chores', component: views.chores },
    { path: '/receipts', name: 'receipts', component: views.receipts },
    { path: '/receipts/:id', name: 'receipt', component: views.receipt, props: (r) => ({ id: Number(r.params.id) }) },
    { path: '/journal', name: 'journal', component: views.journal },
    { path: '/wardrobe', name: 'wardrobe', component: views.wardrobe },
    { path: '/equipment', name: 'equipment', component: views.equipment },
    { path: '/equipment/:id', name: 'equipment-detail', component: views.equipmentDetail, props: (r) => ({ id: Number(r.params.id) }) },
    { path: '/settings', name: 'settings', component: views.settings },
    { path: '/scan', name: 'scan', component: views.scan },
    { path: '/recipes', name: 'recipes', component: views.recipes },
    { path: '/recipes/:id', name: 'recipe', component: views.recipe, props: (r) => ({ id: Number(r.params.id) }) },
    { path: '/mealplan', name: 'mealplan', component: views.mealplan },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

// Fetch every page's code once the app is idle, so switching pages never waits on the network.
router.isReady().then(() => {
  const preload = () => Object.values(views).forEach((load) => load())
  if ('requestIdleCallback' in window) window.requestIdleCallback(preload)
  else setTimeout(preload, 1500)
})

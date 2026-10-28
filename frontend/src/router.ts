import { createRouter, createWebHashHistory } from 'vue-router'

export const router = createRouter({
  // Hash history: the app lives under an unknown HA ingress prefix.
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'today', component: () => import('./views/TodayView.vue') },
    { path: '/stock', name: 'stock', component: () => import('./views/StockView.vue') },
    { path: '/shopping', name: 'shopping', component: () => import('./views/ShoppingView.vue') },
    { path: '/chores', name: 'chores', component: () => import('./views/ChoresView.vue') },
    { path: '/receipts', name: 'receipts', component: () => import('./views/ReceiptsView.vue') },
    { path: '/receipts/:id', name: 'receipt', component: () => import('./views/ReceiptDetailView.vue'), props: (r) => ({ id: Number(r.params.id) }) },
    { path: '/journal', name: 'journal', component: () => import('./views/JournalView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

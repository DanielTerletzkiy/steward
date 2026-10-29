<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useDisplay, useTheme } from 'vuetify'
import { api } from '@/api'
import { LANG, LANGUAGES, setLanguage, t, type Language } from '@/i18n'
import { connected, reconnectNow } from '@/composables/live'
import { auth, loginUrl } from '@/composables/auth'
import { toasts } from '@/composables/notify'
import { initTheme } from '@/composables/theme'
import { useCatalog } from '@/composables/catalog'
import EmptyState from '@/components/EmptyState.vue'
import type { Me } from '@/types'

const theme = useTheme()
const { mdAndUp } = useDisplay()
const route = useRoute()
useCatalog()

type NavItem = { name: string; to: string; icon: string; activeIcon: string; label: string; long?: string }

const item = (name: string, to: string, icon: string, activeIcon: string, label: string, long?: string): NavItem => ({ name, to, icon, activeIcon, label, long })

// Desktop drawer groups: daily household, kitchen, the rest of the home.
const navGroups: NavItem[][] = [
  [
    item('today', '/', 'mdi-home-outline', 'mdi-home', t.nav.today),
    item('stock', '/stock', 'mdi-fridge-outline', 'mdi-fridge', t.nav.stock),
    item('shopping', '/shopping', 'mdi-cart-outline', 'mdi-cart', t.nav.shopping, t.nav.shoppingLong),
    item('chores', '/chores', 'mdi-checkbox-marked-circle-outline', 'mdi-checkbox-marked-circle', t.nav.chores),
  ],
  [
    item('recipes', '/recipes', 'mdi-book-open-variant-outline', 'mdi-book-open-variant', t.nav.recipes),
    item('mealplan', '/mealplan', 'mdi-calendar-month-outline', 'mdi-calendar-month', t.nav.mealplan),
  ],
  [
    item('wardrobe', '/wardrobe', 'mdi-hanger', 'mdi-hanger', t.nav.wardrobe),
    item('equipment', '/equipment', 'mdi-washing-machine', 'mdi-washing-machine', t.nav.equipment),
    item('receipts', '/receipts', 'mdi-receipt-text-outline', 'mdi-receipt-text', t.nav.receipts),
  ],
]
const extraNav: NavItem[] = [
  item('journal', '/journal', 'mdi-history', 'mdi-history', t.nav.journal),
  item('settings', '/settings', 'mdi-cog-outline', 'mdi-cog', t.nav.settings),
]
const scanItem = item('scan', '/scan', 'mdi-barcode-scan', 'mdi-barcode-scan', t.nav.scan)

// Phones: four sections in the bottom navigation, everything else in the "More" sheet.
const bottomNav = navGroups[0]
const moreNav: NavItem[] = [scanItem, ...navGroups.slice(1).flat(), ...extraNav]
const moreOpen = ref(false)

const languages = Object.entries(LANGUAGES) as [Language, string][]

const parents: Record<string, string> = { receipt: 'receipts', 'equipment-detail': 'equipment', recipe: 'recipes' }
const section = computed(() => {
  const name = String(route.name ?? 'today')
  return parents[name] ?? name
})
const inMore = computed(() => moreNav.some((i) => i.name === section.value))
// The kitchen terminal page is full screen: no navigation, no sign-in page.
const kiosk = computed(() => route.meta.kiosk === true)

const me = ref<Me | null>(null)

// Hide the "offline" hint during the first connect attempt.
const settled = ref(false)
onMounted(() => {
  initTheme(theme)
  window.setTimeout(() => (settled.value = true), 2500)
  api.me().then((m) => (me.value = m)).catch(() => undefined)
})
const showOffline = computed(() => settled.value && !connected.value && !auth.failed)

async function runToastAction() {
  const action = toasts.current?.action
  toasts.show = false
  await action?.run()
}
</script>

<template>
  <v-app>
    <v-navigation-drawer v-if="mdAndUp && !kiosk" permanent width="248" color="background" border="0">
      <div class="d-flex align-center px-5 pt-5 pb-3">
        <v-avatar color="primary" size="36" rounded="lg" class="mr-3"><v-icon icon="mdi-home-heart" /></v-avatar>
        <div>
          <div class="text-subtitle-1 font-weight-bold">{{ t.app.title }}</div>
          <div class="text-caption text-medium-emphasis d-flex align-center">
            <v-icon :icon="connected ? 'mdi-circle' : 'mdi-circle-outline'" :color="connected ? 'success' : 'warning'" size="8" class="mr-1" />
            {{ connected ? t.app.live : t.app.offlineShort }}
          </div>
        </div>
      </div>
      <div class="px-3 pb-2">
        <v-btn to="/scan" block color="primary" :variant="section === 'scan' ? 'flat' : 'tonal'" rounded="lg" height="44" prepend-icon="mdi-barcode-scan">{{ t.nav.scan }}</v-btn>
      </div>
      <v-list nav density="compact" color="primary" class="px-3">
        <template v-for="(group, gi) in navGroups" :key="gi">
          <v-divider v-if="gi > 0" class="my-2" />
          <v-list-item
            v-for="n in group"
            :key="n.name"
            :to="n.to"
            :active="section === n.name"
            :prepend-icon="section === n.name ? n.activeIcon : n.icon"
            :title="n.long ?? n.label"
            rounded="pill"
          />
        </template>
        <v-divider class="my-2" />
        <v-list-item
          v-for="n in extraNav"
          :key="n.name"
          :to="n.to"
          :active="section === n.name"
          :prepend-icon="section === n.name ? n.activeIcon : n.icon"
          :title="n.label"
          rounded="pill"
        />
        <v-menu location="top">
          <template #activator="{ props }">
            <v-list-item v-bind="props" prepend-icon="mdi-translate" :title="LANGUAGES[LANG]" :subtitle="t.app.language" rounded="pill" />
          </template>
          <v-list density="compact">
            <v-list-item v-for="[code, label] in languages" :key="code" :title="label" :active="code === LANG" @click="setLanguage(code)" />
          </v-list>
        </v-menu>
      </v-list>
      <template v-if="me?.user" #append>
        <v-divider />
        <v-list-item class="px-5 py-3" :title="me.user.name" :subtitle="t.auth.signedIn">
          <template #prepend>
            <v-avatar color="secondary" variant="tonal" size="32" class="text-body-2 font-weight-bold">{{ me.user.name.charAt(0).toUpperCase() }}</v-avatar>
          </template>
          <template v-if="me.can_sign_out" #append>
            <v-btn icon="mdi-logout" variant="text" size="small" href="auth/logout" :title="t.auth.signOut" />
          </template>
        </v-list-item>
      </template>
    </v-navigation-drawer>

    <v-app-bar v-if="!mdAndUp && !kiosk" flat density="comfortable" color="background">
      <template #prepend>
        <v-avatar color="primary" size="32" rounded="lg" class="ml-2"><v-icon icon="mdi-home-heart" size="20" /></v-avatar>
      </template>
      <v-app-bar-title class="font-weight-bold">{{ t.app.title }}</v-app-bar-title>
      <template #append>
        <v-btn v-if="showOffline" icon="mdi-cloud-off-outline" color="warning" :title="t.app.offline" @click="reconnectNow" />
        <v-btn icon="mdi-barcode-scan" to="/scan" :title="t.nav.scan" :active="section === 'scan'" />
        <v-menu>
          <template #activator="{ props }">
            <v-btn v-bind="props" icon="mdi-translate" :title="t.app.language" />
          </template>
          <v-list density="compact">
            <v-list-item v-for="[code, label] in languages" :key="code" :title="label" :active="code === LANG" @click="setLanguage(code)" />
          </v-list>
        </v-menu>
      </template>
    </v-app-bar>

    <v-main>
      <div v-if="auth.failed && !kiosk" class="page">
        <EmptyState icon="mdi-account-lock-outline" :title="t.auth.needed" :text="t.auth.neededHint">
          <v-btn color="primary" variant="flat" prepend-icon="mdi-login" :href="loginUrl()">{{ t.auth.signIn }}</v-btn>
        </EmptyState>
      </div>
      <template v-else>
        <v-alert
          v-if="showOffline && mdAndUp && !kiosk"
          type="warning"
          variant="tonal"
          density="compact"
          class="ma-4 mb-0"
          :text="t.app.offline"
        >
          <template #append><v-btn size="small" variant="text" @click="reconnectNow">{{ t.app.retry }}</v-btn></template>
        </v-alert>
        <router-view v-slot="{ Component }">
          <v-fade-transition hide-on-leave>
            <component :is="Component" />
          </v-fade-transition>
        </router-view>
      </template>
    </v-main>

    <v-bottom-navigation v-if="!mdAndUp && !kiosk" :model-value="inMore ? 'more' : section" grow color="primary" height="64">
      <v-btn v-for="n in bottomNav" :key="n.name" :value="n.name" :to="n.to">
        <v-icon :icon="section === n.name ? n.activeIcon : n.icon" />
        <span>{{ n.label }}</span>
      </v-btn>
      <v-btn value="more" @click="moreOpen = true">
        <v-icon :icon="inMore ? 'mdi-dots-horizontal-circle' : 'mdi-dots-horizontal-circle-outline'" />
        <span>{{ t.nav.more }}</span>
      </v-btn>
    </v-bottom-navigation>

    <v-bottom-sheet v-if="!mdAndUp" v-model="moreOpen">
      <v-card rounded="t-xl" class="pb-3">
        <div class="d-flex justify-center pt-2 pb-2"><div class="sheet-handle" /></div>
        <div class="more-grid px-3">
          <v-btn
            v-for="n in moreNav"
            :key="n.name"
            :to="n.to"
            :color="section === n.name ? 'primary' : undefined"
            :variant="section === n.name ? 'tonal' : 'text'"
            rounded="lg"
            height="76"
            class="more-tile"
            stacked
            @click="moreOpen = false"
          >
            <v-icon :icon="section === n.name ? n.activeIcon : n.icon" size="26" class="mb-1" />
            <span class="text-caption more-label">{{ n.label }}</span>
          </v-btn>
        </div>
        <template v-if="me?.user">
          <v-divider class="mt-2" />
          <v-list-item class="px-5 pt-3" :title="me.user.name" :subtitle="t.auth.signedIn">
            <template #prepend>
              <v-avatar color="secondary" variant="tonal" size="32" class="text-body-2 font-weight-bold">{{ me.user.name.charAt(0).toUpperCase() }}</v-avatar>
            </template>
            <template v-if="me.can_sign_out" #append>
              <v-btn variant="text" size="small" prepend-icon="mdi-logout" href="auth/logout">{{ t.auth.signOut }}</v-btn>
            </template>
          </v-list-item>
        </template>
      </v-card>
    </v-bottom-sheet>

    <v-snackbar
      v-model="toasts.show"
      :key="toasts.current?.id"
      :timeout="toasts.current?.timeout ?? 3500"
      :color="toasts.current?.color"
      location="bottom"
      :class="mdAndUp || kiosk ? '' : 'mb-16'"
      rounded="lg"
    >
      {{ toasts.current?.text }}
      <template v-if="toasts.current?.action" #actions>
        <v-btn color="primary" variant="text" class="font-weight-bold" @click="runToastAction">{{ toasts.current.action.label }}</v-btn>
      </template>
    </v-snackbar>
  </v-app>
</template>

<style scoped>
.sheet-handle {
  width: 32px;
  height: 4px;
  border-radius: 2px;
  background: rgba(var(--v-theme-on-surface), 0.3);
}
.more-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 4px;
}
.more-tile {
  min-width: 0 !important;
  padding: 0 4px !important;
}
.more-label {
  white-space: normal;
  line-height: 1.15;
  text-align: center;
  letter-spacing: normal;
  text-transform: none;
}
</style>

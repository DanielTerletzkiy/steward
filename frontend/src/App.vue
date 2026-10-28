<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useDisplay, useTheme } from 'vuetify'
import { LANG, LANGUAGES, setLanguage, t, type Language } from '@/i18n'
import { connected, reconnectNow } from '@/composables/live'
import { toasts } from '@/composables/notify'
import { initTheme } from '@/composables/theme'
import { useCatalog } from '@/composables/catalog'

const theme = useTheme()
const { mdAndUp } = useDisplay()
const route = useRoute()
useCatalog()

const nav = [
  { name: 'today', to: '/', icon: 'mdi-home-outline', activeIcon: 'mdi-home', label: t.nav.today },
  { name: 'stock', to: '/stock', icon: 'mdi-fridge-outline', activeIcon: 'mdi-fridge', label: t.nav.stock },
  { name: 'shopping', to: '/shopping', icon: 'mdi-cart-outline', activeIcon: 'mdi-cart', label: t.nav.shopping, long: t.nav.shoppingLong },
  { name: 'chores', to: '/chores', icon: 'mdi-checkbox-marked-circle-outline', activeIcon: 'mdi-checkbox-marked-circle', label: t.nav.chores },
  { name: 'receipts', to: '/receipts', icon: 'mdi-receipt-text-outline', activeIcon: 'mdi-receipt-text', label: t.nav.receipts },
]
const extraNav = [{ name: 'journal', to: '/journal', icon: 'mdi-history', activeIcon: 'mdi-history', label: t.nav.journal }]

const languages = Object.entries(LANGUAGES) as [Language, string][]

const section = computed(() => (route.name === 'receipt' ? 'receipts' : String(route.name ?? 'today')))

// Hide the "offline" hint during the first connect attempt.
const settled = ref(false)
onMounted(() => {
  initTheme(theme)
  window.setTimeout(() => (settled.value = true), 2500)
})
const showOffline = computed(() => settled.value && !connected.value)

async function runToastAction() {
  const action = toasts.current?.action
  toasts.show = false
  await action?.run()
}
</script>

<template>
  <v-app>
    <v-navigation-drawer v-if="mdAndUp" permanent width="248" color="background" border="0">
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
      <v-list nav density="comfortable" color="primary" class="px-3">
        <v-list-item
          v-for="item in nav"
          :key="item.name"
          :to="item.to"
          :active="section === item.name"
          :prepend-icon="section === item.name ? item.activeIcon : item.icon"
          :title="item.long ?? item.label"
          rounded="pill"
        />
        <v-divider class="my-2" />
        <v-list-item
          v-for="item in extraNav"
          :key="item.name"
          :to="item.to"
          :active="section === item.name"
          :prepend-icon="item.icon"
          :title="item.label"
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
    </v-navigation-drawer>

    <v-app-bar v-if="!mdAndUp" flat density="comfortable" color="background">
      <template #prepend>
        <v-avatar color="primary" size="32" rounded="lg" class="ml-2"><v-icon icon="mdi-home-heart" size="20" /></v-avatar>
      </template>
      <v-app-bar-title class="font-weight-bold">{{ t.app.title }}</v-app-bar-title>
      <template #append>
        <v-btn v-if="showOffline" icon="mdi-cloud-off-outline" color="warning" :title="t.app.offline" @click="reconnectNow" />
        <v-btn icon="mdi-history" to="/journal" :title="t.nav.journal" :active="section === 'journal'" />
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
      <v-alert
        v-if="showOffline && mdAndUp"
        type="warning"
        variant="tonal"
        density="compact"
        class="ma-4 mb-0"
        :text="t.app.offline"
      >
        <template #append><v-btn size="small" variant="text" @click="reconnectNow">{{ t.app.retry }}</v-btn></template>
      </v-alert>
      <router-view v-slot="{ Component }">
        <v-fade-transition mode="out-in" hide-on-leave>
          <component :is="Component" />
        </v-fade-transition>
      </router-view>
    </v-main>

    <v-bottom-navigation v-if="!mdAndUp" :model-value="section" grow color="primary" height="64">
      <v-btn v-for="item in nav" :key="item.name" :value="item.name" :to="item.to">
        <v-icon :icon="section === item.name ? item.activeIcon : item.icon" />
        <span>{{ item.label }}</span>
      </v-btn>
    </v-bottom-navigation>

    <v-snackbar
      v-model="toasts.show"
      :key="toasts.current?.id"
      :timeout="toasts.current?.timeout ?? 3500"
      :color="toasts.current?.color"
      location="bottom"
      :class="mdAndUp ? '' : 'mb-16'"
      rounded="lg"
    >
      {{ toasts.current?.text }}
      <template v-if="toasts.current?.action" #actions>
        <v-btn color="primary" variant="text" class="font-weight-bold" @click="runToastAction">{{ toasts.current.action.label }}</v-btn>
      </template>
    </v-snackbar>
  </v-app>
</template>

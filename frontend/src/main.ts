import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import { vuetify } from './plugins/vuetify'
import { startLive } from './composables/live'
import './styles.css'

startLive()
createApp(App).use(vuetify).use(router).mount('#app')

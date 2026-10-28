import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'
import { md3 } from 'vuetify/blueprints'
import { de, en } from 'vuetify/locale'
import { LANG, LOCALE } from '@/i18n'

const prefersDark = typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches

export const vuetify = createVuetify({
  blueprint: md3,
  locale: { locale: LANG, fallback: 'en', messages: { de, en } },
  date: { locale: { [LANG]: LOCALE } },
  theme: {
    defaultTheme: prefersDark ? 'dark' : 'light',
    themes: {
      light: {
        dark: false,
        colors: {
          primary: '#00796b',
          secondary: '#4a635f',
          tertiary: '#456179',
          background: '#f4fbf8',
          surface: '#ffffff',
          'surface-variant': '#dae5e1',
          'surface-container': '#e9efec',
          error: '#ba1a1a',
          warning: '#b26a00',
          success: '#2e7d32',
          info: '#0061a4',
        },
      },
      dark: {
        dark: true,
        colors: {
          primary: '#4fd8c4',
          secondary: '#b1ccc6',
          tertiary: '#adcae6',
          background: '#0e1513',
          surface: '#161d1b',
          'surface-variant': '#3f4946',
          'surface-container': '#1e2624',
          error: '#ffb4ab',
          warning: '#ffb952',
          success: '#81c784',
          info: '#9ecaff',
        },
      },
    },
  },
  defaults: {
    VCard: { rounded: 'xl' },
    VBtn: { style: 'text-transform: none; letter-spacing: normal;' },
    VTextField: { variant: 'outlined', density: 'comfortable' },
    VSelect: { variant: 'outlined', density: 'comfortable' },
    VAutocomplete: { variant: 'outlined', density: 'comfortable' },
    VCombobox: { variant: 'outlined', density: 'comfortable' },
    VTextarea: { variant: 'outlined', density: 'comfortable' },
    VChip: { size: 'small' },
  },
})

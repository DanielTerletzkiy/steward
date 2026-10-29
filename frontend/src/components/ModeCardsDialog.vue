<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import JsBarcode from 'jsbarcode'
import { t } from '@/i18n'

// Printable mode cards for the kitchen terminal: scanning one switches the terminal to that mode.
// Code 128, which every 1D scanner reads (cheap laser scanners can't read QR codes).
const open = defineModel<boolean>({ default: false })

const CARDS = [
  { mode: 'consume', icon: 'mdi-silverware-fork-knife' },
  { mode: 'purchase', icon: 'mdi-cart-arrow-down' },
  { mode: 'open', icon: 'mdi-package-variant' },
  { mode: 'spoil', icon: 'mdi-delete-variant' },
  { mode: 'shopping', icon: 'mdi-cart-plus' },
] as const
const code = (mode: string) => `STEWARD-MODE-${mode.toUpperCase()}`

const svgs = ref<Record<string, SVGSVGElement | null>>({})
watch(open, async (isOpen) => {
  if (!isOpen) return
  await nextTick()
  for (const { mode } of CARDS) {
    const el = svgs.value[mode]
    if (!el) continue
    // A white margin (quiet zone) around the bars, which scanners need. The viewBox lets the code scale
    // to the card's width without cutting it off.
    JsBarcode(el, code(mode), { format: 'CODE128', width: 2, height: 70, displayValue: false, margin: 12, background: '#ffffff' })
    el.setAttribute('viewBox', `0 0 ${el.getAttribute('width')?.replace('px', '')} ${el.getAttribute('height')?.replace('px', '')}`)
    el.removeAttribute('width')
    el.removeAttribute('height')
  }
})

function print() {
  // A separate page with just the cards, so the browser prints nothing else.
  const cards = CARDS.map(
    ({ mode }) => `<div class="card"><div class="label">${t.kiosk.modes[mode]}</div>${svgs.value[mode]?.outerHTML ?? ''}<div class="code">${code(mode)}</div></div>`,
  ).join('')
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>${t.terminals.modeCards}</title><style>
    body { font: 16px system-ui, sans-serif; margin: 12mm; }
    .grid { display: grid; grid-template-columns: repeat(2, 85mm); gap: 8mm; }
    .card { border: 1px dashed #999; border-radius: 3mm; padding: 6mm; text-align: center; break-inside: avoid; }
    .label { font-size: 22pt; font-weight: 700; margin-bottom: 4mm; }
    svg { width: 100%; height: auto; }
    .code { font: 9pt ui-monospace, monospace; color: #666; margin-top: 2mm; }
  </style></head><body><div class="grid">${cards}</div><script>window.onload = () => window.print()<\/script></body></html>`
  const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
  window.open(url, '_blank')
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
</script>

<template>
  <v-dialog v-model="open" max-width="720">
    <v-card :title="t.terminals.modeCards">
      <v-card-text>
        <p class="text-body-2 text-medium-emphasis mb-4">{{ t.terminals.modeCardsIntro }}</p>
        <div class="cards">
          <v-card v-for="c in CARDS" :key="c.mode" variant="outlined" class="pa-4 text-center">
            <div class="text-h6 font-weight-bold mb-2"><v-icon :icon="c.icon" size="22" class="mr-1" />{{ t.kiosk.modes[c.mode] }}</div>
            <svg :ref="(el) => (svgs[c.mode] = el as SVGSVGElement | null)" class="code" />
          </v-card>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="open = false">{{ t.common.close }}</v-btn>
        <v-btn color="primary" variant="flat" prepend-icon="mdi-printer-outline" @click="print">{{ t.terminals.print }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.code {
  width: 100%;
  height: auto;
  display: block;
  border-radius: 4px;
}
</style>

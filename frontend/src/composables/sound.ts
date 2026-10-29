// Short tones for the kiosk page, made with Web Audio (no sound files). Silent where there is no speaker.
let context: AudioContext | null = null

function tone(freq: number, start: number, length: number, type: OscillatorType = 'sine') {
  if (!context) return
  const osc = context.createOscillator()
  const gain = context.createGain()
  osc.type = type
  osc.frequency.value = freq
  const t0 = context.currentTime + start
  gain.gain.setValueAtTime(0.0001, t0)
  gain.gain.exponentialRampToValueAtTime(0.25, t0 + 0.01)
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + length)
  osc.connect(gain).connect(context.destination)
  osc.start(t0)
  osc.stop(t0 + length + 0.02)
}

function ready(): boolean {
  try {
    context ??= new AudioContext()
    if (context.state === 'suspended') context.resume().catch(() => undefined)
    return true
  } catch {
    return false
  }
}

export function beepOk() {
  if (!ready()) return
  tone(1320, 0, 0.08)
  tone(1760, 0.09, 0.1)
}

export function beepError() {
  if (!ready()) return
  tone(220, 0, 0.18, 'square')
  tone(180, 0.2, 0.25, 'square')
}

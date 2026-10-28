// One WebSocket to api/ws for the whole app. Views subscribe to topics and refetch on events.
import { onBeforeUnmount, ref } from 'vue'
import type { Topic } from '@/types'

type Listener = (topic: Topic | '*') => void

const listeners = new Set<{ topics: Set<string>; fn: Listener }>()
export const connected = ref(false)
export const everConnected = ref(false)

let socket: WebSocket | null = null
let attempt = 0
let retryTimer: number | undefined
let pingTimer: number | undefined

function wsUrl(): string {
  const url = new URL('api/ws', window.location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.hash = ''
  return url.toString()
}

function emit(topic: Topic | '*') {
  for (const l of listeners) {
    if (topic === '*' || l.topics.has(topic)) l.fn(topic)
  }
}

function connect() {
  window.clearTimeout(retryTimer)
  try {
    socket = new WebSocket(wsUrl())
  } catch {
    scheduleReconnect()
    return
  }
  socket.onopen = () => {
    const wasReconnect = everConnected.value
    connected.value = true
    everConnected.value = true
    attempt = 0
    window.clearInterval(pingTimer)
    pingTimer = window.setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send('{"type":"ping"}'), 30000)
    // We may have missed events while disconnected: refresh everything.
    if (wasReconnect) emit('*')
  }
  socket.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'event' && typeof msg.topic === 'string') emit(msg.topic)
    } catch {
      /* ignore */
    }
  }
  socket.onclose = () => {
    connected.value = false
    window.clearInterval(pingTimer)
    socket = null
    scheduleReconnect()
  }
  socket.onerror = () => socket?.close()
}

function scheduleReconnect() {
  const delay = Math.min(30000, 1000 * 2 ** attempt) * (0.75 + Math.random() * 0.5)
  attempt++
  retryTimer = window.setTimeout(connect, delay)
}

export function startLive() {
  if (!socket) connect()
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && !connected.value) {
      attempt = 0
      connect()
    }
  })
}

export function reconnectNow() {
  attempt = 0
  socket?.close()
  if (!socket) connect()
}

/** Call `fn` (debounced) whenever one of `topics` changes. Unsubscribes with the component. */
export function onTopics(topics: Topic[], fn: () => void, debounceMs = 150) {
  let timer: number | undefined
  const entry = {
    topics: new Set<string>(topics),
    fn: () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(fn, debounceMs)
    },
  }
  listeners.add(entry)
  onBeforeUnmount(() => {
    listeners.delete(entry)
    window.clearTimeout(timer)
  })
}

/** Global (non-component) subscription; returns an unsubscribe function. */
export function subscribe(topics: Topic[], fn: () => void): () => void {
  const entry = { topics: new Set<string>(topics), fn: () => fn() }
  listeners.add(entry)
  return () => listeners.delete(entry)
}

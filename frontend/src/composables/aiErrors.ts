// What went wrong with an AI call: not set up (409), the AI or Home Assistant failed (502/503), or something else.
import { ApiError } from '@/api'

export type AiProblem = { kind: 'setup' | 'failed' | 'other'; message: string }

export function aiProblem(e: unknown): AiProblem {
  const message = e instanceof Error ? e.message : String(e)
  if (e instanceof ApiError && e.status === 409) return { kind: 'setup', message }
  if (e instanceof ApiError && (e.status === 502 || e.status === 503 || e.status === 504)) return { kind: 'failed', message }
  return { kind: 'other', message }
}

import { onMounted, ref, shallowRef, type Ref } from 'vue'
import { onTopics } from './live'
import type { Topic } from '@/types'

/** Load data on mount, refetch on live events, keep the last good value while refreshing. */
export function useResource<T>(fetcher: () => Promise<T>, topics: Topic[], initial: T) {
  const data = shallowRef<T>(initial) as Ref<T>
  const loading = ref(true)
  const error = ref<string | null>(null)
  let seq = 0

  async function reload() {
    const mine = ++seq
    try {
      const value = await fetcher()
      if (mine !== seq) return
      data.value = value
      error.value = null
    } catch (e) {
      if (mine !== seq) return
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  onMounted(reload)
  onTopics(topics, reload)
  return { data, loading, error, reload }
}

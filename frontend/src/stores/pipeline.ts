// Synchronize authoritative run snapshots through polling and optional server events.
import { computed, onScopeDispose, ref } from 'vue'
import { defineStore } from 'pinia'
import type { Run, Profile, Preferences, ModelOption } from '../types/domain'

// Decode API responses and turn failed HTTP requests into actionable errors.
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item: { msg: string }) => item.msg).join('; ')
      : data.detail
    throw Object.assign(new Error(detail || `Request failed (${response.status}). Please retry.`), {
      status: response.status,
    })
  }
  return data
}

export const usePipelineStore = defineStore('pipeline', () => {
  // Reactive server state is separate from connection and submission status.
  const run = ref<Run | null>(null)
  const runId = ref('')
  const error = ref('')
  const connecting = ref(false)
  const reconnecting = ref(false)
  const busy = ref(false)
  const activeAction = ref('')
  const modelOptions = ref<ModelOption[]>([])
  const profileOptions = ref<ModelOption[]>([])
  const defaultEvaluation = ref('claude')
  const running = computed(() => run.value?.status === 'running' || !!run.value?.worker_active)
  // Generation tokens prevent old requests from updating a newly attached workspace.
  let version = 0
  let stream: EventSource | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let failures = 0
  let controller: AbortController | undefined

  // Invalidate outstanding callbacks and release streams, timers, and requests.
  function stop() {
    version++
    stream?.close()
    stream = undefined
    clearTimeout(timer)
    controller?.abort()
    controller = undefined
  }
  // Ignore stale snapshots and stop live updates once worker activity ends.
  function accept(data: Run) {
    if (data.id !== runId.value) return
    if (run.value?.id === data.id && (run.value.revision || 0) > (data.revision || 0)) return
    run.value = data
    connecting.value = false
    if (data.status !== 'running' && !data.worker_active) {
      stream?.close()
      stream = undefined
      clearTimeout(timer)
    }
  }
  // Fetch authoritative state with timeout and backoff, ignoring outdated requests.
  async function poll(token: number) {
    if (token !== version || !runId.value) return
    const request = new AbortController()
    controller = request
    const timeout = setTimeout(() => request.abort(), 15000)
    try {
      const data = await api<Run>(`/api/searches/${encodeURIComponent(runId.value)}`, {
        signal: request.signal,
        cache: 'no-store',
      })
      if (token !== version) return
      accept(data)
      failures = 0
      reconnecting.value = false
      error.value = ''
    } catch (cause) {
      if (token !== version) return
      error.value = (cause as Error).message
      if ((cause as Error & { status?: number }).status === 404) {
        stop()
        run.value = null
        reconnecting.value = false
        connecting.value = false
        return
      }
      failures++
      reconnecting.value = true
    } finally {
      clearTimeout(timeout)
      if (controller === request) controller = undefined
      if (token === version) {
        connecting.value = false
        if (reconnecting.value || running.value)
          timer = setTimeout(() => poll(token), Math.min(1500 * 2 ** Math.min(failures, 3), 15000))
      }
    }
  }
  // Consume progress events while retaining polling as the recovery path.
  function connectStream(token: number) {
    if (!running.value || typeof EventSource === 'undefined' || token !== version) return
    stream = new EventSource(`/api/searches/${encodeURIComponent(runId.value)}/progress`)
    const source = stream
    for (const type of [
      'phase_update',
      'profile_extracted',
      'scrape_progress',
      'run_completed',
      'run_failed',
    ]) {
      source.addEventListener(type, (event) => {
        if (token !== version) return
        try {
          accept(JSON.parse((event as MessageEvent).data))
          reconnecting.value = false
        } catch {
          /* polling repairs invalid events */
        }
      })
    }
    source.addEventListener('run_deleted', () => {
      stop()
      run.value = null
      error.value = 'This run was deleted.'
    })
    source.onerror = () => {
      if (token !== version) return
      source.close()
      stream = undefined
      // Snapshots continue on the existing polling timer even if streaming is unavailable.
    }
  }
  // Reconnect to a workspace without starting a new search.
  async function attach(id: string) {
    stop()
    if (id !== runId.value) run.value = null
    runId.value = id
    error.value = ''
    connecting.value = true
    try {
      sessionStorage.setItem('careerActiveRunId', id)
    } catch {
      /* optional recovery */
    }
    const token = version
    await poll(token)
    connectStream(token)
  }
  // Load supported model choices and public defaults concurrently.
  async function loadModels() {
    const [profiles, evaluations, config] = await Promise.all([
      api<ModelOption[]>('/api/models/resume'),
      api<ModelOption[]>('/api/models/evaluation'),
      api<{ evaluation_provider: string }>('/api/config'),
    ])
    profileOptions.value = profiles
    modelOptions.value = evaluations
    defaultEvaluation.value = config.evaluation_provider
  }
  // Create a resume extraction run using multipart form data.
  async function upload(file: File, model: string) {
    busy.value = true
    error.value = ''
    try {
      const body = new FormData()
      body.append('resume', file)
      body.append('model', model)
      const data = await api<{ runId: string }>('/api/resumes/upload', { method: 'POST', body })
      return data.runId
    } catch (cause) {
      error.value = (cause as Error).message
      return null
    } finally {
      busy.value = false
    }
  }
  // Submit the candidate draft and normalized preferences, then attach to progress.
  async function confirm(profile: Profile, preferences: Preferences) {
    busy.value = true
    error.value = ''
    const locations = (preferences.locations || []).map((value) => value.trim()).filter(Boolean)
    const { evaluation_model: _legacyModel, ...automaticPreferences } = preferences
    const searchPreferences = {
      ...automaticPreferences,
      locations: locations.length ? locations : ['Worldwide'],
    }
    try {
      await api(`/api/searches/${runId.value}/confirm-profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile, preferences: searchPreferences }),
      })
      await attach(runId.value)
      return true
    } catch (cause) {
      error.value = (cause as Error).message
      return false
    } finally {
      busy.value = false
    }
  }
  // Submit only preferences so additional results stay in the same workspace.
  async function findMore(preferences: Preferences) {
    busy.value = true
    error.value = ''
    const { evaluation_model: _legacyModel, ...automaticPreferences } = preferences
    const locations = (preferences.locations || []).map((value) => value.trim()).filter(Boolean)
    try {
      await api(`/api/searches/${encodeURIComponent(runId.value)}/find-more`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preferences: {
            ...automaticPreferences,
            locations: locations.length ? locations : ['Worldwide'],
          },
        }),
      })
      await attach(runId.value)
      return true
    } catch (cause) {
      error.value = (cause as Error).message
      return false
    } finally {
      busy.value = false
    }
  }
  // Request cancellation or targeted evaluation retry, then refresh the snapshot.
  async function action(kind: 'cancel' | 'retry-evaluation' | 'retry-scraping') {
    if (busy.value) return
    busy.value = true
    activeAction.value = kind
    error.value = ''
    try {
      await api(
        `/api/searches/${runId.value}/${kind === 'retry-evaluation' ? 'retry-evaluations' : kind}`,
        { method: 'POST' },
      )
      await attach(runId.value)
    } catch (cause) {
      error.value = (cause as Error).message
    } finally {
      activeAction.value = ''
      busy.value = false
    }
  }
  // Delete this workspace and clear its browser-local session and action state.
  async function deleteData() {
    busy.value = true
    try {
      const result = await api<{ deletion_pending: boolean }>(`/api/searches/${runId.value}`, {
        method: 'DELETE',
      })
      stop()
      run.value = null
      try {
        sessionStorage.removeItem('careerActiveRunId')
        localStorage.removeItem(`career-actions:${runId.value}`)
      } catch {
        /* storage unavailable */
      }
      runId.value = ''
      return result
    } catch (cause) {
      error.value = (cause as Error).message
      return null
    } finally {
      busy.value = false
    }
  }
  // Reattach when connectivity returns instead of resubmitting paid work.
  function wake() {
    if (runId.value) void attach(runId.value)
  }
  // Restore connectivity listeners only for this store’s lifetime.
  if (typeof window !== 'undefined') window.addEventListener('online', wake)
  onScopeDispose(() => {
    stop()
    if (typeof window !== 'undefined') window.removeEventListener('online', wake)
  })
  return {
    run,
    runId,
    error,
    connecting,
    reconnecting,
    busy,
    activeAction,
    running,
    modelOptions,
    profileOptions,
    defaultEvaluation,
    attach,
    stop,
    loadModels,
    upload,
    confirm,
    findMore,
    action,
    deleteData,
  }
})

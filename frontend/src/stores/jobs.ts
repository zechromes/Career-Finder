// Keep local compatibility flags and synchronize stable job identities to the owning profile.
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Job, Run } from '../types/domain'
import type { components } from '../types/api'
export type DismissalInput = components['schemas']['DismissalInput']
type Feedback = Record<string, components['schemas']['DismissalPreference']>
type ActionResponse = components['schemas']['JobActions']
import { api } from './pipeline'
export type JobAction = 'saved' | 'dismissed' | 'applied'
type Flags = Record<string, Partial<Record<JobAction, boolean>>>
export function jobKey(job: Job) {
  return job.jobId || job.apply_url || `${job.title}|${job.company}|${job.location}`
}
export function jobActionKey(job: Job) {
  try {
    const url = new URL(job.apply_url || '')
    if (!['https:', 'http:'].includes(url.protocol)) return jobKey(job)
    url.hash = ''
    for (const key of [...url.searchParams.keys()]) {
      if (/^(utm_|trk$|trackingId$|ref$|source$)/i.test(key)) url.searchParams.delete(key)
    }
    url.searchParams.sort()
    return url.toString().replace(/\/$/, '')
  } catch {
    return jobKey(job)
  }
}
export const useJobsStore = defineStore('jobs', () => {
  const actions = ref<Flags>({})
  const storageError = ref('')
  const feedback = ref<Feedback>({})
  const dismissTarget = ref<Job | null>(null)
  let pendingFeedback: Record<string, DismissalInput | null> = {}
  let pending: Flags = {}
  let activeRun = ''
  let generation = 0
  let editVersion = 0
  let writes = Promise.resolve()
  function persist() {
    try {
      localStorage.setItem(`career-feedback:${activeRun}`, JSON.stringify(feedback.value))
      localStorage.setItem(`career-feedback-pending:${activeRun}`, JSON.stringify(pendingFeedback))
      localStorage.setItem(`career-actions:${activeRun}`, JSON.stringify(actions.value))
      localStorage.setItem(`career-actions-pending:${activeRun}`, JSON.stringify(pending))
    } catch {
      storageError.value = 'Could not save job actions in this browser.'
    }
  }
  function load(id: string) {
    generation++
    activeRun = id
    actions.value = {}
    pending = {}
    feedback.value = {}
    pendingFeedback = {}
    dismissTarget.value = null
    storageError.value = ''
    try {
      feedback.value = JSON.parse(localStorage.getItem(`career-feedback:${id}`) || '{}')
      pendingFeedback = JSON.parse(localStorage.getItem(`career-feedback-pending:${id}`) || '{}')
      actions.value = JSON.parse(localStorage.getItem(`career-actions:${id}`) || '{}')
      pending = JSON.parse(localStorage.getItem(`career-actions-pending:${id}`) || '{}')
    } catch {
      storageError.value =
        'Browser storage is unavailable. Job actions will last only for this visit.'
    }
  }
  function flags(job: Job) {
    return { ...actions.value[jobKey(job)], ...actions.value[jobActionKey(job)] }
  }
  async function sync(run: Run) {
    const token = generation
    const version = editVersion
    const id = activeRun
    if (run.id !== id) return
    try {
      const server = await api<ActionResponse>(`/api/searches/${id}/actions`)
      if (token !== generation) return
      if (version === editVersion) {
        const serverFeedback = { ...(server.dismissal_feedback || {}) }
        for (const key of Object.keys(pendingFeedback)) {
          if (feedback.value[key]) serverFeedback[key] = feedback.value[key]
          else delete serverFeedback[key]
        }
        feedback.value = serverFeedback
      }
      const legacy = { ...actions.value }
      actions.value =
        version === editVersion
          ? { ...legacy, ...server.actions }
          : { ...server.actions, ...legacy }
      for (const job of [...(run.recommendations || []), ...(run.excluded_recommendations || [])]) {
        const key = jobActionKey(job)
        const previous = legacy[key] || legacy[jobKey(job)]
        for (const action of ['saved', 'dismissed', 'applied'] as const) {
          if (previous?.[action] !== undefined && server.actions?.[key]?.[action] === undefined) {
            pending[key] = { ...pending[key], [action]: previous[action] }
          }
        }
      }
      for (const [key, changes] of Object.entries(pending)) {
        actions.value[key] = { ...actions.value[key], ...changes }
        for (const [action, value] of Object.entries(changes)) {
          enqueue(id, token, key, action as JobAction, value!)
        }
      }
      if (token === generation) persist()
    } catch {
      if (token === generation)
        storageError.value = 'Could not sync saved job actions. Local flags remain available.'
    }
  }
  function toggle(job: Job, action: JobAction) {
    setAction(job, action, !flags(job)[action])
  }
  function dismiss(job: Job, details: DismissalInput | null) {
    setAction(job, 'dismissed', true, details)
    dismissTarget.value = null
  }
  function forgetFeedback(key: string) {
    setAction({ apply_url: key } as Job, 'dismissed', true, null, key)
  }
  function setAction(
    job: Job,
    action: JobAction,
    value: boolean,
    details: DismissalInput | null = null,
    suppliedKey?: string,
  ) {
    editVersion++
    const key = suppliedKey || jobActionKey(job)
    if (action === 'dismissed') {
      pendingFeedback[key] = value ? details : null
      if (value && details)
        feedback.value[key] = {
          ...details,
          title: job.title || '',
          location: job.location || '',
          seniority: '',
        }
      else delete feedback.value[key]
    }
    actions.value[key] = { ...flags(job), [action]: value }
    pending[key] = { ...pending[key], [action]: value }
    persist()
    const id = activeRun
    const token = generation
    if (!id) return
    enqueue(id, token, key, action, value)
  }
  function enqueue(id: string, token: number, key: string, action: JobAction, value: boolean) {
    const details = action === 'dismissed' ? pendingFeedback[key] : undefined
    const stamp = JSON.stringify(details)
    const isCurrent = () =>
      pending[key]?.[action] === value &&
      (action !== 'dismissed' || JSON.stringify(pendingFeedback[key]) === stamp)
    writes = writes.then(async () => {
      if (token !== generation) return
      // A later edit replaces a queued older value.
      if (!isCurrent()) return
      try {
        const response = await api<ActionResponse>(`/api/searches/${id}/actions`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            key,
            action,
            value,
            ...(details !== undefined ? { dismissal: details } : {}),
          }),
        })
        if (token === generation && isCurrent()) {
          if (action === 'dismissed') {
            delete pendingFeedback[key]
            if (response?.dismissal_feedback) {
              if (response.dismissal_feedback[key])
                feedback.value[key] = response.dismissal_feedback[key]
              else delete feedback.value[key]
            }
          }
          // A GET started after the click can still contain the pre-save value.
          // Invalidate that snapshot before clearing the pending edit, otherwise
          // its late response can overwrite this confirmed action.
          editVersion++
          delete pending[key][action]
          if (!Object.keys(pending[key]).length) delete pending[key]
          if (!Object.keys(pending).length) storageError.value = ''
          persist()
        }
      } catch {
        if (token === generation)
          storageError.value =
            'Job action saved locally. Server sync will retry when this search is opened again.'
      }
    })
  }
  return {
    actions,
    feedback,
    dismissTarget,
    storageError,
    load,
    toggle,
    dismiss,
    forgetFeedback,
    flags,
    sync,
  }
})

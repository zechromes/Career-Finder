<!-- Spot check for postings merged as duplicates: were they really the same job? -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../stores/pipeline'
import type { components } from '../types/api'
type S = components['schemas']
const props = defineProps<{ datasetId: string; bundle: S['ReviewBundle'] }>()
const emit = defineEmits<{ saved: [labels: S['ReviewState']] }>()
const reviewer = ref('')
const error = ref('')
const busy = ref(false)
const pairs = computed(() =>
  (props.bundle.dataset.dropped_jobs || []).filter((job) => job.duplicate_of),
)
const judged = (id: string) => props.bundle.labels.jobs?.[id]?.duplicate_correct
async function judge(job: S['DroppedJob'], same: boolean) {
  if (!reviewer.value.trim()) {
    error.value = 'Enter your name or initials first.'
    return
  }
  busy.value = true
  error.value = ''
  const existing = props.bundle.labels.jobs?.[job.id]
  try {
    emit(
      'saved',
      await api<S['ReviewState']>(`/api/review-datasets/${props.datasetId}/jobs/${job.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          revision: props.bundle.labels.revision || 0,
          reviewer: reviewer.value.trim(),
          review: {
            ai_assisted: false,
            notes: '',
            extraction_complete: false,
            ...existing,
            duplicate_correct: same,
          },
        }),
      }),
    )
    try {
      localStorage.setItem('career-reviewer-name', reviewer.value.trim())
    } catch {
      // Remembering the name is a convenience only.
    }
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
onMounted(() => {
  try {
    reviewer.value = localStorage.getItem('career-reviewer-name') || ''
  } catch {
    reviewer.value = ''
  }
})
</script>
<template>
  <section aria-label="Duplicate check" class="space-y-3">
    <h3 class="font-semibold">Duplicate check</h3>
    <p class="text-sm">
      The app merges postings it believes are the same job. Check a few pairs: if they are different
      jobs, a real opening was lost.
    </p>
    <p v-if="!pairs.length" class="text-sm">No merged duplicates were recorded for checking.</p>
    <template v-else>
      <label class="field-label"
        >Your name or initials<input v-model="reviewer" class="field" maxlength="100"
      /></label>
      <p v-if="error" role="alert" class="text-rose-700 dark:text-rose-300">{{ error }}</p>
      <ul class="space-y-3">
        <li
          v-for="job in pairs"
          :key="job.id"
          class="space-y-2 rounded-lg border border-slate-300 p-3 dark:border-slate-600"
        >
          <p><strong>Removed:</strong> {{ job.title }} · {{ job.company }} ({{ job.board }})</p>
          <p>
            <strong>Kept:</strong> {{ job.duplicate_of!.title }} ·
            {{ job.duplicate_of!.company }} ({{ job.duplicate_of!.board }})
          </p>
          <p class="text-sm">Matched by: {{ job.duplicate_of!.method }}</p>
          <details>
            <summary class="cursor-pointer py-1 text-sm">Compare descriptions</summary>
            <div class="mt-2 grid gap-3 sm:grid-cols-2">
              <p
                class="max-h-48 overflow-y-auto whitespace-pre-wrap break-words text-sm"
                tabindex="0"
              >
                {{ job.description || 'No description' }}
              </p>
              <p
                class="max-h-48 overflow-y-auto whitespace-pre-wrap break-words text-sm"
                tabindex="0"
              >
                {{ job.duplicate_of!.description || 'No description' }}
              </p>
            </div>
          </details>
          <div
            class="flex flex-wrap gap-2"
            role="group"
            :aria-label="`Is ${job.title} the same job?`"
          >
            <button
              type="button"
              class="btn-secondary"
              :disabled="busy"
              :aria-pressed="judged(job.id) === true"
              @click="judge(job, true)"
            >
              Same job
            </button>
            <button
              type="button"
              class="btn-secondary"
              :disabled="busy"
              :aria-pressed="judged(job.id) === false"
              @click="judge(job, false)"
            >
              Different jobs
            </button>
          </div>
        </li>
      </ul>
    </template>
  </section>
</template>

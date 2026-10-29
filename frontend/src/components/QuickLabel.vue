<!-- Fast fit-only labeling: one job at a time in a fixed random order, saved on each answer. -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../stores/pipeline'
import type { components } from '../types/api'
type S = components['schemas']
type Fit = 'strong_match' | 'review' | 'not_suitable'
const props = defineProps<{ datasetId: string; bundle: S['ReviewBundle']; dropped?: boolean }>()
const emit = defineEmits<{ saved: [labels: S['ReviewState']] }>()
// About 30 random labels give a first, rough result without reviewing every job;
// a smaller sample of dropped postings shows whether ingestion loses good fits.
const TARGET = props.dropped ? 20 : 30
// Only drops that could remove a posting before ranking are worth labeling.
const LOSS_STAGES = ['filter', 'description', 'budget']
const items = computed<(S['ReviewJob'] | S['DroppedJob'])[]>(() =>
  props.dropped
    ? props.bundle.dataset.dropped_jobs!.filter((job) => LOSS_STAGES.includes(job.stage))
    : props.bundle.dataset.jobs,
)
const choices: { value: Fit; label: string; key: string; hint: string }[] = [
  {
    value: 'strong_match',
    label: 'Good fit',
    key: '1',
    hint: 'You meet the must-have requirements and would apply.',
  },
  {
    value: 'review',
    label: 'Not sure',
    key: '2',
    hint: 'You cannot tell from the posting and your profile.',
  },
  {
    value: 'not_suitable',
    label: 'Not a fit',
    key: '3',
    hint: 'A clear mismatch: wrong field, far too senior, or a must-have you lack.',
  },
]
const reviewer = ref('')
const reason = ref('')
const error = ref('')
const busy = ref(false)
const skipped = ref(new Set<string>())
const history = ref<string[]>([])
const revisit = ref('')
const reviewerInput = ref<HTMLInputElement>()

// Shuffle with a seed from the dataset ID so the order is random but stable across visits.
function shuffled(ids: string[], seed: string) {
  let h = 2166136261
  for (const c of seed) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  const random = () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507)
    h = Math.imul(h ^ (h >>> 13), 3266489909)
    return ((h ^= h >>> 16) >>> 0) / 4294967296
  }
  const result = [...ids]
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[result[i], result[j]] = [result[j]!, result[i]!]
  }
  return result
}
const order = computed(() =>
  shuffled(
    items.value.map((job) => job.id),
    props.bundle.dataset.id + (props.dropped ? ':dropped' : ''),
  ),
)
const saved = (id: string) => props.bundle.labels.jobs?.[id]
const labeledCount = computed(() => order.value.filter((id) => saved(id)?.fit != null).length)
const currentId = computed(
  () =>
    revisit.value ||
    order.value.find((id) => saved(id)?.fit == null && !skipped.value.has(id)) ||
    '',
)
const job = computed(() => items.value.find((item) => item.id === currentId.value))
const remainingSkipped = computed(
  () => order.value.filter((id) => saved(id)?.fit == null && skipped.value.has(id)).length,
)
const choiceLabel = (fit?: string | null) => choices.find((c) => c.value === fit)?.label

async function answer(fit: Fit) {
  if (!job.value || busy.value) return
  if (!reviewer.value.trim()) {
    error.value = 'Enter your name or initials first.'
    reviewerInput.value?.focus()
    return
  }
  busy.value = true
  error.value = ''
  const id = job.value.id
  // Keep any detailed judgments already saved for this job.
  const existing = saved(id)
  const review = {
    ai_assisted: false,
    extraction_complete: false,
    criteria: {},
    evidence: {},
    missing_requirements: [],
    ...existing,
    fit,
    notes: reason.value.trim() || existing?.notes || '',
  }
  try {
    const labels = await api<S['ReviewState']>(
      `/api/review-datasets/${props.datasetId}/jobs/${id}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          revision: props.bundle.labels.revision || 0,
          reviewer: reviewer.value.trim(),
          review,
        }),
      },
    )
    try {
      localStorage.setItem('career-reviewer-name', reviewer.value.trim())
    } catch {
      // Remembering the name is a convenience only.
    }
    emit('saved', labels)
    if (!revisit.value) history.value.push(id)
    revisit.value = ''
    reason.value = ''
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
function skip() {
  if (!job.value) return
  if (!revisit.value) skipped.value.add(job.value.id)
  revisit.value = ''
  reason.value = ''
}
function back() {
  const id = history.value.pop()
  if (!id) return
  revisit.value = id
  reason.value = saved(id)?.notes || ''
}
function onKey(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null
  if (event.metaKey || event.ctrlKey || event.altKey) return
  if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
  const choice = choices.find((c) => c.key === event.key)
  if (choice) {
    event.preventDefault()
    void answer(choice.value)
  }
}
onMounted(() => {
  try {
    reviewer.value = localStorage.getItem('career-reviewer-name') || ''
  } catch {
    reviewer.value = ''
  }
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>
<template>
  <section :aria-label="dropped ? 'Label dropped jobs' : 'Quick labeling'" class="space-y-4">
    <div class="space-y-2">
      <p class="font-semibold">
        {{ labeledCount }} labeled · aim for {{ TARGET }}
        <span v-if="labeledCount >= TARGET">
          — enough for a first result. Keep going if you like.</span
        >
      </p>
      <div
        role="progressbar"
        aria-label="Labeling progress"
        :aria-valuenow="Math.min(labeledCount, TARGET)"
        aria-valuemin="0"
        :aria-valuemax="TARGET"
        class="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
      >
        <div
          class="h-full bg-indigo-600 dark:bg-indigo-400"
          :style="{ width: `${Math.min(100, (labeledCount / TARGET) * 100)}%` }"
        />
      </div>
      <p class="text-sm text-slate-600 dark:text-slate-300">
        <template v-if="dropped">
          These jobs were dropped before ranking. Labeling about 20 shows whether the app throws
          away good fits early. They appear in a random order; answer from the posting and your
          profile only.
        </template>
        <template v-else>
          Jobs appear in a random order, so any 30 you label are a fair sample. Answer from the
          posting and your profile only.
        </template>
      </p>
    </div>
    <label class="field-label"
      >Your name or initials<input
        ref="reviewerInput"
        v-model="reviewer"
        class="field"
        maxlength="100"
        autocomplete="name"
    /></label>
    <details class="rounded-lg border border-slate-200 p-4 dark:border-slate-700">
      <summary class="cursor-pointer py-2 font-semibold">Your profile (open to compare)</summary>
      <p class="mt-2">Target roles: {{ bundle.dataset.target_roles.join(', ') }}</p>
      <pre class="mt-3 whitespace-pre-wrap break-words font-sans text-sm">{{
        bundle.dataset.profile_text
      }}</pre>
    </details>
    <p v-if="error" role="alert" class="text-rose-700 dark:text-rose-300">{{ error }}</p>
    <article
      v-if="job"
      class="space-y-4 rounded-xl border border-slate-200 p-4 dark:border-slate-700"
    >
      <p v-if="revisit" class="text-sm">
        Changing a previous answer. Current answer: {{ choiceLabel(saved(revisit)?.fit) }}
      </p>
      <h2 class="text-xl font-semibold">{{ job.title }} · {{ job.company }}</h2>
      <div
        class="max-h-80 overflow-y-auto rounded-lg bg-slate-50 p-3 dark:bg-slate-800"
        tabindex="0"
        aria-label="Job posting text"
      >
        <p v-if="job.description" class="whitespace-pre-wrap break-words">{{ job.description }}</p>
        <p v-else>
          No description was collected for this job. Open the original posting to judge it.
        </p>
      </div>
      <p v-if="job.url">
        <a
          :href="job.url"
          target="_blank"
          rel="noopener noreferrer"
          class="text-indigo-700 underline dark:text-indigo-300"
          >Open the original posting</a
        >
      </p>
      <div class="flex flex-wrap gap-3" role="group" aria-label="Is this job a good fit?">
        <button
          v-for="choice in choices"
          :key="choice.value"
          type="button"
          :class="choice.value === 'strong_match' ? 'btn-primary' : 'btn-secondary'"
          :disabled="busy"
          :aria-keyshortcuts="choice.key"
          @click="answer(choice.value)"
        >
          {{ choice.label }} <span class="text-sm">({{ choice.key }})</span>
        </button>
      </div>
      <ul class="space-y-1 text-sm">
        <li v-for="choice in choices" :key="choice.value">
          <strong>{{ choice.label }}:</strong> {{ choice.hint }}
        </li>
      </ul>
      <label class="field-label"
        >Reason (optional)<input
          v-model="reason"
          class="field"
          maxlength="5000"
          placeholder="For example: needs 5 years of paid experience"
      /></label>
      <div class="flex flex-wrap gap-3">
        <button type="button" class="btn-secondary" :disabled="busy" @click="skip">
          Skip for now
        </button>
        <button
          type="button"
          class="btn-secondary"
          :disabled="busy || !history.length"
          @click="back"
        >
          Change previous answer
        </button>
      </div>
    </article>
    <div v-else class="space-y-2 rounded-xl bg-slate-100 p-4 dark:bg-slate-800">
      <p class="font-semibold">
        {{
          remainingSkipped
            ? 'No more unskipped jobs.'
            : dropped
              ? 'Every recorded dropped job is labeled.'
              : 'Every job in this dataset is labeled.'
        }}
      </p>
      <button
        v-if="remainingSkipped"
        type="button"
        class="btn-secondary"
        @click="skipped = new Set()"
      >
        Show {{ remainingSkipped }} skipped jobs
      </button>
      <button
        v-if="history.length"
        type="button"
        class="btn-secondary"
        :disabled="busy"
        @click="back"
      >
        Change previous answer
      </button>
    </div>
  </section>
</template>

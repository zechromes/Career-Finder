<!-- Paid comparison of embedding models on the source workspace, scored with your labels. -->
<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { api } from '../stores/pipeline'
import type { components } from '../types/api'
type S = components['schemas']
const props = defineProps<{ bundle: S['ReviewBundle'] }>()
const open = ref(false)
const models = ref<string[]>([])
const selected = ref<string[]>([])
const topK = ref(20)
const busy = ref(false)
const error = ref('')
const result = ref<S['ExperimentResult']>()
let timer: ReturnType<typeof setTimeout> | undefined
let alive = true
const percent = (value?: number | null) =>
  value == null ? 'Not available' : `${(value * 100).toFixed(0)}%`

async function show() {
  open.value = true
  error.value = ''
  try {
    const options = await api<S['ExperimentOptions']>('/api/experiments/options')
    models.value = options.embedding_models
    selected.value = [...options.embedding_models]
  } catch (cause) {
    error.value = (cause as Error).message
  }
}
async function poll(id: string) {
  try {
    const value = await api<S['ExperimentResult']>(`/api/experiments/${id}`)
    if (!alive) return
    result.value = value
    if (value.status === 'running') timer = setTimeout(() => poll(id), 1500)
    else busy.value = false
  } catch (cause) {
    if (!alive) return
    error.value = (cause as Error).message
    busy.value = false
  }
}
async function run() {
  busy.value = true
  error.value = ''
  result.value = undefined
  try {
    const source = props.bundle.dataset.source_id
    // The workspace must still exist; its current pool supplies the fingerprint.
    const pool = await api<S['ExperimentDataset']>(`/api/experiments/sources/${source}`)
    const ids = new Set(pool.jobs.map((job) => job.id))
    const labels = Object.fromEntries(
      Object.entries(props.bundle.labels.jobs || {})
        .filter(
          ([id, review]) =>
            ids.has(id) &&
            !review.ai_assisted &&
            (review.fit === 'strong_match' || review.fit === 'not_suitable'),
        )
        .map(([id, review]) => [id, review.fit === 'strong_match']),
    )
    const started = await api<S['ExperimentResult']>('/api/experiments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_id: source,
        fingerprint: pool.fingerprint,
        phase: 'retrieval',
        embedding_models: selected.value,
        providers: [],
        top_k: topK.value,
        labels,
      }),
    })
    result.value = started
    void poll(started.id)
  } catch (cause) {
    error.value = (cause as Error).message
    busy.value = false
  }
}
onBeforeUnmount(() => {
  alive = false
  clearTimeout(timer)
})
</script>
<template>
  <section aria-label="Compare embedding models" class="space-y-3">
    <h3 class="font-semibold">Compare embedding models (paid)</h3>
    <p class="text-sm">
      Re-ranks this search's job pool with each embedding model and checks how many of your good
      fits land in the top K. Normal search results are not changed.
    </p>
    <button v-if="!open" type="button" class="btn-secondary" @click="show">
      Set up a comparison
    </button>
    <form v-else class="space-y-3" @submit.prevent="run">
      <fieldset :disabled="busy" class="space-y-2">
        <legend class="font-semibold">Embedding models</legend>
        <label v-for="model in models" :key="model" class="flex min-h-11 items-center gap-3">
          <input v-model="selected" type="checkbox" :value="model" />{{ model }}
        </label>
        <label class="field-label"
          >Top K (1–20)<input
            v-model.number="topK"
            class="field"
            type="number"
            min="1"
            max="20"
            required
        /></label>
      </fieldset>
      <p class="text-sm">
        This sends the pool's job text to OpenAI to create embeddings and may cost a few cents. It
        needs the original search, which is kept for 7 days.
      </p>
      <button type="submit" class="btn-primary" :disabled="busy || !selected.length">
        {{ busy ? 'Comparing…' : 'Run comparison' }}
      </button>
    </form>
    <p v-if="error" role="alert" class="text-rose-700 dark:text-rose-300">{{ error }}</p>
    <div v-if="result" class="space-y-2">
      <p role="status">{{ result.status }} · {{ result.message }}</p>
      <ul class="space-y-1">
        <li v-for="trial in result.retrieval" :key="trial.model">
          <strong>{{ trial.model }}:</strong>
          <template v-if="trial.error"> failed: {{ trial.error }}</template>
          <template v-else>
            found {{ percent(trial.metrics.observed_recall_at_k) }} of your good fits in the top
            {{ result.top_k }}; {{ percent(trial.metrics.precision_on_labeled) }} of labeled jobs
            there were good fits; {{ trial.metrics.missed_labeled_positives?.length || 0 }} good
            fits missed.
          </template>
        </li>
      </ul>
      <p class="text-sm">
        This uses exact similarity plus keyword ranking, without the seniority and dismissal
        adjustments, so it isolates the embedding model rather than reproducing the live shortlist.
      </p>
    </div>
  </section>
</template>

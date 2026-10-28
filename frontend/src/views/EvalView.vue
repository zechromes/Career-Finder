<script setup lang="ts">
import ReviewDatasets from '../components/ReviewDatasets.vue'
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../stores/pipeline'
import type { components } from '../types/api'
type Schemas = components['schemas']
type Request = Schemas['ExperimentRequest']
const route = useRoute()
const router = useRouter()
const options = ref<Schemas['ExperimentOptions']>()
const sources = ref<Schemas['ExperimentSource'][]>([])
const source = ref('')
const dataset = ref<Schemas['ExperimentDataset']>()
const result = ref<Schemas['ExperimentResult']>()
const phase = ref<Request['phase']>('both')
const embeddings = ref<NonNullable<Request['embedding_models']>>(['text-embedding-3-small'])
const providers = ref<NonNullable<Request['providers']>>(['gpt'])
const topK = ref(5)
// The model comparison is collapsed unless an experiment link is opened.
const advanced = ref(typeof route.query.experiment === 'string')
const labels = ref<Record<string, string>>({})
const error = ref('')
const loading = ref(true)
const submitting = ref(false)
const running = computed(() => result.value?.status === 'running')
const locked = computed(() => loading.value || submitting.value || running.value)
const canRun = computed(
  () =>
    dataset.value &&
    !locked.value &&
    (phase.value === 'generation' || embeddings.value.length) &&
    (phase.value === 'retrieval' || providers.value.length),
)
let alive = true
let timer: ReturnType<typeof setTimeout> | undefined
let datasetVersion = 0
let pollVersion = 0
const percent = (value: number | null | undefined) =>
  value == null ? 'Not available' : `${(value * 100).toFixed(1)}%`
const title = (id: string) => dataset.value?.jobs.find((job) => job.id === id)?.title || id
const validDataset = computed(
  () => !result.value || dataset.value?.fingerprint === result.value.fingerprint,
)

async function loadDataset(clear = true) {
  const version = ++datasetVersion
  dataset.value = undefined
  labels.value = {}
  if (clear) {
    pollVersion++
    clearTimeout(timer)
    result.value = undefined
    await router.replace('/eval')
  }
  if (!source.value) return
  loading.value = true
  error.value = ''
  try {
    const value = await api<Schemas['ExperimentDataset']>(
      `/api/experiments/sources/${source.value}`,
    )
    if (alive && version === datasetVersion) {
      dataset.value = value
      labels.value = Object.fromEntries(value.jobs.map((job) => [job.id, '']))
    }
  } catch (cause) {
    if (alive && version === datasetVersion) error.value = (cause as Error).message
  } finally {
    if (alive && version === datasetVersion) loading.value = false
  }
}
async function poll() {
  if (!result.value) return
  clearTimeout(timer)
  const version = ++pollVersion
  const id = result.value.id
  try {
    const value = await api<Schemas['ExperimentResult']>(`/api/experiments/${id}`)
    if (!alive || version !== pollVersion) return
    result.value = value
    error.value = ''
    if (value.status === 'running') timer = setTimeout(poll, 1500)
  } catch (cause) {
    if (!alive || version !== pollVersion) return
    error.value = (cause as Error).message
    if ((cause as Error & { status?: number }).status === 404) {
      result.value = undefined
      await router.replace('/eval')
    }
  }
}
async function run() {
  if (!canRun.value || !dataset.value) return
  submitting.value = true
  error.value = ''
  try {
    const body: Request = {
      source_id: source.value,
      fingerprint: dataset.value.fingerprint,
      phase: phase.value,
      embedding_models: embeddings.value,
      providers: providers.value,
      top_k: topK.value,
      labels: Object.fromEntries(
        Object.entries(labels.value)
          .filter(([, value]) => value !== '')
          .map(([key, value]) => [key, value === 'positive']),
      ),
    }
    const value = await api<Schemas['ExperimentResult']>('/api/experiments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!alive) return
    result.value = value
    await router.replace({ path: '/eval', query: { experiment: value.id } })
    void poll()
  } catch (cause) {
    if (alive) error.value = (cause as Error).message
  } finally {
    if (alive) submitting.value = false
  }
}
async function cancel() {
  if (!result.value) return
  pollVersion++
  clearTimeout(timer)
  submitting.value = true
  try {
    const value = await api<Schemas['ExperimentResult']>(
      `/api/experiments/${result.value.id}/cancel`,
      { method: 'POST' },
    )
    if (alive) {
      result.value = value
      clearTimeout(timer)
    }
  } catch (cause) {
    if (alive) error.value = (cause as Error).message
  } finally {
    if (alive) submitting.value = false
  }
}
function download() {
  if (!result.value) return
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(result.value, null, 2)], { type: 'application/json' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = `experiment-${result.value.id}.json`
  link.click()
  URL.revokeObjectURL(url)
}
onMounted(async () => {
  try {
    const [config, workspaces] = await Promise.all([
      api<Schemas['ExperimentOptions']>('/api/experiments/options'),
      api<Schemas['ExperimentSource'][]>('/api/experiments/sources'),
    ])
    if (!alive) return
    options.value = config
    sources.value = workspaces
    const id = route.query.experiment
    if (typeof id === 'string') {
      result.value = await api<Schemas['ExperimentResult']>(
        `/api/experiments/${encodeURIComponent(id)}`,
      )
      if (!alive) return
      source.value = result.value.source_id
      await loadDataset(false)
      const settings = result.value.settings
      phase.value = settings.phase || 'both'
      embeddings.value = settings.embedding_models || []
      providers.value = settings.providers || []
      topK.value = settings.top_k || 5
      if (validDataset.value) {
        for (const [key, value] of Object.entries(settings.labels || {}))
          labels.value[key] = value ? 'positive' : 'negative'
      }
      await poll()
    }
  } catch (cause) {
    if (alive) error.value = (cause as Error).message
  } finally {
    if (alive) loading.value = false
  }
})
onBeforeUnmount(() => {
  alive = false
  datasetVersion++
  clearTimeout(timer)
})
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-6">
    <header class="space-y-3">
      <h1 class="text-3xl font-bold">Check how well the app matches jobs</h1>
      <p>
        The app picks jobs it thinks suit your resume. To find out whether it picks well, you label
        some jobs yourself, then the app compares its picks with your answers. Nothing here changes
        your normal search results.
      </p>
      <ol class="list-decimal space-y-1 pl-6">
        <li><strong>Choose a finished search</strong> below.</li>
        <li><strong>Create a review dataset.</strong> This saves a copy of that search's jobs.</li>
        <li>
          <strong>Label about 30 jobs</strong> as Good fit, Not sure or Not a fit. Each takes a few
          seconds.
        </li>
        <li>
          <strong>Read the results</strong> on the dataset page: how many of your good fits the app
          found.
        </li>
      </ol>
    </header>
    <p
      v-if="error"
      role="alert"
      class="rounded-lg bg-rose-50 p-4 text-rose-900 dark:bg-rose-950 dark:text-rose-200"
    >
      {{ error }}
      <button v-if="result" type="button" class="underline" @click="poll">
        Refresh experiment
      </button>
    </p>
    <p v-if="loading" role="status">Loading experiment data…</p>
    <p v-if="!loading && !sources.length && !error">
      No workspaces are ready. Complete a job search, then return here.
    </p>
    <label class="field-label"
      >Workspace
      <select
        v-model="source"
        aria-label="Workspace"
        class="field"
        :disabled="locked"
        @change="loadDataset()"
      >
        <option value="">Choose a finished search</option>
        <option v-for="item in sources" :key="item.id" :value="item.id">
          {{ item.name }} · {{ item.job_count }} saved results
        </option>
      </select>
    </label>
    <ReviewDatasets :source-id="source" :disabled="locked" />
    <details
      :open="advanced"
      class="rounded-2xl border border-slate-200 p-5 dark:border-slate-700"
      @toggle="advanced = ($event.target as HTMLDetailsElement).open"
    >
      <summary class="cursor-pointer py-2 text-lg font-semibold">
        Advanced: compare AI models (uses paid API calls)
      </summary>
      <div class="mt-3 space-y-5">
        <header class="space-y-2">
          <h2 class="text-2xl font-semibold">Compare AI models</h2>
          <p>
            For developers. Runs the selected search workspace through different AI models to
            compare
            <strong>ranking</strong> (which jobs are picked first) and
            <strong>fit assessment</strong>
            (how each model judges a job). Results are more meaningful once you have labeled jobs.
          </p>
          <p class="text-sm text-slate-600 dark:text-slate-300">
            Runs start only when you choose Run experiment. Selected providers receive the relevant
            posting and profile text and may charge API usage. No new jobs are scraped.
          </p>
        </header>
        <form
          class="space-y-5 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
          @submit.prevent="run"
        >
          <fieldset :disabled="locked" class="space-y-5">
            <legend class="text-lg font-semibold">Experiment settings</legend>
            <div class="grid gap-4 sm:grid-cols-2">
              <label class="field-label"
                >Phase
                <select v-model="phase" aria-label="Phase" class="field">
                  <option value="both">Retrieval and generation</option>
                  <option value="retrieval">Retrieval only</option>
                  <option value="generation">Generation only</option>
                </select>
              </label>
              <label class="field-label"
                >Shortlist size (K)
                <input
                  v-model.number="topK"
                  class="field"
                  type="number"
                  min="1"
                  max="20"
                  required
                />
              </label>
            </div>
            <fieldset v-if="phase !== 'generation'" class="space-y-2">
              <legend class="font-semibold">Embedding models</legend>
              <label
                v-for="model in options?.embedding_models"
                :key="model"
                class="flex min-h-11 items-center gap-3"
              >
                <input v-model="embeddings" type="checkbox" :value="model" />{{ model }}
              </label>
              <p class="text-sm text-slate-600 dark:text-slate-300">
                Exact cosine similarity + BM25, combined with the application's weighted rank
                fusion. Each model re-embeds the same pool. This tests retrieval before seniority
                and dismissal adjustments.
              </p>
            </fieldset>
            <fieldset v-if="phase !== 'retrieval'" class="space-y-2">
              <legend class="font-semibold">Generation models</legend>
              <label
                v-for="model in options?.generation_models"
                :key="model.value"
                class="flex min-h-11 items-center gap-3"
              >
                <input v-model="providers" type="checkbox" :value="model.value" />{{ model.label }}
              </label>
              <p class="text-sm text-slate-600 dark:text-slate-300">
                All selected models assess the same jobs with the existing evidence rules and shared
                OpenAI requirement extraction. Assessment reuse is disabled; requirement extraction
                may use its existing cache.
              </p>
            </fieldset>
            <p class="text-sm">
              {{
                phase === 'generation'
                  ? 'Generation uses the first K postings in the fixed dataset order.'
                  : `Generation uses the first selected embedding model's shortlist (${embeddings[0] || 'choose a model'}). Other embedding models are compared separately.`
              }}
              If that retrieval fails, generation is skipped.
            </p>
            <details
              v-if="dataset"
              class="rounded-lg border border-slate-200 p-3 dark:border-slate-700"
            >
              <summary class="cursor-pointer py-2 font-semibold">
                Dataset &amp; optional human labels ({{ dataset.jobs.length }} jobs)
              </summary>
              <p class="my-3 text-sm">
                {{ dataset.scope }}. Label strong candidate fit independently of model outputs.
                Unlabeled jobs are never counted as negatives. Partial labels give observed recall,
                not full-pool accuracy.
              </p>
              <div class="max-h-96 space-y-3 overflow-y-auto">
                <div
                  v-for="job in dataset.jobs"
                  :key="job.id"
                  class="rounded border border-slate-200 p-3 dark:border-slate-700"
                >
                  <label class="field-label"
                    >{{ job.title }} · {{ job.company }}
                    <select
                      v-model="labels[job.id]"
                      class="field"
                      :aria-label="`Human label for ${job.title}`"
                    >
                      <option value="">Unlabeled</option>
                      <option value="positive">Strong fit</option>
                      <option value="negative">Not a strong fit</option>
                    </select>
                  </label>
                  <details class="mt-2">
                    <summary class="cursor-pointer py-2">Posting text</summary>
                    <p class="whitespace-pre-wrap text-sm">{{ job.description }}</p>
                  </details>
                </div>
              </div>
            </details>
          </fieldset>
          <button type="submit" class="btn-primary" :disabled="!canRun">
            {{ submitting ? 'Submitting…' : 'Run experiment' }}
          </button>
          <button
            v-if="running"
            type="button"
            class="btn-secondary ml-3"
            :disabled="submitting"
            @click="cancel"
          >
            Cancel experiment
          </button>
        </form>
        <section v-if="result" aria-label="Experiment results" class="space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <h2 class="text-2xl font-semibold">Experiment results</h2>
            <button type="button" class="btn-secondary" @click="download">
              Download results JSON
            </button>
          </div>
          <p role="status">{{ result.status }} · {{ result.message }}</p>
          <p class="text-sm">
            {{ result.pool_size }} postings · K = {{ result.top_k }} · {{ result.scope }}. Results
            are kept in server memory for up to 24 hours (latest 20), and disappear on restart.
            Leaving this page does not cancel a run.
          </p>
          <p v-if="!validDataset" class="text-sm">
            The source dataset has changed or is unavailable; stored job identifiers remain in the
            report.
          </p>
          <div
            v-for="trial in result.retrieval"
            :key="trial.model"
            class="rounded-xl border border-slate-200 p-4 dark:border-slate-700"
          >
            <h3 class="text-lg font-semibold">Retrieval · {{ trial.model }}</h3>
            <p>{{ trial.seconds.toFixed(2) }} seconds</p>
            <p v-if="trial.error" role="alert">Failed: {{ trial.error }}</p>
            <template v-else>
              <p class="my-2 text-sm">
                Label coverage: {{ percent(trial.metrics.label_coverage) }} · Observed recall@K:
                {{ percent(trial.metrics.observed_recall_at_k) }} · Precision on labeled shortlist:
                {{ percent(trial.metrics.precision_on_labeled) }} · Unlabeled shortlisted:
                {{ trial.metrics.unlabeled_selected }}
              </p>
              <ol class="list-decimal space-y-1 pl-6">
                <li v-for="id in trial.ranked_ids" :key="id">
                  {{ validDataset ? title(id) : id }}
                </li>
              </ol>
              <p v-if="trial.metrics.missed_labeled_positives?.length" class="mt-2 text-sm">
                Missed labeled strong fits:
                {{
                  (trial.metrics.missed_labeled_positives || [])
                    .map((id) => (validDataset ? title(id) : id))
                    .join(', ')
                }}
              </p>
            </template>
          </div>
          <div
            v-for="trial in result.generation"
            :key="trial.provider"
            class="space-y-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700"
          >
            <h3 class="text-lg font-semibold">Generation · {{ trial.model }}</h3>
            <p>
              {{ trial.seconds.toFixed(2) }} seconds · {{ trial.results?.length || 0 }}/{{
                trial.input_ids.length
              }}
              assessments completed
            </p>
            <p class="text-sm">
              Strong-match precision on labeled predictions:
              {{ percent(trial.metrics.precision_on_labeled) }} · Label coverage:
              {{ percent(trial.metrics.label_coverage) }} · Unlabeled strong predictions:
              {{ trial.metrics.unlabeled_selected }}
            </p>
            <p v-for="(message, index) in trial.errors" :key="index" role="alert">
              Failed assessment: {{ message }}
            </p>
            <details
              v-for="job in trial.results"
              :key="job.jobId"
              class="rounded-lg bg-slate-50 p-3 dark:bg-slate-800"
            >
              <summary class="cursor-pointer py-2 font-semibold">
                {{ job.title }} · {{ job.fit_category }} ·
                {{ job.score == null ? 'Unscored' : `${job.score}/100` }}
              </summary>
              <p class="my-2">{{ job.rationale }}</p>
              <p v-if="job.mismatch_reason" class="my-2">{{ job.mismatch_reason }}</p>
              <ul class="space-y-3">
                <li
                  v-for="(criterion, index) in job.requirement_verdicts"
                  :key="index"
                  class="border-t border-slate-300 pt-3 dark:border-slate-600"
                >
                  <p class="font-semibold">{{ criterion.requirement }} · {{ criterion.verdict }}</p>
                  <p>{{ criterion.explanation }}</p>
                  <p class="mt-1 text-sm">
                    Posting ({{
                      criterion.job_evidence_verified ? 'quote verified' : 'quote unverified'
                    }}): {{ criterion.job_quote || 'No quote' }}
                  </p>
                  <p class="text-sm">
                    Profile ({{
                      criterion.resume_evidence_verified ? 'quote verified' : 'quote unverified'
                    }}): {{ criterion.resume_quote || 'No evidence provided' }}
                  </p>
                </li>
              </ul>
            </details>
          </div>
        </section>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { RouterLink, useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { api } from '../stores/pipeline'
import ReviewGuide from '../components/ReviewGuide.vue'
import QuickLabel from '../components/QuickLabel.vue'
import StageResults from '../components/StageResults.vue'
import type { components } from '../types/api'
type S = components['schemas']
const route = useRoute()
const router = useRouter()
const bundle = ref<S['ReviewBundle']>()
const metrics = ref<S['ReviewMetrics']>()
const index = ref(0)
const reviewer = ref('')
const draft = ref<S['JobReview']>({ ai_assisted: false, notes: '', extraction_complete: false })
const baseline = ref(JSON.stringify(draft.value))
const error = ref('')
const message = ref('')
const busy = ref(false)
const revealed = ref(false)
const reviewStep = ref<'requirements' | 'evidence'>('requirements')
// Keep the review mode in the URL so refreshes and shared links reopen it.
const mode = ref<'quick' | 'detailed'>(route.query.mode === 'detailed' ? 'detailed' : 'quick')
const job = computed(() => bundle.value?.dataset.jobs[index.value])
function setMode(next: 'quick' | 'detailed') {
  if (next === mode.value) return
  if (dirty.value && !window.confirm('Discard unsaved review changes?')) return
  mode.value = next
  void router.replace({ query: next === 'detailed' ? { mode: next } : {} })
  if (next === 'detailed') loadDraft()
}
async function quickSaved(labels: S['ReviewState']) {
  if (!bundle.value) return
  bundle.value.labels = labels
  try {
    metrics.value = await api(`/api/review-datasets/${id}/metrics`)
  } catch (cause) {
    error.value = (cause as Error).message
  }
}
const dirty = computed(() => baseline.value !== JSON.stringify(draft.value))
const percent = (value?: number | null) =>
  value == null ? 'Not reviewed' : `${(value * 100).toFixed(1)}%`
const id = String(route.params.datasetId)
function loadDraft() {
  const saved = bundle.value?.labels.jobs?.[job.value!.id]
  draft.value = JSON.parse(
    JSON.stringify(
      saved || {
        fit: null,
        ai_assisted: false,
        notes: '',
        extraction_complete: false,
        criteria: {},
        evidence: {},
        missing_requirements: [],
      },
    ),
  )
  for (const row of job.value!.criteria)
    draft.value.criteria![row.id] ||= { correct: null, importance: null, notes: '' }
  for (const row of job.value!.evidence)
    draft.value.evidence![row.id] ||= { support: null, verdict: null, notes: '' }
  baseline.value = JSON.stringify(draft.value)
  revealed.value = false
  reviewStep.value = 'requirements'
}
function move(next: number) {
  if (dirty.value && !window.confirm('Discard unsaved review changes?')) return
  index.value = next
  loadDraft()
  message.value = ''
  error.value = ''
}
onBeforeRouteLeave(() => !dirty.value || window.confirm('Discard unsaved review changes?'))
async function load() {
  busy.value = true
  error.value = ''
  try {
    bundle.value = await api(`/api/review-datasets/${id}`)
    loadDraft()
    metrics.value = await api(`/api/review-datasets/${id}/metrics`)
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
async function save() {
  if (!bundle.value || !job.value) return
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    bundle.value.labels = await api(`/api/review-datasets/${id}/jobs/${job.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        revision: bundle.value.labels.revision || 0,
        reviewer: reviewer.value,
        review: draft.value,
      }),
    })
    baseline.value = JSON.stringify(draft.value)
    message.value = 'Review saved.'
    metrics.value = await api(`/api/review-datasets/${id}/metrics`)
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
function download() {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify({ ...bundle.value, metrics: metrics.value }, null, 2)], {
      type: 'application/json',
    }),
  )
  const a = document.createElement('a')
  a.href = url
  a.download = `review-dataset-${id}.json`
  a.click()
  URL.revokeObjectURL(url)
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
onMounted(() => {
  window.addEventListener('beforeunload', beforeUnload)
  void load()
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
</script>
<template>
  <div class="mx-auto max-w-5xl space-y-5">
    <RouterLink to="/eval" class="text-indigo-700 underline dark:text-indigo-300"
      >Back to experiments</RouterLink
    >
    <h1 class="text-3xl font-bold">Dataset review</h1>
    <p v-if="error" role="alert" class="text-rose-700 dark:text-rose-300">{{ error }}</p>
    <p v-if="busy" role="status">Loading or saving review…</p>
    <p v-if="message" role="status">{{ message }}</p>
    <template v-if="bundle && job">
      <p>
        {{ bundle.dataset.jobs.length }} jobs saved from your search. Your labels are compared with
        the jobs the app picked; they never change your search results.
      </p>
      <div class="flex flex-wrap gap-3" role="group" aria-label="Review mode">
        <button
          type="button"
          class="btn-secondary"
          :aria-pressed="mode === 'quick'"
          @click="setMode('quick')"
        >
          Quick labeling (recommended)
        </button>
        <button
          type="button"
          class="btn-secondary"
          :aria-pressed="mode === 'detailed'"
          @click="setMode('detailed')"
        >
          Detailed review
        </button>
      </div>
      <StageResults v-if="metrics" :metrics="metrics" :bundle="bundle" />
      <QuickLabel v-if="mode === 'quick'" :dataset-id="id" :bundle="bundle" @saved="quickSaved" />
      <template v-else>
        <section
          aria-label="How to review"
          class="space-y-3 rounded-xl bg-indigo-50 p-5 dark:bg-indigo-950"
        >
          <h2 class="text-xl font-semibold">Start with one job and one decision</h2>
          <p>
            Your answers help check whether the app finds suitable jobs and explains them
            accurately. You are reviewing the app, not applying for this job or changing its scores.
          </p>
          <ol class="list-decimal space-y-2 pl-5">
            <li>
              <strong>Read:</strong> compare the candidate profile below with the job posting.
            </li>
            <li>
              <strong>Decide fit:</strong> choose a fit label and explain the evidence. Enter your
              name or initials and save.
            </li>
            <li>
              <strong>Optional deeper review:</strong> reveal model outputs to check extracted
              requirements, then the models’ evidence.
            </li>
          </ol>
          <p>
            You can save just the fit decision and return later. You do not need to complete every
            field or every job in one sitting. Unanswered items stay unreviewed.
          </p>
        </section>
        <details open class="rounded-lg border border-slate-200 p-4 dark:border-slate-700">
          <summary class="cursor-pointer py-2 font-semibold">1. Read the candidate profile</summary>
          <p class="my-3">
            Use this saved profile as your evidence. Do not fill gaps from assumptions or outside
            knowledge.
          </p>
          <p>Target roles: {{ bundle.dataset.target_roles.join(', ') }}</p>
          <pre class="mt-3 whitespace-pre-wrap break-words font-sans text-sm">{{
            bundle.dataset.profile_text
          }}</pre>
        </details>
        <details
          v-if="metrics"
          aria-label="Review quality metrics"
          class="rounded-xl bg-slate-100 p-4 dark:bg-slate-800"
        >
          <summary class="cursor-pointer py-2 font-semibold">
            Review progress and quality metrics · {{ metrics.fit_reviewed }}/{{ metrics.pool_size }}
            fit decisions saved
          </summary>
          <p class="my-2">
            These numbers update after saving. They describe reviewed cases, not guaranteed accuracy
            across all jobs.
          </p>
          <p>
            Fit labels: {{ metrics.fit_reviewed }}/{{ metrics.pool_size }} · Observed shortlist
            recall: {{ percent(metrics.retrieval.observed_recall_at_k) }}
          </p>
          <p v-if="metrics.ai_assisted_reviews">
            AI-assisted reviews excluded from all metrics: {{ metrics.ai_assisted_reviews }}
          </p>
          <p>
            Shared criteria reviewed: {{ metrics.extraction.reviewed }}/{{
              metrics.extraction.total
            }}
            · Extraction precision: {{ percent(metrics.extraction.precision) }} · Recall on
            completeness-reviewed jobs: {{ percent(metrics.extraction.recall_on_complete_reviews) }}
          </p>
          <p>
            Importance accuracy: {{ percent(metrics.extraction.importance_accuracy) }} · Missed
            requirements: {{ metrics.extraction.missed_requirements }}
          </p>
          <p v-for="(value, provider) in metrics.evidence" :key="provider" class="mt-2 break-words">
            {{ provider }}: support rate {{ percent(value.support_rate) }} · Verdict agreement
            {{ percent(value.verdict_accuracy) }} · Reviewed {{ value.reviewed }}/{{
              value.total
            }}
            · Uncertain {{ value.uncertain }}
          </p>
          <p class="mt-2 text-sm">
            For-review fit labels and uncertain support judgments are excluded from binary metrics.
            Partial labels yield observed metrics only. Legacy provider-defined criteria are
            excluded from shared-extraction metrics.
          </p>
        </details>
        <label class="field-label"
          >Jump to a posting
          <select
            class="field"
            aria-label="Jump to a posting"
            :value="index"
            :disabled="busy"
            @change="
              (event) => {
                const element = event.target as HTMLSelectElement
                move(Number(element.value))
                element.value = String(index)
              }
            "
          >
            <option
              v-for="(item, position) in bundle.dataset.jobs"
              :key="item.id"
              :value="position"
            >
              {{ position + 1 }}. {{ item.title }} ·
              {{ item.previously_shortlisted ? 'Shortlisted' : 'Outside shortlist'
              }}{{ bundle.labels.jobs?.[item.id]?.fit ? ' · Reviewed' : '' }}
            </option>
          </select>
        </label>
        <div class="flex flex-wrap items-center gap-3">
          <button
            type="button"
            class="btn-secondary"
            :disabled="index === 0 || busy"
            @click="move(index - 1)"
          >
            Previous job
          </button>
          <p>Job {{ index + 1 }} of {{ bundle.dataset.jobs.length }}</p>
          <button
            type="button"
            class="btn-secondary"
            :disabled="index + 1 === bundle.dataset.jobs.length || busy"
            @click="move(index + 1)"
          >
            Next job
          </button>
          <button type="button" class="btn-secondary" :disabled="dirty || busy" @click="download">
            Download saved dataset &amp; labels
          </button>
        </div>
        <article class="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
          <h2 class="text-xl font-semibold">{{ job.title }} · {{ job.company }}</h2>
          <p class="my-2 text-sm">
            {{
              job.previously_shortlisted ? 'Previously shortlisted' : 'Outside previous shortlist'
            }}
            · {{ job.tags.join(' · ') }}
          </p>
          <p class="whitespace-pre-wrap break-words">{{ job.description }}</p>
        </article>
        <form class="space-y-5" @submit.prevent="save">
          <fieldset :disabled="busy" class="space-y-4">
            <legend class="text-xl font-semibold">2. Decide candidate fit</legend>
            <ReviewGuide kind="fit" />
            <label class="field-label"
              >Reviewer name or initials<input
                v-model="reviewer"
                class="field"
                required
                maxlength="100"
            /></label>
            <label class="field-label"
              >Candidate fit<select v-model="draft.fit" aria-label="Candidate fit" class="field">
                <option :value="null">Unreviewed</option>
                <option value="strong_match">Strong fit</option>
                <option value="review">For review / uncertain</option>
                <option value="not_suitable">Not suitable</option>
              </select></label
            >
            <label class="field-label"
              >Fit explanation<textarea
                v-model="draft.notes"
                class="field"
                maxlength="5000"
                placeholder="For example: the role requires a licence, but the profile does not mention one, so I cannot confirm eligibility."
              />
            </label>
            <label class="flex min-h-11 items-center gap-3"
              ><input v-model="draft.ai_assisted" type="checkbox" />I used an AI suggestion for this
              review</label
            >
            <p class="text-sm">
              AI-assisted reviews are saved for reference but excluded from every quality metric, so
              the metrics reflect only your independent judgments.
            </p>
            <p class="text-sm">
              Ready to save? Use Save job review below. The remaining checks are optional.
            </p>
            <h3 class="text-lg font-semibold">3. Optional: check the app’s answers</h3>
            <p>
              Decide fit first to avoid being influenced by the models. Revealing answers does not
              save or change your judgments.
            </p>
            <label class="flex min-h-11 items-center gap-3"
              ><input v-model="revealed" type="checkbox" />Show saved model outputs for extraction
              and evidence review</label
            >
            <div
              v-if="revealed"
              class="flex flex-wrap gap-3"
              role="group"
              aria-label="Choose a deeper review step"
            >
              <button
                type="button"
                class="btn-secondary"
                :aria-pressed="reviewStep === 'requirements'"
                @click="reviewStep = 'requirements'"
              >
                Check job requirements
              </button>
              <button
                type="button"
                class="btn-secondary"
                :aria-pressed="reviewStep === 'evidence'"
                @click="reviewStep = 'evidence'"
              >
                Check model evidence
              </button>
            </div>
            <section
              v-if="revealed && reviewStep === 'requirements'"
              aria-label="Requirement extraction review"
              class="space-y-4"
            >
              <h3 class="text-lg font-semibold">Check job requirements</h3>
              <ReviewGuide kind="requirements" />
              <p v-if="!job.extraction_available">
                No shared-extractor output is available for this posting. Legacy criteria, if
                present, are identified separately. These jobs cannot contribute to
                shared-extraction metrics yet.
              </p>
              <div
                v-for="(criterion, n) in job.criteria"
                :key="criterion.id"
                class="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700"
              >
                <p class="font-semibold">{{ n + 1 }}. {{ criterion.requirement }}</p>
                <p class="text-sm">
                  {{ criterion.origin }} ·
                  {{ criterion.extraction_model || 'Model not recorded' }} ·
                  {{ criterion.importance }}
                </p>
                <blockquote class="whitespace-pre-wrap text-sm">
                  {{ criterion.job_quote }}
                </blockquote>
                <label class="field-label"
                  >Is criterion {{ n + 1 }} valid and correctly stated?<select
                    v-model="draft.criteria![criterion.id]!.correct"
                    class="field"
                    :aria-label="`Criterion ${n + 1} correctness`"
                  >
                    <option :value="null">Unreviewed</option>
                    <option :value="true">Correct</option>
                    <option :value="false">Incorrect / duplicate / unsupported</option>
                  </select></label
                >
                <label class="field-label"
                  >Correct importance<select
                    v-model="draft.criteria![criterion.id]!.importance"
                    class="field"
                    :aria-label="`Criterion ${n + 1} importance`"
                  >
                    <option :value="null">Unreviewed</option>
                    <option value="must_have">Mandatory</option>
                    <option value="nice_to_have">Preferred</option>
                    <option value="unclear">Unclear</option>
                  </select></label
                >
                <label class="field-label"
                  >Correction notes<textarea
                    v-model="draft.criteria![criterion.id]!.notes"
                    class="field"
                    maxlength="3000"
                  />
                </label>
              </div>
              <h4 class="font-semibold">Missing requirements</h4>
              <div
                v-for="(missing, n) in draft.missing_requirements"
                :key="n"
                class="space-y-2 rounded-lg border p-3"
              >
                <label class="field-label"
                  >Requirement<input
                    v-model="missing.requirement"
                    class="field"
                    required
                    maxlength="3000"
                /></label>
                <label class="field-label"
                  >Exact posting quote<textarea
                    v-model="missing.job_quote"
                    class="field"
                    required
                    maxlength="10000"
                  />
                </label>
                <label class="field-label"
                  >Importance<select v-model="missing.importance" class="field">
                    <option value="must_have">Mandatory</option>
                    <option value="nice_to_have">Preferred</option>
                    <option value="unclear">Unclear</option>
                  </select></label
                >
                <button
                  type="button"
                  class="btn-secondary"
                  @click="draft.missing_requirements!.splice(n, 1)"
                >
                  Remove missing requirement
                </button>
              </div>
              <button
                type="button"
                class="btn-secondary"
                @click="
                  draft.missing_requirements!.push({
                    requirement: '',
                    job_quote: '',
                    importance: 'unclear',
                  })
                "
              >
                Add missing requirement
              </button>
              <label class="flex min-h-11 items-center gap-3"
                ><input
                  v-model="draft.extraction_complete"
                  type="checkbox"
                  :disabled="!job.extraction_available"
                />I reviewed all shared criteria and checked the full posting for omissions</label
              >
            </section>
            <section
              v-if="revealed && reviewStep === 'evidence'"
              aria-label="Evidence support review"
              class="space-y-4"
            >
              <h3 class="text-lg font-semibold">Check model evidence</h3>
              <ReviewGuide kind="evidence" />
              <p v-if="!job.evidence.length">
                No matching saved assessment is available. You can still label candidate fit and
                record requirements; no model output has been fabricated.
              </p>
              <div
                v-for="(row, n) in job.evidence"
                :key="row.id"
                class="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700"
              >
                <p class="font-semibold">
                  {{ row.provider }} · {{ row.model }} · {{ row.requirement }} · {{ row.verdict }}
                </p>
                <p>{{ row.explanation }}</p>
                <p class="text-sm">
                  Posting quote ({{ row.job_quote_found ? 'found' : 'not found' }}):
                  {{ row.job_quote || 'None' }}
                </p>
                <p class="text-sm">
                  Profile quote ({{ row.profile_quote_found ? 'found' : 'not found' }}):
                  {{ row.resume_quote || 'None' }}
                </p>
                <label class="field-label"
                  >Does the evidence justify this verdict and explanation?<select
                    v-model="draft.evidence![row.id]!.support"
                    class="field"
                    :aria-label="`Evidence ${n + 1} support`"
                  >
                    <option :value="null">Unreviewed</option>
                    <option value="supported">Supported</option>
                    <option value="unsupported">Unsupported</option>
                    <option value="uncertain">Uncertain</option>
                  </select></label
                >
                <label class="field-label"
                  >Your requirement verdict<select
                    v-model="draft.evidence![row.id]!.verdict"
                    class="field"
                    :aria-label="`Evidence ${n + 1} verdict`"
                  >
                    <option :value="null">Unreviewed</option>
                    <option value="met">Met</option>
                    <option value="partial">Partially met</option>
                    <option value="not_met">Not met</option>
                    <option value="unknown">Unknown</option>
                  </select></label
                >
                <label class="field-label"
                  >Evidence review notes<textarea
                    v-model="draft.evidence![row.id]!.notes"
                    class="field"
                    maxlength="3000"
                  />
                </label>
              </div>
            </section>
          </fieldset>
          <div
            class="sticky bottom-0 flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
          >
            <button class="btn-primary" type="submit" :disabled="busy">Save job review</button>
            <p class="text-sm">
              {{ dirty ? 'Unsaved review changes' : 'No unsaved changes' }}. Partial reviews are
              welcome.
            </p>
          </div>
        </form>
      </template>
    </template>
  </div>
</template>

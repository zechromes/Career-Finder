<!-- Resolve a job deep link and expose its posting and model evidence in accessible tabs. -->
<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { usePipelineStore } from '../stores/pipeline'
import { jobKey, useJobsStore } from '../stores/jobs'
import EvaluationEvidence from '../components/EvaluationEvidence.vue'
import TailoredResume from '../components/TailoredResume.vue'
import JobActions from '../components/JobActions.vue'
import CompanyLogo from '../components/CompanyLogo.vue'
import JobDescription from '../components/JobDescription.vue'
import ErrorState from '../components/ErrorState.vue'
import EmptyState from '../components/EmptyState.vue'
import Tabs from '../components/Tabs.vue'
import { fitChipClass, fitLabel } from '../utils/fitCategory'
const route = useRoute()
const router = useRouter()
const tabs = [
  { value: 'overview', label: 'Overview' },
  { value: 'description', label: 'Job description' },
  { value: 'evaluation', label: 'Evaluation evidence' },
  { value: 'resume', label: 'Tailored resume' },
]
const activeTab = computed(() =>
  tabs.some((tab) => tab.value === route.query.section) ? String(route.query.section) : 'overview',
)
// Keep the selected detail section in the URL for deep-link navigation.
function selectTab(key: string) {
  router.replace({ query: { ...route.query, section: key } })
}
const store = usePipelineStore()
const actions = useJobsStore()
const runId = computed(() => String(route.params.runId))
const job = computed(() => {
  if (store.run?.id !== runId.value) return undefined
  return [...(store.run.recommendations || []), ...(store.run.excluded_recommendations || [])].find(
    (item) => jobKey(item) === route.query.job,
  )
})
const applicationUrl = computed(() => {
  try {
    const url = new URL(job.value?.apply_url || '')
    return ['http:', 'https:'].includes(url.protocol) ? url.href : ''
  } catch {
    return ''
  }
})
const location = computed(() => {
  const value = job.value?.location?.trim()
  return !value || value.toLowerCase() === 'none' ? 'Worldwide' : value
})
const postedDate = computed(() => {
  const value = job.value?.posted_at
  const date = value ? new Date(value) : null
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' })
    : 'Not provided by the job board'
})
const verdict = computed(() => fitLabel(job.value?.fit_category))
watch(
  runId,
  async (id) => {
    actions.load(id)
    await store.attach(id)
  },
  { immediate: true },
)
watch([() => store.run?.id, () => store.run?.saved_profile_id], () => {
  if (store.run) void actions.sync(store.run)
})
onBeforeUnmount(() => store.stop())
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <div class="mb-6 flex flex-wrap items-center justify-between gap-4">
    <RouterLink :to="`/run/${runId}/results`" class="btn-secondary">← Back to results</RouterLink>
    <div v-if="job" class="flex items-center gap-3"><JobActions :job="job" inline /></div>
  </div>
  <h1 class="sr-only">Job details</h1>
  <p v-if="store.connecting" class="panel" role="status">Loading job details…</p>
  <ErrorState v-else-if="store.error" title="Could not load job" :message="store.error"
    ><button class="btn-secondary" @click="store.attach(runId)">Retry</button></ErrorState
  >
  <div v-else-if="job" class="space-y-6">
    <header class="panel">
      <p class="eyebrow">{{ job.source || 'Job posting' }}</p>
      <div class="mt-4 flex items-start gap-4">
        <CompanyLogo :company="job.company" :src="job.company_logo" />
        <div class="min-w-0">
          <h2 class="break-words text-3xl font-bold leading-tight sm:text-4xl">{{ job.title }}</h2>
          <p class="mt-3 text-lg text-slate-600 dark:text-slate-300">
            {{ job.company || 'Company unavailable' }}
          </p>
        </div>
      </div>
      <dl
        class="mt-8 grid gap-6 border-y border-slate-200 py-6 text-sm sm:grid-cols-2 lg:grid-cols-4 dark:border-slate-700"
      >
        <div>
          <dt class="text-slate-500 dark:text-slate-400">Location</dt>
          <dd class="mt-2 font-medium">{{ location }}</dd>
        </div>
        <div>
          <dt class="text-slate-500 dark:text-slate-400">Work arrangement</dt>
          <dd class="mt-2 font-medium">
            {{ !job.work_type || job.work_type === 'unknown' ? 'Not specified' : job.work_type }}
          </dd>
        </div>
        <div>
          <dt class="text-slate-500 dark:text-slate-400">Salary</dt>
          <dd class="mt-2 font-medium">{{ job.salary || 'Not specified' }}</dd>
        </div>
        <div>
          <dt class="text-slate-500 dark:text-slate-400">Date posted</dt>
          <dd class="mt-2 font-medium">{{ postedDate }}</dd>
        </div>
      </dl>
      <div class="mt-6 flex flex-wrap items-center justify-between gap-4">
        <p class="text-sm text-slate-600 dark:text-slate-300">
          Posting availability has not been verified.
        </p>
        <a
          v-if="applicationUrl"
          :href="applicationUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="btn-primary"
          :aria-label="`View application for ${job.title} at ${job.company} (opens in a new tab)`"
          >View application ↗</a
        >
        <p v-else class="text-sm">Application link unavailable</p>
      </div>
    </header>
    <Tabs
      :tabs="tabs"
      :model-value="activeTab"
      label="Job detail sections"
      id-prefix="job"
      @update:model-value="selectTab"
    />
    <section
      v-show="activeTab === 'overview'"
      id="job-panel-overview"
      role="tabpanel"
      aria-labelledby="job-tab-overview"
      tabindex="0"
      class="panel"
    >
      <div class="flex flex-wrap items-center justify-between gap-4">
        <h2 id="overall-assessment-heading" class="text-xl font-bold">Overall assessment</h2>
        <span
          class="rounded-full px-4 py-2 text-sm font-semibold"
          :class="fitChipClass(job.fit_category)"
          >{{ verdict }}</span
        >
      </div>
      <p v-if="job.score != null" class="mt-4 text-2xl font-bold">
        {{ `${job.score} / 100`
        }}<span
          class="ml-3 text-sm font-normal text-slate-600 dark:text-slate-300"
          >{{
            Object.keys(job.model_evaluations || {}).length ? 'Average model score' : 'Match score'
          }}</span
        >
      </p>
      <p class="mt-4 max-w-4xl whitespace-pre-line leading-7 text-slate-700 dark:text-slate-200">
        {{ job.rationale || 'Assessment is not available yet.' }}
      </p>
      <p v-if="job.assessment_summary" class="mt-2 text-sm text-slate-600 dark:text-slate-300">
        {{ job.assessment_summary }}
      </p>
      <p v-if="job.mismatch_reason" class="mt-3 leading-7 text-amber-900 dark:text-amber-200">
        {{ job.mismatch_reason }}
      </p>
    </section>
    <section
      v-show="activeTab === 'description'"
      id="job-panel-description"
      role="tabpanel"
      aria-labelledby="job-tab-description"
      tabindex="0"
    >
      <h2 id="description-heading" class="mb-6 text-2xl font-bold">Full job description</h2>
      <JobDescription :text="job.job_description" />
    </section>
    <div
      v-show="activeTab === 'evaluation'"
      id="job-panel-evaluation"
      role="tabpanel"
      aria-labelledby="job-tab-evaluation"
      tabindex="0"
    >
      <EvaluationEvidence :job="job" />
    </div>
    <div
      v-show="activeTab === 'resume'"
      id="job-panel-resume"
      role="tabpanel"
      aria-labelledby="job-tab-resume"
      tabindex="0"
    >
      <TailoredResume :job="job" :run-id="runId" />
    </div>
  </div>
  <p v-else-if="store.running" class="panel" role="status">
    This job is not available yet. Results are still arriving.
  </p>
  <EmptyState
    v-else
    title="Job not found"
    message="This job may no longer be available after a new search. Return to the results to select a job."
  />
</template>

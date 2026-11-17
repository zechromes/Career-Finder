<!-- Present a job summary, recorded dates, assessment details, and application link. -->
<script setup lang="ts">
import DateAdded from './DateAdded.vue'
import { RouterLink } from 'vue-router'
import { jobKey } from '../stores/jobs'
import { computed, useId } from 'vue'
import { groupRequirements } from '../utils/requirementGroups'
import { fitChipClass, fitLabel } from '../utils/fitCategory'
import type { Job } from '../types/domain'
import JobActions from './JobActions.vue'
import CompanyLogo from './CompanyLogo.vue'
const props = defineProps<{ job: Job; runId?: string; expanded?: boolean }>()
const titleId = useId()
const requirementGroups = computed(() => groupRequirements(props.job.candidate_requirements || []))
const verdict = computed(() => fitLabel(props.job.fit_category))
// Only HTTP(S) application links are actionable; absent metadata uses explicit fallbacks.
const url = computed(() => {
  try {
    const value = new URL(props.job.apply_url || '')
    return ['http:', 'https:'].includes(value.protocol) ? value.href : ''
  } catch {
    return ''
  }
})
const location = computed(() => {
  const value = props.job.location?.trim()
  return !value || value.toLowerCase() === 'none' ? 'Worldwide' : value
})
const posted = computed(() => {
  if (!props.job.posted_at) return 'Posting date unavailable'
  const date = new Date(props.job.posted_at)
  if (Number.isNaN(date.getTime())) return 'Posting date unavailable'
  return `Posted on ${date.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}`
})
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <article
    :aria-labelledby="titleId"
    class="job-card flex min-w-0 flex-col rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5 shadow-sm transition-shadow hover:shadow-md focus-within:ring-2 focus-within:ring-indigo-400 sm:p-6"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <span
        class="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-1 text-xs text-slate-700 dark:text-slate-200"
        >{{ job.source || 'Unknown source' }}</span
      ><span class="text-xs text-slate-600 dark:text-slate-300">{{ posted }}</span
      ><JobActions :job="job" />
    </div>
    <div class="mt-4 flex items-start gap-3">
      <CompanyLogo :company="job.company" :src="job.company_logo" />
      <div class="min-w-0">
        <h3 :id="titleId" class="break-words text-xl font-semibold leading-7">
          <RouterLink
            v-if="runId"
            :to="{ path: `/run/${runId}/job`, query: { job: jobKey(job) } }"
            class="text-indigo-700 underline-offset-4 hover:underline dark:text-indigo-300"
            >{{ job.title }}</RouterLink
          ><template v-else>{{ job.title }}</template>
        </h3>
        <p class="mt-1 font-medium text-slate-700 dark:text-slate-200">
          {{ job.company || 'Company unavailable' }}
        </p>
      </div>
    </div>
    <p class="mt-1 text-sm text-slate-600 dark:text-slate-300">
      {{ location }} ·
      {{
        !job.work_type || job.work_type === 'unknown'
          ? 'Work arrangement not specified'
          : job.work_type
      }}
    </p>
    <p class="mt-2 text-xs text-slate-600 dark:text-slate-300">
      Date added: <DateAdded :value="job.added_at" />
    </p>
    <div class="mt-4 flex flex-wrap items-center gap-2">
      <span
        class="rounded-lg px-3 py-1 text-sm font-semibold"
        :class="fitChipClass(job.fit_category)"
        ><template v-if="job.score != null"
          >{{ Object.keys(job.model_evaluations || {}).length ? 'Average ' : ''
          }}{{ job.score }}/100 · </template
        >{{ verdict }}</span
      ><span
        title="The original posting has not been checked for current availability."
        class="text-xs text-slate-600 dark:text-slate-300"
        >Not verified</span
      >
    </div>
    <details
      :open="expanded"
      class="mt-5 rounded-xl border border-slate-200 px-4 text-sm dark:border-slate-700"
    >
      <summary
        :aria-label="`Assessment details for ${job.title} at ${job.company}`"
        class="cursor-pointer py-3 font-semibold text-indigo-700 dark:text-indigo-300"
      >
        Assessment details
      </summary>
      <div class="space-y-5 pb-4 leading-6">
        <section>
          <h4 class="font-semibold">Match rationale</h4>
          <p class="mt-1 whitespace-pre-line text-slate-700 dark:text-slate-200">
            {{ job.rationale || 'Rationale unavailable.' }}
          </p>
          <p v-if="job.assessment_summary" class="mt-2 text-sm text-slate-600 dark:text-slate-300">
            {{ job.assessment_summary }}
          </p>
          <p v-if="job.mismatch_reason" class="mt-2 text-amber-900 dark:text-amber-300">
            {{ job.mismatch_reason }}
          </p>
        </section>
        <p
          v-if="job.description_available === false"
          class="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-300"
        >
          The source did not return a job description. Company details, requirements and skills gaps
          cannot be reliably assessed. Run a new search to retry description capture.
        </p>
        <section>
          <h4 class="font-semibold">About the company</h4>
          <p class="mt-1 text-slate-700 dark:text-slate-200">
            {{ job.about_company || 'Company information is unavailable for this assessment.' }}
          </p>
        </section>
        <section>
          <h4 class="font-semibold">What the company needs from the candidate</h4>
          <div v-if="requirementGroups.length" class="mt-3 space-y-3">
            <div
              v-for="group in requirementGroups"
              :key="group.title"
              class="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-950"
            >
              <h5 class="mb-3 text-sm font-semibold text-indigo-700 dark:text-indigo-300">
                {{ group.title }}
              </h5>
              <ul
                class="list-disc space-y-3 pl-4 text-sm leading-6 text-slate-700 dark:text-slate-200"
              >
                <li v-for="item in group.items" :key="item" class="pl-1">{{ item }}</li>
              </ul>
            </div>
          </div>
          <p v-else class="mt-1 text-slate-700 dark:text-slate-200">
            Candidate requirements are unavailable for this assessment.
          </p>
        </section>
        <section v-if="job.salary">
          <h4 class="font-semibold">Salary</h4>
          <p class="mt-1 text-slate-700 dark:text-slate-200">{{ job.salary }}</p>
        </section>
        <section>
          <h4 class="font-semibold">Missing skills</h4>
          <div v-if="job.missing_skills?.length" class="mt-2 flex flex-wrap gap-2">
            <span
              v-for="skill in job.missing_skills"
              :key="skill"
              class="rounded-lg bg-amber-50 dark:bg-amber-950 px-2 py-1 text-xs text-amber-900 dark:text-amber-300"
              >{{ skill }}</span
            >
          </div>
          <p v-else class="mt-1 text-slate-600 dark:text-slate-300">
            {{
              job.description_available === false || !job.candidate_requirements?.length
                ? 'Missing skills could not be assessed because job requirements are unavailable.'
                : 'No specific missing skills were identified from the available requirements. This does not confirm that every requirement is met.'
            }}
          </p>
        </section>
      </div>
    </details>
    <div class="mt-5 border-t border-slate-100 pt-5 dark:border-slate-800">
      <a
        v-if="url"
        :href="url"
        target="_blank"
        rel="noopener noreferrer"
        class="btn-primary w-full"
        :aria-label="`View application for ${job.title} at ${job.company} (opens in a new tab)`"
        >View application</a
      >
      <p v-else class="text-sm text-slate-600 dark:text-slate-300">Application link unavailable</p>
    </div>
  </article>
</template>

<!-- Component presentation and interaction styling. -->
<style scoped>
.job-card button,
.job-card a.btn-primary {
  min-height: 2.75rem;
}
summary:focus-visible {
  outline: 3px solid #818cf8;
  outline-offset: 4px;
  border-radius: 0.5rem;
}
</style>

<!-- Show one model’s requirement evidence at a time without mixing provider verdicts. -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Job } from '../types/domain'
import { requirementSection } from '../utils/requirementSections'
const props = defineProps<{ job: Job }>()
const selected = ref('')
const providerNames: Record<string, string> = {
  claude: 'Anthropic Claude',
  gpt: 'OpenAI GPT',
  gemini: 'Google Gemini',
}
// Preserve provider-specific verdicts instead of presenting combined evidence as one model’s claim.
const models = computed(() => Object.entries(props.job.model_evaluations || {}))
const activeKey = computed(() =>
  models.value.some(([key]) => key === selected.value)
    ? selected.value
    : models.value[0]?.[0] || '',
)
const assessment = computed(() =>
  activeKey.value ? props.job.model_evaluations?.[activeKey.value] : props.job,
)
const status = computed(() => (activeKey.value ? assessment.value?.status : 'complete'))
const evidence = computed(() => assessment.value?.requirement_verdicts || [])
// A verdict filter and the long-summary toggle; both reset for another model or job.
const filter = ref('')
const fullSummary = ref(false)
watch([activeKey, () => props.job.jobId || props.job.apply_url], () => {
  filter.value = ''
  fullSummary.value = false
})
const SUMMARY_LIMIT = 400
const longSummary = computed(
  () =>
    (assessment.value?.rationale?.length || 0) > SUMMARY_LIMIT ||
    (assessment.value?.about_company?.length || 0) > SUMMARY_LIMIT,
)
// Gaps first, required before preferred, so the list opens on what needs attention.
const verdictOrder = ['not_met', 'partial', 'unknown', 'met']
const importanceOrder = ['must_have', 'unclear', 'nice_to_have']
const rank = (order: string[], value?: string | null) => {
  const index = order.indexOf(value || '')
  return index < 0 ? order.length : index
}
const sections = computed(() => {
  const grouped = new Map<string, typeof evidence.value>()
  for (const row of evidence.value) {
    if (filter.value && row.verdict !== filter.value) continue
    const title =
      row.section || requirementSection(props.job.job_description || '', row.job_quote || '')
    grouped.set(title, [...(grouped.get(title) || []), row])
  }
  return [...grouped].map(([title, items]) => ({
    title,
    items: [...items].sort(
      (a, b) =>
        rank(verdictOrder, a.verdict) - rank(verdictOrder, b.verdict) ||
        rank(importanceOrder, a.importance) - rank(importanceOrder, b.importance),
    ),
  }))
})
const importanceLabels: Record<string, string> = {
  must_have: 'Required',
  nice_to_have: 'Preferred',
}
// New assessments list several resume quotes; older ones hold a single quote.
type Evidence = {
  resume_quote?: string
  resume_quotes?: string[]
  resume_quotes_verified?: boolean[]
  resume_evidence_verified?: boolean
}
function resumeQuotes(item: Evidence) {
  return item.resume_quotes?.length
    ? item.resume_quotes
    : item.resume_quote
      ? [item.resume_quote]
      : []
}
function quoteVerified(item: Evidence, index: number) {
  return item.resume_quotes_verified?.[index] ?? !!item.resume_evidence_verified
}
const labels: Record<string, string> = {
  met: 'Met',
  partial: 'Partially met',
  not_met: 'Not met',
  unknown: 'Unknown',
  strong_match: 'Strong match',
  review: 'For review',
  not_suitable: 'Not recommended',
  pending: 'Waiting',
  failed: 'Failed',
  skipped: 'Skipped',
}
const colors: Record<string, string> = {
  met: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200',
  partial: 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200',
  not_met: 'bg-rose-100 text-rose-900 dark:bg-rose-950 dark:text-rose-200',
  unknown: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
}
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <section class="panel" aria-labelledby="evaluation-heading">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="eyebrow">Model comparison</p>
        <h2 id="evaluation-heading" class="mt-2 text-2xl font-bold">Evaluation evidence</h2>
        <p class="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Compare verdicts, then inspect the evidence behind each requirement.
        </p>
      </div>
      <span
        v-if="models.length"
        class="rounded-full bg-indigo-50 px-3 py-1 text-sm text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200"
        >{{ models.filter(([, row]) => row.status === 'complete').length }} /
        {{ models.length }} complete</span
      >
    </div>
    <div
      v-if="models.length"
      role="group"
      aria-label="Evaluation models"
      class="mt-6 grid gap-3 md:grid-cols-3"
    >
      <button
        v-for="[key, model] in models"
        :key="key"
        type="button"
        :aria-pressed="activeKey === key"
        @click="selected = key"
        class="rounded-xl border-2 p-4 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
        :class="
          activeKey === key
            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950'
            : 'border-slate-200 dark:border-slate-700'
        "
      >
        <span class="block text-sm font-bold uppercase tracking-wide">{{
          providerNames[key] || key
        }}</span
        ><span class="mt-1 block break-words text-xs text-slate-600 dark:text-slate-300">{{
          model.evaluation_model_id
        }}</span>
        <span class="mt-4 block text-2xl font-bold">{{
          model.status !== 'complete'
            ? labels[model.status]
            : model.score == null
              ? labels[model.fit_category]
              : `${model.score}/100`
        }}</span
        ><span
          v-if="model.status === 'complete' && model.score != null"
          class="mt-1 block text-sm"
          >{{ labels[model.fit_category] }}</span
        >
      </button>
    </div>
    <p v-if="models.length" class="mt-3 text-xs text-slate-600 dark:text-slate-300">
      Each model decides its own verdict. The overall verdict needs every model to agree;
      disagreement or an incomplete assessment keeps it For review.
    </p>
    <div
      v-if="status === 'failed'"
      role="status"
      class="mt-6 rounded-xl border border-rose-200 bg-rose-50 p-5 text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200"
    >
      <h3 class="font-semibold">This model could not evaluate the job</h3>
      <p class="mt-2">{{ assessment?.error || 'The provider request failed.' }}</p>
      <p class="mt-2 text-sm">Return to results to retry failed model assessments.</p>
    </div>
    <div
      v-else-if="status === 'skipped'"
      role="status"
      class="mt-6 rounded-xl bg-slate-50 p-5 dark:bg-slate-950"
    >
      <h3 class="font-semibold">This model was skipped</h3>
      <p class="mt-2">{{ assessment?.error || 'The model was unavailable.' }}</p>
      <p class="mt-2 text-sm">
        The overall verdict uses the other models. Return to results to retry skipped models.
      </p>
    </div>
    <p
      v-else-if="status === 'pending'"
      role="status"
      class="mt-6 rounded-xl bg-slate-50 p-5 dark:bg-slate-950"
    >
      Waiting for this model’s assessment. Results will appear automatically.
    </p>
    <template v-else>
      <div class="mt-6 rounded-xl bg-slate-50 p-5 dark:bg-slate-950">
        <h3 class="font-semibold">Assessment summary</h3>
        <p
          class="mt-2 max-w-prose whitespace-pre-wrap leading-7"
          :class="{ 'line-clamp-4': longSummary && !fullSummary }"
        >
          {{ assessment?.rationale || 'Rationale unavailable.' }}
        </p>
        <button
          v-if="longSummary"
          type="button"
          class="mt-2 text-sm font-semibold text-indigo-700 underline dark:text-indigo-300"
          :aria-expanded="fullSummary"
          @click="fullSummary = !fullSummary"
        >
          {{ fullSummary ? 'Show less' : 'Show full summary' }}
        </button>
        <p
          v-if="assessment?.mismatch_reason"
          class="mt-3 font-medium text-amber-900 dark:text-amber-200"
        >
          {{ assessment.mismatch_reason }}
        </p>
        <p v-if="assessment?.rule_exception" class="mt-3">
          <span class="font-semibold">Rule set aside:</span> {{ assessment.rule_exception }}
        </p>
        <p class="mt-3 text-xs text-slate-600 dark:text-slate-300">
          {{ assessment?.evaluation_model_id || 'Historical assessment' }} ·
          {{ assessment?.score_method || 'Scoring method unavailable' }}
        </p>
      </div>
      <div class="mt-5 grid gap-5 md:grid-cols-2">
        <section v-if="assessment?.about_company">
          <h3 class="font-semibold">About the company</h3>
          <p class="mt-2 leading-6" :class="{ 'line-clamp-3': longSummary && !fullSummary }">
            {{ assessment.about_company }}
          </p>
        </section>
        <section>
          <h3 class="font-semibold">Missing skills</h3>
          <div class="mt-2 flex flex-wrap gap-2">
            <span
              v-for="skill in assessment?.missing_skills || []"
              :key="skill"
              class="rounded-lg bg-amber-50 px-3 py-1 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200"
              >{{ skill }}</span
            >
            <p
              v-if="!assessment?.missing_skills?.length"
              class="text-sm text-slate-600 dark:text-slate-300"
            >
              No specific gaps recorded.
            </p>
          </div>
        </section>
        <section v-if="assessment?.salary">
          <h3 class="font-semibold">Salary</h3>
          <p class="mt-2">{{ assessment.salary }}</p>
        </section>
        <section v-if="assessment?.experience_alignment">
          <h3 class="font-semibold">Experience alignment</h3>
          <p class="mt-2">{{ assessment.experience_alignment }}</p>
          <p v-if="assessment.minimum_professional_years != null" class="mt-1 text-sm">
            Minimum: {{ assessment.minimum_professional_years }} years
          </p>
          <p v-if="assessment.required_experience_evidence" class="mt-2 text-sm">
            {{ assessment.required_experience_evidence }}
          </p>
        </section>
      </div>
      <div v-if="evidence.length" class="mt-8 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 class="text-lg font-semibold">Requirements</h3>
          <p class="mt-0.5 text-xs text-slate-600 dark:text-slate-300">
            Gaps first. Open a requirement to compare the posting with your resume.
          </p>
        </div>
        <div role="group" aria-label="Show requirements by verdict" class="flex flex-wrap gap-2">
          <button
            v-for="key in verdictOrder"
            :key="key"
            type="button"
            class="rounded-full px-3 py-1 text-sm font-medium ring-offset-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-40 dark:ring-offset-slate-900"
            :class="[colors[key], filter === key ? 'ring-2 ring-slate-700 dark:ring-slate-200' : '']"
            :aria-pressed="filter === key"
            :disabled="!evidence.some((item) => item.verdict === key)"
            @click="filter = filter === key ? '' : key"
          >
            {{ evidence.filter((item) => item.verdict === key).length }} {{ labels[key] }}
          </button>
        </div>
      </div>
      <section v-for="section in sections" :key="section.title" class="mt-5">
        <h4
          class="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400"
        >
          {{ section.title }}
        </h4>
        <ul
          class="divide-y divide-slate-200 rounded-xl border border-slate-200 dark:divide-slate-700 dark:border-slate-700"
        >
          <li v-for="(item, index) in section.items" :key="item.requirement_id || index">
            <details class="group">
              <summary
                class="flex cursor-pointer list-none items-start gap-3 p-4 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 dark:hover:bg-slate-800 [&::-webkit-details-marker]:hidden"
              >
                <span
                  class="mt-0.5 w-28 shrink-0 rounded-full px-2.5 py-1 text-center text-xs font-semibold"
                  :class="colors[item.verdict]"
                  >{{ labels[item.verdict] }}</span
                >
                <span class="min-w-0 flex-1">
                  <span class="break-words font-medium">{{ item.requirement }}</span>
                  <span class="ml-2 text-xs text-slate-500 dark:text-slate-400">{{
                    importanceLabels[item.importance || ''] || 'Importance unclear'
                  }}</span>
                  <span
                    v-if="item.explanation"
                    class="mt-1 block text-sm leading-6 text-slate-600 dark:text-slate-300"
                    >{{ item.explanation }}</span
                  >
                </span>
                <span
                  aria-hidden="true"
                  class="mt-1 shrink-0 text-slate-400 transition-transform group-open:rotate-180 motion-reduce:transition-none"
                  >▾</span
                >
              </summary>
              <div class="grid gap-5 px-4 pb-5 sm:pl-[8.75rem] md:grid-cols-2">
                <div class="min-w-0">
                  <p
                    class="text-xs font-bold uppercase tracking-wide text-indigo-700 dark:text-indigo-300"
                  >
                    Job posting
                    <span class="ml-1 font-normal normal-case tracking-normal text-slate-500">{{
                      item.job_evidence_verified ? '· Verified against posting' : '· Quote not verified'
                    }}</span>
                  </p>
                  <blockquote
                    class="mt-2 whitespace-pre-wrap break-words border-l-2 border-indigo-300 pl-3 text-sm leading-6"
                  >
                    {{ item.job_quote || 'No supporting quote recorded.' }}
                  </blockquote>
                </div>
                <div class="min-w-0">
                  <p
                    class="text-xs font-bold uppercase tracking-wide text-teal-700 dark:text-teal-300"
                  >
                    Your resume
                  </p>
                  <template v-if="resumeQuotes(item).length">
                    <div v-for="(quote, quoteIndex) in resumeQuotes(item)" :key="quoteIndex" class="mt-2">
                      <blockquote
                        class="whitespace-pre-wrap break-words border-l-2 border-teal-300 pl-3 text-sm leading-6"
                      >
                        {{ quote }}
                      </blockquote>
                      <p class="mt-1 pl-3 text-xs text-slate-500 dark:text-slate-400">
                        {{
                          quoteVerified(item, quoteIndex)
                            ? 'Verified against resume'
                            : 'Quote not verified'
                        }}
                      </p>
                    </div>
                  </template>
                  <blockquote
                    v-else
                    class="mt-2 whitespace-pre-wrap break-words border-l-2 border-teal-300 pl-3 text-sm leading-6"
                  >
                    No supporting quote recorded.
                  </blockquote>
                </div>
              </div>
            </details>
          </li>
        </ul>
      </section>
      <div
        v-if="!evidence.length"
        class="mt-4 rounded-xl border border-dashed border-slate-300 p-5 dark:border-slate-700"
      >
        <p>Requirement-level evidence is unavailable for this assessment.</p>
        <ul v-if="assessment?.candidate_requirements?.length" class="mt-3 list-disc space-y-2 pl-5">
          <li v-for="requirement in assessment.candidate_requirements" :key="requirement">
            {{ requirement }}
          </li>
        </ul>
      </div>
    </template>
  </section>
</template>

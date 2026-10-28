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
// Keep independent navigation for each source section; reset when switching models.
const indices = ref<Record<string, number>>({})
watch(activeKey, () => {
  indices.value = {}
})
watch(
  () => props.job.jobId || props.job.apply_url,
  () => {
    indices.value = {}
  },
)
const sections = computed(() => {
  const grouped = new Map<string, typeof evidence.value>()
  for (const row of evidence.value) {
    const title =
      row.section || requirementSection(props.job.job_description || '', row.job_quote || '')
    grouped.set(title, [...(grouped.get(title) || []), row])
  }
  return [...grouped].map(([title, items]) => {
    const index = Math.min(indices.value[title] || 0, items.length - 1)
    return { title, items, index, visible: items.slice(index, index + 1) }
  })
})
function moveRequirement(title: string, direction: number) {
  const section = sections.value.find((item) => item.title === title)
  if (section)
    indices.value[title] = Math.max(
      0,
      Math.min(section.items.length - 1, section.index + direction),
    )
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
          model.status === 'complete'
            ? model.score == null
              ? 'Unscored'
              : `${model.score}/100`
            : labels[model.status]
        }}</span
        ><span v-if="model.status === 'complete'" class="mt-1 block text-sm">{{
          labels[model.fit_category]
        }}</span>
      </button>
    </div>
    <p v-if="models.length" class="mt-3 text-xs text-slate-600 dark:text-slate-300">
      The overall score averages all three scored assessments. Disagreement or an incomplete
      assessment keeps the overall verdict For review.
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
        <p class="mt-2 whitespace-pre-wrap leading-7">
          {{ assessment?.rationale || 'Rationale unavailable.' }}
        </p>
        <p
          v-if="assessment?.mismatch_reason"
          class="mt-3 font-medium text-amber-900 dark:text-amber-200"
        >
          {{ assessment.mismatch_reason }}
        </p>
        <p class="mt-3 text-xs text-slate-600 dark:text-slate-300">
          {{ assessment?.evaluation_model_id || 'Historical assessment' }} ·
          {{ assessment?.score_method || 'Scoring method unavailable' }}
        </p>
      </div>
      <div class="mt-5 grid gap-5 md:grid-cols-2">
        <section v-if="assessment?.about_company">
          <h3 class="font-semibold">About the company</h3>
          <p class="mt-2 leading-6">{{ assessment.about_company }}</p>
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
      <div class="mt-6 flex flex-wrap gap-2" aria-label="Requirement summary">
        <span
          v-for="key in ['met', 'partial', 'not_met', 'unknown']"
          :key="key"
          class="rounded-full px-3 py-1 text-sm font-medium"
          :class="colors[key]"
          >{{ evidence.filter((item) => item.verdict === key).length }} {{ labels[key] }}</span
        >
      </div>
      <section
        v-for="section in sections"
        :key="section.title"
        class="mt-6"
        role="region"
        aria-roledescription="carousel"
        :aria-label="
          sections.length === 1 ? 'Requirement evidence' : `${section.title} requirement evidence`
        "
        @keydown.left.prevent="moveRequirement(section.title, -1)"
        @keydown.right.prevent="moveRequirement(section.title, 1)"
      >
        <h3 class="mb-4 text-lg font-semibold">{{ section.title }}</h3>
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <p
            role="status"
            aria-live="polite"
            aria-atomic="true"
            class="text-sm font-medium text-slate-600 dark:text-slate-300"
          >
            Requirement {{ section.index + 1 }} of {{ section.items.length }}
          </p>
          <div class="flex gap-2">
            <button
              type="button"
              aria-label="Previous requirement"
              :disabled="section.index === 0"
              @click="moveRequirement(section.title, -1)"
              class="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-600 dark:hover:bg-slate-800"
            >
              ← Previous
            </button>
            <button
              type="button"
              aria-label="Next requirement"
              :disabled="section.index === section.items.length - 1"
              @click="moveRequirement(section.title, 1)"
              class="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-600 dark:hover:bg-slate-800"
            >
              Next →
            </button>
          </div>
        </div>
        <div
          v-for="item in section.visible"
          :key="section.index"
          role="group"
          aria-roledescription="slide"
          :aria-label="`Requirement ${section.index + 1} of ${section.items.length}`"
          class="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700"
        >
          <div
            class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 p-5 dark:border-slate-700"
          >
            <div class="min-w-0 flex-1">
              <p
                class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
              >
                {{
                  item.importance === 'must_have'
                    ? 'Required'
                    : item.importance === 'nice_to_have'
                      ? 'Preferred'
                      : 'Importance unclear'
                }}
              </p>
              <h3 class="mt-1 break-words font-semibold">{{ item.requirement }}</h3>
            </div>
            <span
              class="rounded-full px-3 py-1 text-sm font-semibold"
              :class="colors[item.verdict]"
              >{{ labels[item.verdict] }}</span
            >
            <p
              v-if="item.explanation"
              class="w-full text-sm leading-6 text-slate-600 dark:text-slate-300"
            >
              {{ item.explanation }}
            </p>
          </div>
          <div class="grid gap-5 p-5 md:grid-cols-2">
            <div>
              <p
                class="text-xs font-bold uppercase tracking-wide text-indigo-700 dark:text-indigo-300"
              >
                Job posting
              </p>
              <blockquote
                class="mt-3 whitespace-pre-wrap break-words border-l-2 border-indigo-300 pl-3 text-sm leading-6"
              >
                {{ item.job_quote || 'No supporting quote recorded.' }}
              </blockquote>
              <p class="mt-3 text-xs text-slate-600 dark:text-slate-300">
                {{ item.job_evidence_verified ? 'Verified against posting' : 'Quote not verified' }}
              </p>
            </div>
            <div>
              <p class="text-xs font-bold uppercase tracking-wide text-teal-700 dark:text-teal-300">
                Your resume
              </p>
              <blockquote
                class="mt-3 whitespace-pre-wrap break-words border-l-2 border-teal-300 pl-3 text-sm leading-6"
              >
                {{ item.resume_quote || 'No supporting quote recorded.' }}
              </blockquote>
              <p class="mt-3 text-xs text-slate-600 dark:text-slate-300">
                {{
                  item.resume_evidence_verified ? 'Verified against resume' : 'Quote not verified'
                }}
              </p>
            </div>
          </div>
        </div>
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

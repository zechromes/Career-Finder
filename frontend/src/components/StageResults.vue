<!-- Plain-language results for each RAG stage, from human fit labels only. -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { components } from '../types/api'
type S = components['schemas']
const props = defineProps<{ metrics: S['ReviewMetrics']; bundle: S['ReviewBundle'] }>()
type Tab = 'overview' | 'ingestion' | 'retrieval' | 'generation'
const tabs: { value: Tab; label: string }[] = [
  { value: 'overview', label: 'Overview' },
  { value: 'ingestion', label: '1. Ingestion' },
  { value: 'retrieval', label: '2. Retrieval' },
  { value: 'generation', label: '3. Generation' },
]
const tab = ref<Tab>('overview')
const names: Record<string, string> = { claude: 'Claude', gpt: 'GPT', gemini: 'Gemini' }
const percent = (value?: number | null) =>
  value == null ? 'Not available' : `${(value * 100).toFixed(0)}%`
const title = (id: string) => props.bundle.dataset.jobs.find((job) => job.id === id)?.title || id
// AI-assisted reviews are left out, as in every metric.
const counts = computed(() => {
  const reviews = Object.values(props.bundle.labels.jobs || {}).filter((r) => !r.ai_assisted)
  return {
    good: reviews.filter((r) => r.fit === 'strong_match').length,
    notFit: reviews.filter((r) => r.fit === 'not_suitable').length,
    unsure: reviews.filter((r) => r.fit === 'review').length,
  }
})
const stages = computed(() => props.metrics.stages)
const funnel = computed(() => {
  const f = stages.value.funnel
  return [
    { label: 'Recommended as a strong match', value: f.recommended },
    { label: 'Shown as needs review', value: f.needs_review },
    { label: 'Rejected by the AI (generation)', value: f.rejected_at_generation },
    { label: 'Shortlisted, but no saved verdict', value: f.not_assessed },
    { label: 'Not shortlisted (retrieval)', value: f.lost_at_retrieval },
  ].filter((row) => row.value || row.label.startsWith('Not shortlisted'))
})
const generationRows = computed(() => [
  ...Object.entries(stages.value.generation).map(([provider, value]) => ({
    name: `${names[provider] || provider}${value.model ? ` (${value.model})` : ''}`,
    value,
  })),
  ...(stages.value.app ? [{ name: 'App overall (combined)', value: stages.value.app }] : []),
])
const goodTotal = (value: S['GenerationMetrics']) =>
  (value.human_good.strong_match || 0) +
  (value.human_good.review || 0) +
  (value.human_good.not_suitable || 0)
</script>
<template>
  <section
    aria-label="Results so far"
    class="space-y-3 rounded-xl bg-slate-100 p-4 dark:bg-slate-800"
  >
    <h2 class="text-xl font-semibold">Results so far</h2>
    <p v-if="!counts.good && !counts.notFit">
      No results yet. Label some jobs as Good fit or Not a fit to see how the app did.
    </p>
    <template v-else>
      <div class="flex flex-wrap gap-2" role="group" aria-label="Results by stage">
        <button
          v-for="item in tabs"
          :key="item.value"
          type="button"
          class="btn-secondary"
          :aria-pressed="tab === item.value"
          @click="tab = item.value"
        >
          {{ item.label }}
        </button>
      </div>

      <div v-if="tab === 'overview'" class="space-y-3">
        <p>
          You marked <strong>{{ counts.good }}</strong> jobs as Good fit,
          <strong>{{ counts.notFit }}</strong> as Not a fit and {{ counts.unsure }} as Not sure.
        </p>
        <p v-if="counts.good">
          The app's shortlist included
          <strong
            >{{ stages.funnel.good_fits - stages.funnel.lost_at_retrieval }} of your
            {{ stages.funnel.good_fits }}</strong
          >
          good fits ({{ percent(metrics.retrieval.observed_recall_at_k) }}).
        </p>
        <template v-if="counts.good">
          <h3 class="font-semibold">Where your {{ stages.funnel.good_fits }} good fits ended up</h3>
          <ul class="space-y-2">
            <li v-for="row in funnel" :key="row.label" class="space-y-1">
              <p>
                {{ row.label }}: <strong>{{ row.value }}</strong>
              </p>
              <div class="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                <div
                  class="h-full bg-indigo-600 dark:bg-indigo-400"
                  :style="{ width: `${(row.value / stages.funnel.good_fits) * 100}%` }"
                />
              </div>
            </li>
          </ul>
          <p class="text-sm">
            Ingestion losses are not tracked yet, so jobs dropped before ranking are not counted
            here.
          </p>
        </template>
        <p v-if="!stages.verdicts_available" class="text-sm">
          This dataset has no saved model verdicts, so generation outcomes are unknown. Run
          <code>python scripts/add_review_verdicts.py</code> while the original search still exists,
          or create a new dataset.
        </p>
      </div>

      <div v-else-if="tab === 'ingestion'" class="space-y-2">
        <p>
          <strong>Ingestion</strong> collects jobs from the job boards, filters them by location,
          date and exclusions, removes duplicates and prepares them for search.
        </p>
        <p>
          The app does not yet record the jobs it drops at this stage, so losses here cannot be
          measured. All {{ metrics.pool_size }} jobs in this dataset already made it through
          ingestion.
        </p>
      </div>

      <div v-else-if="tab === 'retrieval'" class="space-y-2">
        <p>
          <strong>Retrieval</strong> ranks the collected jobs against your profile and picks a
          shortlist for the AI models to assess.
        </p>
        <p v-if="counts.good">
          Found <strong>{{ percent(metrics.retrieval.observed_recall_at_k) }}</strong> of your good
          fits: {{ stages.funnel.good_fits - stages.funnel.lost_at_retrieval }} of
          {{ stages.funnel.good_fits }} were shortlisted.
        </p>
        <p v-if="metrics.retrieval.precision_on_labeled != null">
          Of the labeled jobs it shortlisted,
          <strong>{{ percent(metrics.retrieval.precision_on_labeled) }}</strong> were good fits.
        </p>
        <template v-if="stages.retrieval_missed.length">
          <h3 class="font-semibold">Good fits that were not shortlisted</h3>
          <ul class="list-disc space-y-1 pl-6">
            <li v-for="job in stages.retrieval_missed" :key="job.id">
              {{ job.title
              }}<span v-if="job.experienced_title" class="text-sm">
                · experienced-level title for your profile</span
              >
            </li>
          </ul>
        </template>
        <p class="text-sm">
          Rank positions were not saved, so how high good fits appeared within the shortlist cannot
          be measured.
        </p>
      </div>

      <div v-else class="space-y-3">
        <p>
          <strong>Generation</strong> is where the AI models read each shortlisted job and judge
          your fit. Only shortlisted jobs were assessed.
        </p>
        <p v-if="!stages.verdicts_available">
          This dataset has no saved model verdicts. Run
          <code>python scripts/add_review_verdicts.py</code> while the original search still exists,
          or create a new dataset.
        </p>
        <template v-else>
          <div
            class="overflow-x-auto"
            tabindex="0"
            role="region"
            aria-label="Model comparison table"
          >
            <table class="w-full min-w-[36rem] text-left text-sm">
              <caption class="sr-only">
                AI model verdicts compared with your labels
              </caption>
              <thead>
                <tr>
                  <th scope="col" class="py-2 pr-3">Model</th>
                  <th scope="col" class="py-2 pr-3">Jobs compared</th>
                  <th scope="col" class="py-2 pr-3">Agreed on your good fits</th>
                  <th scope="col" class="py-2 pr-3">Strong-match accuracy</th>
                  <th scope="col" class="py-2 pr-3">Good fits rejected</th>
                  <th scope="col" class="py-2">Failed</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in generationRows"
                  :key="row.name"
                  class="border-t border-slate-300 dark:border-slate-600"
                >
                  <th scope="row" class="py-2 pr-3 font-semibold">{{ row.name }}</th>
                  <td class="py-2 pr-3">{{ row.value.assessed }}</td>
                  <td class="py-2 pr-3">
                    {{ row.value.human_good.strong_match || 0 }} of {{ goodTotal(row.value) }} ({{
                      percent(row.value.good_fit_recall)
                    }})
                  </td>
                  <td class="py-2 pr-3">
                    {{
                      row.value.strong_match_precision == null
                        ? 'No strong matches'
                        : percent(row.value.strong_match_precision)
                    }}
                  </td>
                  <td class="py-2 pr-3">{{ row.value.good_fits_rejected.length }}</td>
                  <td class="py-2">{{ row.value.failed }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <ul class="space-y-1 text-sm">
            <li>
              <strong>Agreed on your good fits:</strong> of the shortlisted jobs you marked Good
              fit, how many the model rated a strong match.
            </li>
            <li>
              <strong>Strong-match accuracy:</strong> when the model said strong match, how often
              you agreed.
            </li>
            <li>
              <strong>Good fits rejected:</strong> jobs you marked Good fit that the model rated not
              suitable. This is the costliest mistake, because you never see those jobs.
            </li>
          </ul>
          <details
            v-for="row in generationRows.filter((r) => r.value.good_fits_rejected.length)"
            :key="row.name"
            class="rounded-lg border border-slate-300 p-3 dark:border-slate-600"
          >
            <summary class="cursor-pointer py-1 font-semibold">
              Good fits rejected by {{ row.name }}
            </summary>
            <ul class="mt-2 list-disc space-y-1 pl-6">
              <li v-for="id in row.value.good_fits_rejected" :key="id">{{ title(id) }}</li>
            </ul>
          </details>
        </template>
      </div>

      <p v-if="counts.good + counts.notFit < 20" class="text-sm">
        These numbers are rough until you have labeled more jobs: with few labels, one job changes
        the percentage a lot. Not sure answers are not counted.
      </p>
    </template>
  </section>
</template>

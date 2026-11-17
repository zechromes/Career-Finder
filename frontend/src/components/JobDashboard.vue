<!-- Combine results, apply filters and sorting, and paginate the table or card view. -->
<script setup lang="ts">
import DateAdded from './DateAdded.vue'
import { RouterLink } from 'vue-router'
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useResultsViewStore, newResultsView, type ResultsView } from '../stores/resultsView'
import type { Job, ModelOption } from '../types/domain'
import { useJobsStore, jobKey } from '../stores/jobs'
import JobCard from './JobCard.vue'
import JobActions from './JobActions.vue'
import CompanyLogo from './CompanyLogo.vue'
import { Squares2X2Icon, TableCellsIcon } from '@heroicons/vue/24/outline'
import EmptyState from './EmptyState.vue'
import { fitChipClass, fitLabel } from '../utils/fitCategory'
const props = withDefaults(
  defineProps<{
    runId?: string
    jobs?: Job[]
    excludedJobs?: Job[]
    evaluationModelId?: string
    evaluationOptions?: ModelOption[]
    evaluationErrors?: { title?: string; message?: string; provider?: string; category?: string }[]
    excelUrl?: string
    running?: boolean
    retryingEvaluations?: boolean
    busy?: boolean
  }>(),
  {
    jobs: () => [],
    excludedJobs: () => [],
    evaluationOptions: () => [],
    evaluationErrors: () => [],
    evaluationModelId: '',
  },
)
const emit = defineEmits<{ 'retry-evaluation': [] }>()
const failureReasons: Record<string, string> = {
  rate_limit: 'Rate limit',
  quota: 'Quota used up',
  credentials: 'Key rejected',
  model: 'Model unavailable',
  timeout: 'Timed out',
}
// One row per model and reason, so a provider outage reads as one line, not one per job.
const errorGroups = computed(() => {
  const groups = new Map<
    string,
    { model: string; reason: string; message: string; jobs: string[] }
  >()
  for (const error of props.evaluationErrors) {
    const key = `${error.provider}|${error.category}`
    const model =
      props.evaluationOptions.find((option) => option.value === error.provider)?.label ||
      error.provider ||
      'A model'
    const group = groups.get(key) || {
      model,
      reason: failureReasons[error.category || ''] || 'Failed',
      message: error.message || '',
      jobs: [],
    }
    group.jobs.push(error.title || 'Untitled job')
    groups.set(key, group)
  }
  return [...groups.values()].sort((a, b) => b.jobs.length - a.jobs.length)
})
const store = useJobsStore()
// View preference is browser-local; result filtering never mutates server snapshots.
const view = ref<'grid' | 'table'>('grid')
try {
  if (localStorage.getItem('careerResultsView') === 'table') view.value = 'table'
} catch {}
watch(view, (value) => {
  try {
    localStorage.setItem('careerResultsView', value)
  } catch {}
})
const resultsViews = useResultsViewStore()
const localView = reactive(newResultsView())
const selectedView = computed(() => (props.runId ? resultsViews.forRun(props.runId) : localView))
function field<K extends keyof ResultsView>(key: K) {
  return computed({
    get: () => selectedView.value[key],
    set: (value: ResultsView[K]) => {
      selectedView.value[key] = value
    },
  })
}
const search = field('search')
const sort = field('sort')
const location = field('location')
const source = field('source')
const workType = field('workType')
const actionFilter = field('actionFilter')
const requestedPage = field('page')
const pageSize = 12
const resultsHeading = ref<HTMLElement | null>(null)
const activeFilters = computed(
  () =>
    [
      search.value.trim(),
      location.value,
      source.value,
      workType.value,
      actionFilter.value !== 'all',
    ].filter(Boolean).length,
)
// Update pagination and move attention back to the results heading.
async function changePage(value: number) {
  page.value = Math.min(pages.value, Math.max(1, value))
  await nextTick()
  resultsHeading.value?.focus()
}
// Keep all fit categories available in one searchable result pool.
const all = computed(() => [
  ...props.jobs,
  ...props.excludedJobs.map((job) => ({ ...job, fit_category: 'not_suitable' as const })),
])
const locations = computed(() =>
  [...new Set(all.value.map((job) => job.location).filter(Boolean))].sort(),
)
const sources = computed(() =>
  [...new Set(all.value.map((job) => job.source).filter(Boolean))].sort(),
)
// A job still waiting for any model assessment has no final verdict yet.
function waiting(job: Job) {
  const rows = Object.values(job.model_evaluations || {})
  return rows.length ? rows.some((row) => row.status === 'pending') : job.score == null
}
// Order by verdict, then by shortlist position (older saved jobs fall back to their score),
// keeping jobs still being assessed last.
function compareJobs(a: Job, b: Job) {
  if (sort.value === 'match' || sort.value === 'match_asc') {
    if (waiting(a) !== waiting(b)) return waiting(a) ? 1 : -1
    const priority = { strong_match: 0, review: 1, not_suitable: 2 }
    const categoryOrder =
      priority[a.fit_category || 'review'] - priority[b.fit_category || 'review']
    const order =
      categoryOrder ||
      (b.score ?? -1) - (a.score ?? -1) ||
      (a.shortlist_rank ?? Infinity) - (b.shortlist_rank ?? Infinity) ||
      0
    return sort.value === 'match_asc' ? -order : order
  }
  if (sort.value === 'date')
    return (Date.parse(b.posted_at || '') || 0) - (Date.parse(a.posted_at || '') || 0)
  return (a.company || '').localeCompare(b.company || '')
}
// Toggle match direction through the same state used by the sort selector.
function toggleMatchSort() {
  sort.value = sort.value === 'match' ? 'match_asc' : 'match'
}
const matchSortDirection = computed(() =>
  sort.value === 'match' ? 'descending' : sort.value === 'match_asc' ? 'ascending' : 'none',
)
// Filter the complete pool before slicing pages, so off-page matches remain discoverable.
const filtered = computed(() =>
  all.value
    .filter((job) => {
      const flags = store.flags(job)
      const text = [
        job.title,
        job.company,
        job.location,
        job.rationale,
        job.mismatch_reason,
        ...(job.missing_skills || []),
      ]
        .join(' ')
        .toLowerCase()
      return (
        search.value
          .toLowerCase()
          .split(/\s+/)
          .every((term) => text.includes(term)) &&
        (!location.value || job.location === location.value) &&
        (!source.value || job.source === source.value) &&
        (!workType.value || job.work_type === workType.value) &&
        (actionFilter.value === 'dismissed' ? flags.dismissed : !flags.dismissed) &&
        (actionFilter.value !== 'saved' || flags.saved) &&
        (actionFilter.value !== 'applied' || flags.applied)
      )
    })
    .sort(compareJobs),
)
// Derive bounded pagination from the filtered pool and reset it when filters change.
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)))
// Bound the visible page without erasing the saved position while snapshots or
// job-action flags are still loading after navigation.
const page = computed({
  get: () => Math.min(requestedPage.value, pages.value),
  set: (value: number) => {
    requestedPage.value = value
  },
})
// Keep nearby pages visible, with noninteractive ellipses for skipped ranges.
const pageItems = computed(() => {
  const selected = new Set([1, pages.value])
  for (
    let number = Math.max(1, page.value - 1);
    number <= Math.min(pages.value, page.value + 1);
    number++
  )
    selected.add(number)
  const items: (number | string)[] = []
  let previous = 0
  for (const number of [...selected].sort((a, b) => a - b)) {
    if (number - previous === 2) items.push(previous + 1)
    else if (number - previous > 2) items.push(`gap-${number}`)
    items.push(number)
    previous = number
  }
  return items
})
const visible = computed(() =>
  filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize),
)
watch(
  [() => props.runId, search, sort, location, source, workType, actionFilter],
  (value, previous) => {
    if (value[0] === previous[0]) requestedPage.value = 1
  },
)
// Reset result filters while retaining the selected view and sort order.
function clear() {
  search.value = ''
  location.value = ''
  source.value = ''
  workType.value = ''
  actionFilter.value = 'all'
}
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <section class="mt-6" aria-label="Job results">
    <header class="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="text-2xl font-bold">
          {{ running ? 'Results as they arrive' : 'Your job matches' }}
        </h2>
        <p class="mt-1 text-sm text-slate-600 dark:text-slate-300">
          {{ evaluationModelId || jobs[0]?.evaluation_model_id || 'Model' }} evaluated ·
          {{ all.length }} jobs · {{ excludedJobs.length }} not recommended
        </p>
        <p class="mt-1 text-xs text-slate-600 dark:text-slate-300">
          Fit scores are AI assessments, not probabilities. Posting availability is not verified.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <a v-if="excelUrl && !running" :href="excelUrl" class="btn-secondary"
          >Export recommended to Excel</a
        >
      </div>
    </header>
    <section
      v-if="evaluationErrors.length || retryingEvaluations"
      aria-labelledby="assessment-issues-title"
      class="mb-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
    >
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0">
          <h3 id="assessment-issues-title" class="font-semibold">
            {{
              retryingEvaluations
                ? 'Retrying failed assessments…'
                : `${evaluationErrors.length} model ${evaluationErrors.length === 1 ? 'assessment' : 'assessments'} failed`
            }}
          </h3>
          <p role="status" class="mt-0.5 text-sm">
            {{
              retryingEvaluations
                ? 'Successful assessments are kept; results update as retries finish.'
                : 'Verdicts from the other models are kept.'
            }}
          </p>
        </div>
        <button
          class="btn-secondary shrink-0"
          :disabled="running || busy || retryingEvaluations"
          :aria-busy="!!retryingEvaluations"
          @click="emit('retry-evaluation')"
        >
          <span
            v-if="retryingEvaluations"
            aria-hidden="true"
            class="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent motion-reduce:animate-none"
          />
          {{ retryingEvaluations ? 'Retrying evaluations…' : 'Retry failed evaluations' }}
        </button>
      </div>
      <ul v-if="errorGroups.length" class="mt-3 flex flex-wrap gap-2" aria-label="Failures by model">
        <li
          v-for="group in errorGroups"
          :key="group.model + group.reason"
          class="rounded-full bg-white px-3 py-1 text-xs font-semibold text-amber-900 ring-1 ring-amber-200 dark:bg-amber-900 dark:text-amber-100 dark:ring-amber-700"
        >
          {{ group.model }} · {{ group.reason }} · {{ group.jobs.length }}
          {{ group.jobs.length === 1 ? 'job' : 'jobs' }}
        </li>
      </ul>
      <details v-if="errorGroups.length" class="mt-3 text-sm">
        <summary class="cursor-pointer font-medium">Show details and affected jobs</summary>
        <div class="mt-2 max-h-56 space-y-3 overflow-y-auto pr-2">
          <section v-for="group in errorGroups" :key="group.model + group.reason">
            <h4 class="font-semibold">{{ group.model }} · {{ group.reason }}</h4>
            <p class="mt-0.5">{{ group.message }}</p>
            <p class="mt-1 text-amber-800 dark:text-amber-300">{{ group.jobs.join(' · ') }}</p>
          </section>
        </div>
      </details>
    </section>
    <p
      v-if="store.storageError"
      role="status"
      class="mb-4 text-sm text-amber-900 dark:text-amber-300"
    >
      {{ store.storageError }}
    </p>
    <div
      class="mb-5 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
    >
      <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 class="font-semibold">Find the right role</h3>
        <span class="text-xs text-slate-600 dark:text-slate-300">{{
          activeFilters ? `${activeFilters} filters active` : 'Showing all active jobs'
        }}</span>
      </div>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label
          ><span class="field-label">Search jobs</span
          ><input
            v-model="search"
            type="search"
            class="field"
            placeholder="Title, company or skill"
        /></label>
        <label
          ><span class="field-label">Sort by</span
          ><select v-model="sort" class="field">
            <option value="match">Best match</option>
            <option value="match_asc">Lowest match first</option>
            <option value="date">Posting date</option>
            <option value="company">Company</option>
          </select></label
        >
        <label
          ><span class="field-label">Location</span
          ><select v-model="location" class="field">
            <option value="">All locations</option>
            <option v-for="item in locations" :key="item">{{ item }}</option>
          </select></label
        >
        <label
          ><span class="field-label">Source platform</span
          ><select v-model="source" class="field">
            <option value="">All sources</option>
            <option v-for="item in sources" :key="item">{{ item }}</option>
          </select></label
        >
        <label
          ><span class="field-label">Work type</span
          ><select v-model="workType" class="field">
            <option value="">All work types</option>
            <option v-for="item in ['remote', 'hybrid', 'on-site', 'unknown']" :key="item">
              {{ item }}
            </option>
          </select></label
        >
        <label
          ><span class="field-label">Job actions</span
          ><select v-model="actionFilter" class="field">
            <option value="all">All active</option>
            <option value="saved">Saved</option>
            <option value="applied">Applied</option>
            <option value="dismissed">Dismissed</option>
          </select></label
        >
        <button class="btn-secondary self-end" :disabled="!activeFilters" @click="clear">
          Clear filters
        </button>
      </div>
    </div>
    <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
      <div class="flex flex-wrap items-center gap-4">
        <div
          role="group"
          aria-label="Results view"
          class="flex gap-1 rounded-lg border border-slate-200 p-1 dark:border-slate-700"
        >
          <button
            type="button"
            class="btn-secondary gap-2"
            :aria-pressed="view === 'grid'"
            :class="{ 'bg-indigo-50 dark:bg-indigo-950': view === 'grid' }"
            @click="view = 'grid'"
          >
            <Squares2X2Icon class="h-5 w-5" aria-hidden="true" />Grid
          </button>
          <button
            type="button"
            class="btn-secondary gap-2"
            :aria-pressed="view === 'table'"
            :class="{ 'bg-indigo-50 dark:bg-indigo-950': view === 'table' }"
            @click="view = 'table'"
          >
            <TableCellsIcon class="h-5 w-5" aria-hidden="true" />Table
          </button>
        </div>
        <h3
          id="results-heading"
          ref="resultsHeading"
          tabindex="-1"
          class="rounded text-lg font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
        >
          All job results
        </h3>
      </div>
      <p
        role="status"
        aria-live="polite"
        aria-atomic="true"
        class="text-sm text-slate-600 dark:text-slate-300"
      >
        {{
          filtered.length
            ? `Showing ${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, filtered.length)} of ${filtered.length} jobs`
            : 'No matching jobs'
        }}{{ running ? ' · More results arriving' : '' }}
      </p>
    </div>
    <ul
      v-if="visible.length && view === 'grid'"
      aria-label="Matching jobs"
      class="grid list-none items-start gap-6 p-0 lg:grid-cols-2"
    >
      <li v-for="job in visible" :key="jobKey(job)" class="min-w-0">
        <JobCard :job="job" :run-id="runId" />
      </li>
    </ul>
    <div
      v-else-if="visible.length"
      class="overflow-x-auto rounded-2xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"
      tabindex="0"
      role="region"
      aria-label="Job results table; scroll horizontally on smaller screens"
    >
      <table class="w-full min-w-[800px] text-left text-sm">
        <caption class="sr-only">
          Job matches with scores, locations, statuses and actions
        </caption>
        <thead class="bg-slate-50 text-slate-600 dark:bg-slate-950 dark:text-slate-300">
          <tr>
            <th scope="col" class="p-4">Role / company</th>
            <th scope="col" class="p-4" :aria-sort="matchSortDirection">
              <button
                type="button"
                class="inline-flex min-h-11 items-center gap-2 rounded px-2 font-semibold hover:bg-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:hover:bg-slate-800"
                :aria-label="
                  sort === 'match' ? 'Sort by match: lowest first' : 'Sort by match: best first'
                "
                @click="toggleMatchSort"
              >
                Match
                <span aria-hidden="true">{{
                  sort === 'match' ? '↓' : sort === 'match_asc' ? '↑' : '↕'
                }}</span>
              </button>
            </th>
            <th scope="col" class="p-4">Location</th>
            <th scope="col" class="p-4">Source</th>
            <th scope="col" class="p-4">Date added</th>
            <th scope="col" class="p-4">Status</th>
            <th scope="col" class="p-4 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="job in visible" :key="jobKey(job)">
            <tr class="border-t border-slate-200 align-top dark:border-slate-700">
              <th scope="row" class="max-w-sm p-4">
                <div class="flex items-start gap-3">
                  <CompanyLogo :company="job.company" :src="job.company_logo" />
                  <div class="min-w-0">
                    <RouterLink
                      v-if="runId"
                      :to="{ path: `/run/${runId}/job`, query: { job: jobKey(job) } }"
                      class="text-left font-semibold text-indigo-700 underline dark:text-indigo-300"
                      >{{ job.title }}</RouterLink
                    ><span v-else class="font-semibold">{{ job.title }}</span>
                    <p class="mt-1 font-normal text-slate-600 dark:text-slate-300">
                      {{ job.company }}
                    </p>
                  </div>
                </div>
              </th>
              <td class="p-4">
                <span
                  class="inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold"
                  :class="fitChipClass(job.fit_category)"
                  >{{ fitLabel(job.fit_category) }}</span
                >
                <p v-if="job.score != null" class="mt-1.5 text-xs text-slate-600 dark:text-slate-300">
                  {{ job.score }}/100
                </p>
              </td>
              <td class="p-4">
                {{ job.location || 'Not provided' }}
                <p class="mt-1 text-xs text-slate-600 dark:text-slate-300">
                  {{ job.work_type || 'unknown' }}
                </p>
              </td>
              <td class="p-4">{{ job.source || 'Unknown' }}</td>
              <td class="p-4"><DateAdded :value="job.added_at" /></td>
              <td class="p-4">
                <div class="flex flex-wrap gap-1">
                  <span
                    v-if="store.flags(job).applied"
                    class="rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                    >Applied</span
                  >
                  <span
                    v-if="store.flags(job).saved"
                    class="rounded-md bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300"
                    >Saved</span
                  >
                  <span
                    v-if="store.flags(job).dismissed"
                    class="rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-200"
                    >Dismissed</span
                  >
                  <span
                    v-if="
                      !store.flags(job).applied &&
                      !store.flags(job).saved &&
                      !store.flags(job).dismissed
                    "
                    class="text-slate-500 dark:text-slate-400"
                    >No status</span
                  >
                </div>
              </td>
              <td class="p-4">
                <div class="flex justify-end"><JobActions :job="job" /></div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
    <EmptyState
      v-else
      :title="
        running
          ? 'Waiting for matching results'
          : all.length
            ? 'No jobs match these filters'
            : 'No jobs found'
      "
      :message="
        running
          ? 'Evaluated jobs will appear here as requests finish.'
          : all.length
            ? 'Clear the filters. Dismissed jobs are available in Job actions.'
            : 'Try broader locations or target roles, or remove work-type and seniority restrictions.'
      "
      ><button v-if="all.length" class="btn-secondary" @click="clear">Clear filters</button>
      <p v-else-if="!running" class="text-sm">
        Select Review your profile in the timeline to adjust your search.
      </p></EmptyState
    >
    <nav
      v-if="filtered.length"
      aria-label="Results pagination"
      class="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 text-sm dark:border-slate-700 dark:bg-slate-900"
    >
      <p aria-live="polite">{{ filtered.length }} jobs · Page {{ page }} of {{ pages }}</p>
      <div class="flex flex-wrap items-center gap-2">
        <button class="btn-secondary" :disabled="page <= 1" @click="changePage(1)">
          First page
        </button>
        <button class="btn-secondary" :disabled="page <= 1" @click="changePage(page - 1)">
          Previous page
        </button>
        <template v-for="item in pageItems" :key="item">
          <button
            v-if="typeof item === 'number'"
            class="min-w-11"
            :class="item === page ? 'btn-primary' : 'btn-secondary'"
            :aria-label="`Page ${item}`"
            :aria-current="item === page ? 'page' : undefined"
            @click="changePage(item)"
          >
            {{ item }}
          </button>
          <span v-else class="px-1 text-slate-500" aria-hidden="true">…</span>
        </template>
        <button class="btn-secondary" :disabled="page >= pages" @click="changePage(page + 1)">
          Next page
        </button>
        <button class="btn-secondary" :disabled="page >= pages" @click="changePage(pages)">
          Last page
        </button>
      </div>
    </nav>
  </section>
</template>

<!-- Component presentation and interaction styling. -->
<style scoped>
button,
select,
input,
a.btn-secondary {
  min-height: 2.75rem;
}
</style>

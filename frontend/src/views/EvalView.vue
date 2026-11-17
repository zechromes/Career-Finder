<!-- Playground: run one pipeline stage on its own and inspect its output. Nothing is saved on
the server; retrieval relevance marks stay in this browser only. -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../stores/pipeline'
import type { components } from '../types/api'
import ChipInput from '../components/ChipInput.vue'
import LocationInput from '../components/LocationInput.vue'
import UploadCheck from '../components/UploadCheck.vue'
import Tabs from '../components/Tabs.vue'
import { displayTimelineEntry } from '../utils/profileTimeline'
import { jobKey, retrievalMetrics, type RelevanceMarks } from '../utils/retrievalMetrics'
type S = components['schemas']
const route = useRoute()
const router = useRouter()
// One tab per stage, kept in the URL so a stage can be linked directly.
const stages = [
  { value: 'upload', label: '1. Upload' },
  { value: 'ingestion', label: '2. Ingestion' },
  { value: 'retrieval', label: '3. Retrieval' },
]
const stage = computed(() =>
  stages.some((item) => item.value === route.query.stage) ? String(route.query.stage) : 'upload',
)
function setStage(value: string) {
  void router.replace({ query: { stage: value } })
}
const busy = ref(false)
const error = ref('')

const file = ref<File | null>(null)
const uploaded = ref<S['UploadPlayground'] | null>(null)
const uploadViews = [
  { value: 'profile', label: 'Extracted profile' },
  { value: 'text', label: 'Resume text' },
  { value: 'json', label: 'JSON' },
]
const uploadView = ref('profile')
async function runUpload() {
  if (!file.value) return
  busy.value = true
  error.value = ''
  uploaded.value = null
  try {
    const body = new FormData()
    body.append('resume', file.value)
    uploaded.value = await api('/api/playground/upload', { method: 'POST', body })
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}

const search = ref({
  queries: [] as string[],
  locations: [] as string[],
  platforms: ['linkedin'] as S['Preferences']['platforms'],
  posted_days_old: 7 as S['Preferences']['posted_days_old'],
  work_type: 'any' as S['Preferences']['work_type'],
})
const collected = ref<S['IngestionPlayground'] | null>(null)
// Readable names for the collection step that dropped a job.
const stageNames: Record<string, string> = {
  filter: 'Filtered out',
  deduplicate: 'Duplicate',
  description: 'No description',
  budget: 'Collection limit',
}
const summary = computed(() => {
  const result = collected.value
  if (!result) return null
  const total = (rows: { count: number }[]) => rows.reduce((sum, row) => sum + row.count, 0)
  const boards = [
    ...new Set([
      ...Object.keys(result.collected),
      ...result.jobs.map((job) => job.board),
      ...result.counts.map((row) => row.board),
    ]),
  ]
  const reasons = new Map<
    string,
    { stage: string; reason: string; count: number; boards: string[] }
  >()
  for (const row of result.counts) {
    const key = `${row.stage}|${row.reason}`
    const entry = reasons.get(key) || { stage: row.stage, reason: row.reason, count: 0, boards: [] }
    entry.count += row.count
    entry.boards.push(`${row.board} ${row.count}`)
    reasons.set(key, entry)
  }
  return {
    collected: Object.values(result.collected).reduce((sum, count) => sum + count, 0),
    kept: result.jobs.length,
    dropped: total(result.counts),
    boards: boards.map((board) => ({
      board,
      collected: result.collected[board] || 0,
      kept: result.jobs.filter((job) => job.board === board).length,
      dropped: total(result.counts.filter((row) => row.board === board)),
    })),
    reasons: [...reasons.values()].sort((a, b) => b.count - a.count),
  }
})
const droppedByReason = computed(() => {
  const groups = new Map<string, S['DroppedJob'][]>()
  for (const job of collected.value?.dropped || []) {
    const label = `${stageNames[job.stage] || job.stage}: ${job.reason}`
    groups.set(label, [...(groups.get(label) || []), job])
  }
  return [...groups].map(([label, jobs]) => ({ label, jobs }))
})
function postedOn(value: string) {
  const date = new Date(value)
  return value && !Number.isNaN(date.getTime()) ? date.toLocaleDateString() : ''
}
// Relevance marks per job, kept in this browser so another builder's run reuses them.
const MARKS_KEY = 'playground-relevance-marks'
function loadMarks(): RelevanceMarks {
  try {
    return JSON.parse(localStorage.getItem(MARKS_KEY) || '{}')
  } catch {
    return {}
  }
}
const marks = ref<RelevanceMarks>(loadMarks())
// Choosing the current mark again clears it back to unknown.
function setMark(key: string, relevant: boolean) {
  const next = { ...marks.value }
  if (next[key] === relevant) delete next[key]
  else next[key] = relevant
  marks.value = next
  try {
    localStorage.setItem(MARKS_KEY, JSON.stringify(next))
  } catch {
    // Storage can be blocked; marks still work for this visit.
  }
}
const metrics = computed(() =>
  retrieved.value && collected.value
    ? retrievalMetrics(
        retrieved.value.ranked.map(jobKey),
        collected.value.jobs.map(jobKey),
        marks.value,
      )
    : null,
)
function percent(value: number | null) {
  return value === null ? '—' : `${Math.round(value * 100)}%`
}
// Retrieval ranks the Ingestion tab's kept jobs against the Upload tab's profile.
const ranking = ref({
  top_k: -1 as S['RetrievalRequest']['top_k'],
  seniority: 'auto' as S['RetrievalRequest']['seniority'],
  query_builder: 'hyde' as NonNullable<S['RetrievalRequest']['query_builder']>,
})
const retrieved = ref<S['RetrievalPlayground'] | null>(null)
// The builder the shown queries came from, so changing the select does not relabel old results.
const retrievedBuilder = ref<typeof ranking.value.query_builder>('hyde')
const retrievalRoles = computed(() =>
  search.value.queries.length ? search.value.queries : uploaded.value?.profile.preferred_domains || [],
)
async function runRetrieval() {
  if (!uploaded.value || !collected.value) return
  busy.value = true
  error.value = ''
  retrieved.value = null
  const builder = ranking.value.query_builder
  try {
    retrieved.value = await api('/api/playground/retrieval', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile: uploaded.value.profile,
        queries: retrievalRoles.value,
        jobs: collected.value.jobs,
        ...ranking.value,
      }),
    })
    retrievedBuilder.value = builder
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
async function runIngestion() {
  busy.value = true
  error.value = ''
  collected.value = null
  try {
    collected.value = await api('/api/playground/ingestion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(search.value),
    })
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-6">
    <header class="space-y-3">
      <h1 class="text-3xl font-bold">Pipeline playground</h1>
      <p>
        Run one stage of the app on its own and see exactly what it produces. Runs make live calls
        but are never saved and never touch your searches.
      </p>
    </header>
    <Tabs
      :tabs="stages"
      :model-value="stage"
      label="Pipeline stages"
      :disabled="busy"
      @update:model-value="setStage"
    />
    <p
      v-if="error"
      role="alert"
      class="rounded-lg bg-rose-50 p-4 text-rose-900 dark:bg-rose-950 dark:text-rose-200"
    >
      {{ error }}
    </p>

    <section v-if="stage === 'upload'" aria-labelledby="upload-title" class="space-y-4">
      <h2 id="upload-title" class="text-2xl font-semibold">1. Upload: reading a resume</h2>
      <p>
        Reads a PDF into a profile exactly as an upload does (one call to the OpenAI upload model),
        then checks the profile against the resume's own text.
      </p>
      <form class="flex flex-wrap items-end gap-3" @submit.prevent="runUpload">
        <label class="field-label"
          >Resume PDF
          <input
            type="file"
            accept="application/pdf,.pdf"
            class="field"
            @change="file = ($event.target as HTMLInputElement).files?.[0] || null"
        /></label>
        <button class="btn-primary" :disabled="busy || !file" :aria-busy="busy">
          {{ busy ? 'Reading…' : 'Run upload' }}
        </button>
      </form>
      <template v-if="uploaded">
        <Tabs
          :tabs="uploadViews"
          :model-value="uploadView"
          label="Upload output"
          @update:model-value="uploadView = $event"
        />
        <article
          v-if="uploadView === 'profile'"
          aria-labelledby="extracted-title"
          class="panel space-y-6"
        >
          <header class="space-y-2">
            <p class="eyebrow">Extracted profile</p>
            <h3 id="extracted-title" class="text-2xl font-bold">
              {{ uploaded.profile.name || 'No name found' }}
            </h3>
            <p v-if="uploaded.profile.headline" class="text-lg">
              {{ uploaded.profile.headline }}
            </p>
            <div class="flex flex-wrap gap-2 text-sm">
              <span class="chip">Career level: {{ uploaded.profile.career_level }}</span>
              <span class="chip"
                >{{ uploaded.profile.years_of_experience ?? 'Unknown' }} years of paid
                experience</span
              >
            </div>
            <p v-if="uploaded.profile.profile" class="leading-7">{{ uploaded.profile.profile }}</p>
          </header>

          <section class="space-y-2">
            <h4 class="font-semibold">Suggested target roles</h4>
            <ul class="flex flex-wrap gap-2">
              <li v-for="role in uploaded.profile.preferred_domains" :key="role" class="chip">
                {{ role }}
              </li>
            </ul>
            <p
              v-if="uploaded.profile.target_roles_reason"
              class="text-sm text-slate-600 dark:text-slate-300"
            >
              {{ uploaded.profile.target_roles_reason }}
            </p>
          </section>

          <section class="grid gap-4 sm:grid-cols-2">
            <div
              v-for="(skills, label) in {
                'Technical skills': uploaded.profile.tech_skills,
                'Soft skills': uploaded.profile.soft_skills,
              }"
              :key="label"
              class="space-y-2"
            >
              <h4 class="font-semibold">{{ label }}</h4>
              <ul v-if="skills?.length" class="flex flex-wrap gap-2">
                <li v-for="skill in skills" :key="skill" class="chip">{{ skill }}</li>
              </ul>
              <p v-else class="text-sm text-slate-600 dark:text-slate-300">None found</p>
            </div>
          </section>

          <section
            v-for="group in [
              { heading: 'Work history', entries: uploaded.profile.work_history },
              { heading: 'Education', entries: uploaded.profile.education },
              ...(uploaded.profile.sections || []),
            ]"
            :key="group.heading"
            class="space-y-3"
          >
            <h4 class="border-b border-slate-200 pb-1 font-semibold dark:border-slate-700">
              {{ group.heading }}
            </h4>
            <p v-if="!group.entries?.length" class="text-sm text-slate-600 dark:text-slate-300">
              Nothing extracted
            </p>
            <div
              v-for="(entry, index) in group.entries"
              :key="index"
              class="rounded-xl bg-slate-50 p-4 dark:bg-slate-950"
            >
              <p class="font-semibold">{{ displayTimelineEntry(entry).title }}</p>
              <p class="text-sm text-slate-600 dark:text-slate-300">
                {{
                  [displayTimelineEntry(entry).company, displayTimelineEntry(entry).date]
                    .filter(Boolean)
                    .join(' · ')
                }}
              </p>
              <p
                v-if="displayTimelineEntry(entry).detail"
                class="mt-2 whitespace-pre-line text-sm leading-6"
              >
                {{ displayTimelineEntry(entry).detail }}
              </p>
            </div>
          </section>

          <section class="space-y-2 text-sm">
            <h4 class="font-semibold">Headings found in the resume</h4>
            <ul class="flex flex-wrap gap-2">
              <li v-for="heading in uploaded.profile.section_headings" :key="heading" class="chip">
                {{ heading }}
              </li>
            </ul>
          </section>
        </article>
        <pre v-else-if="uploadView === 'text'" class="panel whitespace-pre-wrap text-sm">{{
          uploaded.profile.source_text
        }}</pre>
        <pre v-else class="panel whitespace-pre-wrap text-sm">{{
          JSON.stringify(uploaded.profile, null, 2)
        }}</pre>
        <UploadCheck :report="uploaded.check" />
      </template>
    </section>

    <section v-else-if="stage === 'ingestion'" aria-labelledby="ingestion-title" class="space-y-4">
      <h2 id="ingestion-title" class="text-2xl font-semibold">2. Ingestion: collecting jobs</h2>
      <p>
        Searches the selected boards live, bypassing the collection cache, and shows which jobs were
        kept or dropped and why. Can take a few minutes; Google Jobs uses SerpApi credits.
      </p>
      <form class="grid gap-4 sm:grid-cols-2" @submit.prevent="runIngestion">
        <ChipInput v-model="search.queries" label="Target roles" placeholder="Add a role" />
        <LocationInput v-model="search.locations" />
        <fieldset>
          <legend class="field-label">Job boards</legend>
          <label
            v-for="board in ['linkedin', 'indeed', 'seek', 'google', 'adzuna']"
            :key="board"
            class="mr-4 inline-flex gap-2 text-sm capitalize"
            ><input v-model="search.platforms" type="checkbox" :value="board" />{{ board }}</label
          >
        </fieldset>
        <label class="field-label"
          >Posted within
          <select v-model="search.posted_days_old" class="field">
            <option :value="1">Today</option>
            <option :value="7">Last week</option>
            <option :value="30">Last month</option>
            <option :value="0">Any time</option>
          </select></label
        >
        <label class="field-label"
          >Work arrangement
          <select v-model="search.work_type" class="field">
            <option value="any">Any arrangement</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="on-site">On-site</option>
          </select></label
        >
        <div class="flex items-end">
          <button
            class="btn-primary"
            :disabled="busy || !search.queries.length || !search.platforms?.length"
            :aria-busy="busy"
          >
            {{ busy ? 'Collecting…' : 'Run ingestion' }}
          </button>
        </div>
      </form>
      <template v-if="collected && summary">
        <p role="status" class="text-sm text-slate-600 dark:text-slate-300">
          {{ collected.status || 'Collection finished.' }}
        </p>
        <ul
          v-if="collected.messages.length"
          class="space-y-1 rounded-xl bg-amber-50 p-4 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-300"
        >
          <li v-for="(message, index) in collected.messages" :key="index">{{ message }}</li>
        </ul>

        <dl class="grid gap-3 sm:grid-cols-3">
          <div
            v-for="tile in [
              { label: 'Collected from the boards', value: summary.collected },
              { label: 'Kept for matching', value: summary.kept },
              { label: 'Dropped', value: summary.dropped },
            ]"
            :key="tile.label"
            class="panel"
          >
            <dt class="field-label">{{ tile.label }}</dt>
            <dd class="text-4xl font-bold">{{ tile.value }}</dd>
          </div>
        </dl>

        <div class="panel overflow-x-auto">
          <table class="w-full text-left text-sm">
            <caption class="mb-2 text-left text-lg font-semibold">
              By board
            </caption>
            <thead class="text-slate-600 dark:text-slate-300">
              <tr>
                <th scope="col" class="py-2">Board</th>
                <th scope="col" class="py-2 text-right">Collected</th>
                <th scope="col" class="py-2 text-right">Kept</th>
                <th scope="col" class="py-2 text-right">Dropped</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in summary.boards"
                :key="row.board"
                class="border-t border-slate-200 dark:border-slate-700"
              >
                <th scope="row" class="py-2 font-semibold capitalize">{{ row.board }}</th>
                <td class="py-2 text-right">{{ row.collected }}</td>
                <td class="py-2 text-right">{{ row.kept }}</td>
                <td class="py-2 text-right">{{ row.dropped }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="summary.reasons.length" class="panel overflow-x-auto">
          <table class="w-full text-left text-sm">
            <caption class="mb-2 text-left text-lg font-semibold">
              Why jobs were dropped
            </caption>
            <thead class="text-slate-600 dark:text-slate-300">
              <tr>
                <th scope="col" class="py-2">Step</th>
                <th scope="col" class="py-2">Reason</th>
                <th scope="col" class="py-2">Boards</th>
                <th scope="col" class="py-2 text-right">Jobs</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in summary.reasons"
                :key="row.stage + row.reason"
                class="border-t border-slate-200 dark:border-slate-700"
              >
                <td class="py-2">{{ stageNames[row.stage] || row.stage }}</td>
                <td class="py-2">{{ row.reason }}</td>
                <td class="py-2 text-slate-600 dark:text-slate-300">{{ row.boards.join(', ') }}</td>
                <td class="py-2 text-right font-semibold">{{ row.count }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <section aria-labelledby="kept-title" class="space-y-3">
          <h3 id="kept-title" class="text-lg font-semibold">
            Kept jobs ({{ collected.jobs.length }})
          </h3>
          <p v-if="!collected.jobs.length" class="text-sm text-slate-600 dark:text-slate-300">
            No jobs were kept.
          </p>
          <ul class="grid gap-3 md:grid-cols-2">
            <li
              v-for="(job, index) in collected.jobs"
              :key="index"
              class="rounded-xl border border-slate-200 p-4 dark:border-slate-700"
            >
              <a
                :href="job.url"
                target="_blank"
                rel="noopener"
                class="font-semibold text-indigo-700 underline dark:text-indigo-300"
                >{{ job.title }}</a
              >
              <p class="text-sm">{{ job.company }} · {{ job.location || 'No location' }}</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <span class="chip capitalize">{{ job.board }}</span>
                <span v-if="postedOn(job.posted_at)" class="chip"
                  >Posted {{ postedOn(job.posted_at) }}</span
                >
                <span class="chip">{{ job.description_chars.toLocaleString() }} characters</span>
              </div>
            </li>
          </ul>
        </section>

        <section v-if="collected.dropped.length" aria-labelledby="dropped-title" class="space-y-3">
          <h3 id="dropped-title" class="text-lg font-semibold">
            Dropped jobs ({{ collected.dropped.length }} shown)
          </h3>
          <p class="text-sm text-slate-600 dark:text-slate-300">
            A sample capped per reason, so it can be shorter than the Dropped total.
          </p>
          <details
            v-for="group in droppedByReason"
            :key="group.label"
            class="rounded-xl border border-slate-200 p-4 dark:border-slate-700"
          >
            <summary class="cursor-pointer font-semibold">
              {{ group.label }} · {{ group.jobs.length }}
            </summary>
            <ul class="mt-3 grid gap-3 md:grid-cols-2">
              <li
                v-for="(job, index) in group.jobs"
                :key="index"
                class="rounded-xl bg-slate-50 p-4 dark:bg-slate-950"
              >
                <a
                  v-if="job.url"
                  :href="job.url"
                  target="_blank"
                  rel="noopener"
                  class="font-semibold text-indigo-700 underline dark:text-indigo-300"
                  >{{ job.title || 'Untitled job' }}</a
                >
                <p v-else class="font-semibold">{{ job.title || 'Untitled job' }}</p>
                <p class="text-sm">
                  {{ job.company || 'Unknown company' }} · {{ job.location || 'No location' }}
                </p>
                <span class="chip mt-2 capitalize">{{ job.board }}</span>
                <span v-if="job.posted_at" class="chip mt-2"
                  >Posted {{ postedOn(job.posted_at) || job.posted_at }}</span
                >
              </li>
            </ul>
          </details>
        </section>
      </template>
    </section>

    <section v-else aria-labelledby="retrieval-title" class="space-y-4">
      <h2 id="retrieval-title" class="text-2xl font-semibold">3. Retrieval: ranking the jobs</h2>
      <p>
        Ranks the jobs kept in the Ingestion tab against the profile from the Upload tab, exactly as
        a search does: each query is matched by meaning and by keywords, then the lists are merged.
        Embeds jobs with OpenAI unless they are already in the embedding cache.
      </p>
      <p v-if="!uploaded || !collected?.jobs.length" role="status" class="panel">
        Run {{ !uploaded ? 'Upload' : '' }}{{ !uploaded && !collected?.jobs.length ? ' and ' : ''
        }}{{ !collected?.jobs.length ? 'Ingestion (with at least one kept job)' : '' }} first; this
        stage uses their results.
      </p>
      <form v-else class="grid gap-4 sm:grid-cols-3" @submit.prevent="runRetrieval">
        <p class="sm:col-span-3 text-sm">
          {{ collected.jobs.length }} jobs from Ingestion · target roles:
          {{ retrievalRoles.join(', ') || 'none (profile summary only)' }}
        </p>
        <label class="field-label"
          >Shortlist size
          <select v-model="ranking.top_k" class="field">
            <option :value="-1">Automatic (all up to 200, else top 100)</option>
            <option :value="15">Top 15</option>
            <option :value="50">Top 50</option>
            <option :value="100">Top 100</option>
            <option :value="0">All jobs</option>
          </select></label
        >
        <label class="field-label"
          >Seniority
          <select v-model="ranking.seniority" class="field">
            <option value="auto">Prioritize my experience (automatic)</option>
            <option value="any">All levels</option>
          </select></label
        >
        <label class="field-label"
          >Queries
          <select v-model="ranking.query_builder" class="field">
            <option value="evidence">Skills and experience</option>
            <option value="skills">Skills only, weighted by experience</option>
            <option value="legacy">Previous builder</option>
            <option value="hyde">Generated job ads (HyDE, default)</option>
          </select></label
        >
        <div class="flex items-end">
          <button class="btn-primary" :disabled="busy" :aria-busy="busy">
            {{ busy ? 'Ranking…' : 'Run retrieval' }}
          </button>
        </div>
      </form>
      <template v-if="retrieved">
        <section aria-labelledby="queries-title" class="panel space-y-2">
          <h3 id="queries-title" class="text-lg font-semibold">Queries built from the profile</h3>
          <p class="text-sm text-slate-600 dark:text-slate-300">
            <template v-if="retrievedBuilder === 'evidence'">
              Weights sum to 1: roles share 20%, technical skills 40% and experience 40%, split
              among their queries by resume evidence. A skill group weighs its average skill, so
              long lists do not win. Soft skills are not searched.
            </template>
            <template v-else-if="retrievedBuilder === 'skills'">
              Weights sum to 1: roles share a third and technical skills two thirds, split by
              resume evidence. A skill group weighs its average skill, so long lists do not win.
              Experience is not searched; it only weights the skills it shows. Soft skills are not
              searched.
            </template>
            <template v-else-if="retrievedBuilder === 'hyde'">
              Like Skills and experience, but the roles' 20% goes to up to three job ads a model writes from
              your strongest skills and experience (live model call, cached). Ads are searched by
              meaning only, not keywords. If writing fails, the role titles are used instead.
            </template>
            <template v-else>Previous builder: roles, all skills, recent work and other sections.</template>
          </p>
          <table class="w-full text-left text-sm">
            <thead>
              <tr><th class="py-2">Query</th><th class="py-2 text-right">Weight</th></tr>
            </thead>
            <tbody>
              <tr
                v-for="query in retrieved.queries"
                :key="query.text"
                class="border-t border-slate-200 dark:border-slate-700"
              >
                <td class="py-2 pr-4 whitespace-pre-line">{{ query.text }}</td>
                <td class="py-2 text-right">{{ query.weight }}</td>
              </tr>
            </tbody>
          </table>
        </section>
        <section v-if="metrics" aria-labelledby="metrics-title" class="panel space-y-3">
          <h3 id="metrics-title" class="text-lg font-semibold">Retrieval metrics</h3>
          <p class="text-sm text-slate-600 dark:text-slate-300">
            From your marks below: {{ metrics.markedInShortlist }} of {{ retrieved.ranked.length }}
            shortlisted jobs marked, {{ metrics.relevantInPool }} relevant of
            {{ metrics.markedInPool }} marked in the pool of {{ collected?.jobs.length }}. Unmarked
            jobs count as unknown, not as misses. Recall only knows about relevant jobs you have
            seen, so run once with All jobs and mark the whole pool for a complete figure.
          </p>
          <dl class="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div v-for="cut in metrics.recall" :key="cut.k">
              <dt class="text-sm text-slate-600 dark:text-slate-300">Recall@{{ cut.k }}</dt>
              <dd class="text-xl font-semibold tabular-nums">{{ percent(cut.value) }}</dd>
            </div>
            <div>
              <dt class="text-sm text-slate-600 dark:text-slate-300">Context precision</dt>
              <dd class="text-xl font-semibold tabular-nums">
                {{ percent(metrics.contextPrecision) }}
              </dd>
            </div>
            <div>
              <dt class="text-sm text-slate-600 dark:text-slate-300">Context relevance</dt>
              <dd class="text-xl font-semibold tabular-nums">
                {{ percent(metrics.contextRelevance) }}
              </dd>
            </div>
          </dl>
          <p class="text-sm text-slate-600 dark:text-slate-300">
            Recall@k: relevant jobs in the top k ÷ relevant jobs marked in the pool. Context
            precision: whether relevant jobs sit near the top (mean precision at each relevant
            rank). Context relevance: share of marked shortlisted jobs that are relevant.
          </p>
        </section>
        <section aria-labelledby="ranked-title" class="space-y-3">
          <h3 id="ranked-title" class="text-lg font-semibold">
            Shortlist: {{ retrieved.ranked.length }} of {{ retrieved.total_jobs }} jobs
          </h3>
          <ol class="space-y-2">
            <li
              v-for="job in retrieved.ranked"
              :key="job.rank"
              class="flex gap-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-950"
            >
              <span class="w-8 shrink-0 text-right font-semibold">{{ job.rank }}</span>
              <div>
                <a
                  v-if="job.url"
                  :href="job.url"
                  target="_blank"
                  rel="noopener"
                  class="font-semibold text-indigo-700 underline dark:text-indigo-300"
                  >{{ job.title }}</a
                >
                <p class="text-sm">{{ job.company }} · {{ job.location }}</p>
                <span class="chip mt-2 capitalize">{{ job.board }}</span>
                <span v-if="job.above_level" class="chip mt-2"
                  >Above your level · moved down</span
                >
                <div class="mt-3 flex flex-wrap gap-2" role="group" :aria-label="`Mark ${job.title}`">
                  <button
                    type="button"
                    class="btn-secondary"
                    :class="{ 'ring-2 ring-emerald-600': marks[jobKey(job)] === true }"
                    :aria-pressed="marks[jobKey(job)] === true"
                    @click="setMark(jobKey(job), true)"
                  >
                    Relevant
                  </button>
                  <button
                    type="button"
                    class="btn-secondary"
                    :class="{ 'ring-2 ring-rose-600': marks[jobKey(job)] === false }"
                    :aria-pressed="marks[jobKey(job)] === false"
                    @click="setMark(jobKey(job), false)"
                  >
                    Not relevant
                  </button>
                </div>
              </div>
            </li>
          </ol>
        </section>
      </template>
    </section>
  </div>
</template>

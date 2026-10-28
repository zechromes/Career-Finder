<!-- Manage independent saved profiles and reopen their search workspaces. -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api, usePipelineStore } from '../stores/pipeline'
import { useProfileStore } from '../stores/profile'
import type { Profile, Preferences } from '../types/domain'
import {
  Squares2X2Icon,
  TableCellsIcon,
  PlusIcon,
  ArrowDownTrayIcon,
  ArrowRightIcon,
  PencilSquareIcon,
  TrashIcon,
} from '@heroicons/vue/24/outline'
import ProfileReview from '../components/ProfileReview.vue'
type Saved = {
  id: string
  name: string
  profile: Profile
  preferences: Preferences | null
  updated_at: number
  resume_available?: boolean
}
const router = useRouter()
const pipeline = usePipelineStore()
const draft = useProfileStore()
const profiles = ref<Saved[]>([])
const editing = ref<Saved | null>(null)
const name = ref('')
const pendingDelete = ref('')
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const view = ref<'grid' | 'table'>('grid')
try {
  if (localStorage.getItem('career-resume-view') === 'table') view.value = 'table'
} catch {
  /* Storage may be unavailable in private browsing. */
}
function setView(value: 'grid' | 'table') {
  view.value = value
  pendingDelete.value = ''
  try {
    localStorage.setItem('career-resume-view', value)
  } catch {
    /* Keep the view usable. */
  }
}
// Refresh the saved-profile list from the backend.
async function load() {
  profiles.value = await api<Saved[]>('/api/profiles')
}
onMounted(async () => {
  pipeline.stop()
  try {
    await load()
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    loading.value = false
  }
})
// Populate the editing draft from the selected saved profile.
function edit(profile: Saved) {
  editing.value = profile
  name.value = profile.name
  draft.load({ profile: profile.profile, preferences: profile.preferences || undefined })
}
// Share busy and error handling across saved-profile mutations.
async function perform(action: () => Promise<void>) {
  busy.value = true
  error.value = ''
  try {
    await action()
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
// Persist profile edits and refresh the saved-profile list.
function save() {
  return perform(async () => {
    await api(`/api/profiles/${editing.value!.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.value,
        profile: draft.draft,
        preferences: draft.preferences.queries?.length ? draft.preferences : null,
      }),
    })
    await load()
    editing.value = null
  })
}
// Delete the confirmed saved profile, then clear the pending selection.
function remove(id: string) {
  return perform(async () => {
    await api(`/api/profiles/${id}`, { method: 'DELETE' })
    await load()
    pendingDelete.value = ''
  })
}
// Reopen saved results unless a fresh workspace is explicitly requested.
function continueProfile(id: string, fresh = false) {
  return perform(async () => {
    const result = await api<{ runId: string }>(
      `/api/profiles/${id}/searches${fresh ? '?fresh=true' : ''}`,
      { method: 'POST' },
    )
    await router.push(`/run/${result.runId}`)
  })
}
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <div class="mb-6 flex flex-wrap items-center justify-between gap-4">
    <h1 class="text-3xl font-bold">Saved resumes</h1>
    <RouterLink to="/" class="btn-primary">Upload new resume</RouterLink>
  </div>
  <p class="mb-6 text-slate-600 dark:text-slate-300">
    Continue your latest search with its saved results, or start a new search using this resume.
    Your original PDF, profile and preferences stay on this server until deleted.
  </p>
  <p v-if="error" role="alert" class="panel mb-4 text-rose-700 dark:text-rose-300">{{ error }}</p>
  <p v-if="loading" role="status">Loading profiles…</p>
  <template v-else-if="editing">
    <div class="panel mb-5">
      <label
        ><span class="field-label">Profile name</span
        ><input v-model="name" maxlength="100" class="field" :disabled="busy" /></label
      ><button class="btn-secondary mt-3" :disabled="busy" @click="editing = null">
        Cancel editing
      </button>
    </div>
    <ProfileReview :models="[]" :disabled="busy || !name.trim()" save-only @confirm="save" />
  </template>
  <template v-else>
    <div class="mb-4 flex items-center justify-between gap-4">
      <p class="text-sm text-slate-500 dark:text-slate-400">
        {{ profiles.length }} saved {{ profiles.length === 1 ? 'resume' : 'resumes' }}
      </p>
      <div
        role="group"
        aria-label="Saved resumes view"
        class="inline-flex gap-1 rounded-xl border border-slate-200 bg-slate-100 p-1 dark:border-slate-700 dark:bg-slate-800"
      >
        <button
          v-for="option in ['grid', 'table'] as const"
          :key="option"
          type="button"
          class="view-switch"
          :class="view === option ? 'view-switch-active' : ''"
          :aria-label="option"
          :title="option === 'grid' ? 'Grid view' : 'Table view'"
          :aria-pressed="view === option"
          @click="setView(option)"
        >
          <component
            :is="option === 'grid' ? Squares2X2Icon : TableCellsIcon"
            class="h-5 w-5"
            aria-hidden="true"
          />
        </button>
      </div>
    </div>
    <div
      v-if="view === 'table' && profiles.length"
      class="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700"
      role="region"
      aria-label="Saved resumes table"
      tabindex="0"
    >
      <table class="w-full text-left text-sm">
        <caption class="sr-only">
          Saved resumes and available actions
        </caption>
        <thead class="bg-slate-100 dark:bg-slate-800">
          <tr>
            <th scope="col" class="p-3">Name</th>
            <th scope="col" class="p-3">Target roles</th>
            <th scope="col" class="p-3">Location</th>
            <th scope="col" class="p-3">Resume</th>
            <th scope="col" class="p-3">Updated</th>
            <th scope="col" class="p-3 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="profile in profiles" :key="profile.id">
            <tr
              class="border-t border-slate-200 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800/50"
            >
              <th scope="row" class="p-3">{{ profile.profile.name || 'Name not provided' }}</th>
              <td class="p-3">
                {{ profile.preferences?.queries?.join(' · ') || 'Not specified' }}
              </td>
              <td class="p-3">{{ profile.preferences?.locations?.join(' · ') || 'Worldwide' }}</td>
              <td class="p-3">{{ profile.resume_available ? 'PDF saved' : 'Profile only' }}</td>
              <td class="whitespace-nowrap p-3">
                {{ new Date(profile.updated_at * 1000).toLocaleDateString('en-AU') }}
              </td>
              <td class="p-3">
                <div
                  class="flex items-center justify-end gap-1.5"
                  role="group"
                  :aria-label="`Actions for ${profile.profile.name || profile.name}`"
                >
                  <button
                    class="table-continue"
                    :disabled="busy"
                    @click="continueProfile(profile.id)"
                  >
                    Continue<ArrowRightIcon class="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button
                    class="table-action"
                    aria-label="Edit profile"
                    title="Edit profile"
                    :disabled="busy"
                    @click="edit(profile)"
                  >
                    <PencilSquareIcon class="h-4 w-4" aria-hidden="true" />
                  </button>
                  <a
                    v-if="profile.resume_available"
                    class="table-action"
                    aria-label="Download PDF"
                    title="Download PDF"
                    :href="`/api/profiles/${profile.id}/resume`"
                  >
                    <ArrowDownTrayIcon class="h-4 w-4" aria-hidden="true" />
                  </a>
                  <button
                    class="table-action"
                    aria-label="Start a new search"
                    title="Start a new search"
                    :disabled="busy"
                    @click="continueProfile(profile.id, true)"
                  >
                    <PlusIcon class="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button
                    class="table-action table-action-delete"
                    aria-label="Delete saved resume"
                    title="Delete saved resume"
                    :disabled="busy"
                    @click="pendingDelete = profile.id"
                  >
                    <TrashIcon class="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="pendingDelete === profile.id">
              <td colspan="6" class="p-3">
                <div role="alert">
                  <p>
                    Delete “{{ profile.name }}”? Existing searches and uploaded resumes will remain.
                  </p>
                  <button class="btn-secondary mt-2" :disabled="busy" @click="remove(profile.id)">
                    Confirm delete
                  </button>
                  <button class="btn-secondary ml-2" :disabled="busy" @click="pendingDelete = ''">
                    Keep profile
                  </button>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
    <div v-else class="grid items-start gap-4 xl:grid-cols-2">
      <p v-if="!loading && !profiles.length && !error" class="panel">
        No saved resumes yet. Upload a resume, then choose Save resume during review.
      </p>
      <article
        v-for="profile in profiles"
        :key="profile.id"
        class="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900"
        :aria-labelledby="`resume-${profile.id}`"
      >
        <div
          class="border-b border-slate-100 bg-slate-50/70 p-4 sm:p-5 dark:border-slate-800 dark:bg-slate-950/40"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <h2
              :id="`resume-${profile.id}`"
              class="min-w-0 flex-1 break-words text-xl font-bold leading-7 text-slate-950 dark:text-white"
            >
              {{ profile.profile.name || 'Name not provided' }}
            </h2>
            <p class="shrink-0 text-xs leading-7 text-slate-500 dark:text-slate-400">
              Last updated
              {{
                new Date(profile.updated_at * 1000).toLocaleDateString('en-AU', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                })
              }}
            </p>
          </div>
          <span
            class="mt-3 inline-block rounded-full px-2.5 py-1 text-xs font-medium"
            :class="
              profile.resume_available
                ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200'
                : 'bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200'
            "
            >{{ profile.resume_available ? 'PDF saved' : 'Profile only' }}</span
          >
        </div>
        <div class="space-y-4 p-4 sm:p-5">
          <p class="line-clamp-2 break-words text-sm leading-6 text-slate-600 dark:text-slate-300">
            {{ profile.profile.profile || 'Add a summary by editing this profile.' }}
          </p>
          <dl class="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt class="text-xs font-medium text-slate-500 dark:text-slate-400">Experience</dt>
              <dd class="mt-1 font-medium">
                {{
                  profile.profile.years_of_experience == null
                    ? 'Not specified'
                    : `${profile.profile.years_of_experience} years`
                }}
              </dd>
            </div>
            <div>
              <dt class="text-xs font-medium text-slate-500 dark:text-slate-400">
                Search location
              </dt>
              <dd class="mt-1 break-words font-medium">
                {{ profile.preferences?.locations?.filter(Boolean).join(' · ') || 'Worldwide' }}
              </dd>
            </div>
            <div class="col-span-2">
              <dt class="text-xs font-medium text-slate-500 dark:text-slate-400">Target roles</dt>
              <dd class="mt-1 break-words font-medium leading-6">
                {{ profile.preferences?.queries?.join(' · ') || 'Choose roles when you continue' }}
              </dd>
            </div>
          </dl>
          <div v-if="profile.profile.tech_skills?.length">
            <p class="mb-2 text-xs font-medium text-slate-500 dark:text-slate-400">Key skills</p>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="(skill, index) in profile.profile.tech_skills.slice(0, 5)"
                :key="index"
                class="max-w-full break-words rounded-lg bg-slate-100 px-2.5 py-1 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-200"
                >{{ skill }}</span
              ><span
                v-if="profile.profile.tech_skills.length > 5"
                class="py-1 text-xs text-slate-500 dark:text-slate-400"
                >+{{ profile.profile.tech_skills.length - 5 }} more</span
              >
            </div>
          </div>
          <p
            v-if="!profile.resume_available"
            class="rounded-lg bg-amber-50 p-3 text-sm leading-6 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
          >
            The original PDF is not stored with this older profile. Upload it to save a complete
            resume.
          </p>
        </div>
        <div
          class="flex flex-wrap items-center gap-3 border-t border-slate-100 bg-slate-50/50 px-4 py-3 sm:px-5 dark:border-slate-800 dark:bg-slate-950/30"
        >
          <button
            class="btn-primary h-11 min-w-40 flex-1 whitespace-nowrap !px-4 !py-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
            :disabled="busy"
            @click="continueProfile(profile.id)"
          >
            <span>Continue</span><ArrowRightIcon class="h-4 w-4 shrink-0" aria-hidden="true" />
          </button>
          <div
            role="group"
            aria-label="Resume actions"
            class="ml-auto flex shrink-0 items-center gap-2"
          >
            <button
              class="resume-action"
              aria-label="Edit profile"
              title="Edit profile"
              :disabled="busy"
              @click="edit(profile)"
            >
              <PencilSquareIcon class="h-5 w-5" aria-hidden="true" />
            </button>
            <a
              v-if="profile.resume_available"
              :href="`/api/profiles/${profile.id}/resume`"
              class="resume-action"
              aria-label="Download PDF"
              title="Download PDF"
              ><ArrowDownTrayIcon class="h-5 w-5" aria-hidden="true"
            /></a>
            <button
              class="resume-action resume-action-delete"
              title="Delete saved resume"
              aria-label="Delete saved resume"
              :disabled="busy"
              @click="pendingDelete = profile.id"
            >
              <TrashIcon class="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
        </div>
        <div class="px-4 pb-3 sm:px-5">
          <button
            type="button"
            class="text-sm font-medium text-indigo-700 underline underline-offset-4 disabled:opacity-50 dark:text-indigo-300"
            :disabled="busy"
            @click="continueProfile(profile.id, true)"
          >
            Start a new search
          </button>
        </div>
        <div
          v-if="pendingDelete === profile.id"
          role="alert"
          class="border-t border-rose-200 bg-rose-50 p-5 text-sm leading-6 text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200"
        >
          <p>Delete “{{ profile.name }}”? Existing searches and uploaded resumes will remain.</p>
          <div class="mt-3 flex gap-3">
            <button class="btn-secondary" :disabled="busy" @click="remove(profile.id)">
              Confirm delete</button
            ><button class="btn-secondary" :disabled="busy" @click="pendingDelete = ''">
              Keep profile
            </button>
          </div>
        </div>
      </article>
    </div>
  </template>
</template>

<!-- Component presentation and interaction styling. -->
<style scoped>
.view-switch {
  @apply inline-flex h-10 w-10 items-center justify-center rounded-lg text-slate-500 transition-colors hover:text-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:text-slate-400 dark:hover:text-indigo-300;
}
.view-switch-active {
  @apply bg-white text-indigo-700 shadow-sm dark:bg-slate-700 dark:text-indigo-200;
}
.table-action {
  @apply inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-indigo-50 hover:text-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 disabled:opacity-50 dark:text-slate-400 dark:hover:bg-indigo-950 dark:hover:text-indigo-200;
}
.table-action-delete {
  @apply hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-950 dark:hover:text-rose-200;
}
.table-continue {
  @apply mr-1 inline-flex h-10 shrink-0 items-center gap-2 whitespace-nowrap rounded-lg bg-indigo-50 px-3 text-sm font-semibold text-indigo-700 transition-colors hover:bg-indigo-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 disabled:opacity-50 dark:bg-indigo-950 dark:text-indigo-200 dark:hover:bg-indigo-900;
}

.resume-action {
  @apply inline-flex h-11 w-11 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 transition-colors hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-indigo-500 dark:hover:bg-indigo-950 dark:hover:text-indigo-200;
}
.resume-action-delete {
  @apply hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700 focus-visible:outline-rose-500 dark:hover:border-rose-700 dark:hover:bg-rose-950 dark:hover:text-rose-200;
}
</style>

<!-- Coordinate profile review, append searches, live progress, and retained results. -->
<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePipelineStore } from '../stores/pipeline'
import { useProfileStore } from '../stores/profile'
import { useJobsStore } from '../stores/jobs'
import ApplicationStepper from '../components/ApplicationStepper.vue'
import type { Preferences } from '../types/domain'
import SaveProfile from '../components/SaveProfile.vue'
import ProfileReview from '../components/ProfileReview.vue'
import JobDashboard from '../components/JobDashboard.vue'
import ErrorState from '../components/ErrorState.vue'
import EmptyState from '../components/EmptyState.vue'
const route = useRoute()
const router = useRouter()
const store = usePipelineStore()
const profile = useProfileStore()
const jobs = useJobsStore()
// Local navigation state must not itself trigger collection or evaluation.
const editing = ref(false)
const confirmAction = ref(false)
const findingMore = ref(false)
const hasResults = computed(
  () =>
    !!(
      (store.run?.recommendations?.length || 0) + (store.run?.excluded_recommendations?.length || 0)
    ),
)
const canFindMore = computed(
  () =>
    !!store.run?.profile &&
    !store.running &&
    ['complete', 'error', 'cancelled'].includes(store.run.status),
)
const showingResults = computed(() => store.run?.status === 'complete' && !editing.value)
const navigableSteps = computed(() => {
  if (store.running || store.busy || !store.run?.profile) return []
  return store.run.status === 'complete' ? [1, 3] : [1]
})
// Allow only available stages and use append mode when results already exist.
function navigate(step: number) {
  if (!navigableSteps.value.includes(step)) return
  editing.value = step === 1
  findingMore.value = step === 1 && hasResults.value
}
let initialized = ''
// Route changes attach to existing work and restore the matching profile draft.
watch(
  () => route.params.runId,
  async (id) => {
    initialized = ''
    editing.value = false
    findingMore.value = false
    jobs.load(String(id))
    await store.attach(String(id))
    try {
      await store.loadModels()
    } catch (cause) {
      store.error = (cause as Error).message
    }
    if (store.run?.profile) {
      profile.load(store.run, store.defaultEvaluation)
      initialized = String(id)
    }
  },
  { immediate: true },
)
// Extraction may complete after initial attachment; initialize its draft once.
watch(
  () => store.run?.profile,
  (value) => {
    if (value && initialized !== store.runId && store.run) {
      profile.load(store.run, store.defaultEvaluation)
      initialized = store.runId
    }
  },
)
// Keep completed workspaces on a shareable results route.
watch(
  () => store.run?.status,
  (value) => {
    if (
      value === 'complete' &&
      store.runId === String(route.params.runId) &&
      !route.path.endsWith('/results')
    )
      void router.replace(`/run/${store.runId}/results`)
  },
  { immediate: true },
)
watch([() => store.run?.id, () => store.run?.saved_profile_id], () => {
  if (store.run) void jobs.sync(store.run)
})
onBeforeUnmount(() => store.stop())
// Append when results exist; otherwise confirm the initial profile and search.
async function confirm() {
  const success =
    findingMore.value || hasResults.value
      ? await store.findMore(profile.preferences)
      : await store.confirm(profile.draft, profile.preferences)
  if (success) {
    editing.value = false
    findingMore.value = false
  }
}
// Open prefilled search-only preferences without issuing job-board requests.
function findMore() {
  if (!canFindMore.value || store.busy) return
  profile.load(store.run!, store.defaultEvaluation)
  findingMore.value = true
  editing.value = true
}
// Close the editor without submitting another search.
function backToResults() {
  editing.value = false
  findingMore.value = false
}
// Send cooperative cancellation and close the confirmation dialog.
async function cancelRun() {
  await store.action('cancel')
  confirmAction.value = false
}
// Route retries with existing results through the non-replacing append flow.
function edit() {
  if (hasResults.value) findMore()
  else navigate(1)
}
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <h1 class="mb-5 text-3xl font-bold">Your career search</h1>
  <p v-if="store.connecting" role="status" class="panel">Loading your run…</p>
  <p
    v-if="store.reconnecting"
    role="status"
    class="mb-4 rounded-xl bg-amber-50 dark:bg-amber-950 p-3 text-sm text-amber-900 dark:text-amber-300"
  >
    Connection lost. Reconnecting automatically; your server run continues.
  </p>
  <ErrorState v-if="store.error" title="Request could not finish" :message="store.error"
    ><button class="btn-secondary" @click="store.attach(String(route.params.runId))">
      Reconnect to run
    </button></ErrorState
  >
  <template v-if="store.run">
    <div class="mb-5 flex flex-wrap justify-end gap-2">
      <button
        v-if="canFindMore && !editing"
        class="btn-primary"
        :disabled="store.busy"
        @click="findMore"
      >
        Find more jobs</button
      ><button
        v-if="editing && (hasResults || store.run.status === 'complete')"
        class="btn-secondary"
        :disabled="store.busy"
        @click="backToResults"
      >
        Back to results</button
      ><button
        v-if="store.running"
        class="btn-secondary"
        :disabled="store.busy"
        @click="confirmAction = true"
      >
        Cancel run</button
      ><button
        v-if="showingResults"
        class="btn-secondary"
        :disabled="store.busy || store.running"
        @click="router.push('/')"
      >
        Upload new resume
      </button>
    </div>
    <section
      v-if="confirmAction"
      role="alertdialog"
      aria-modal="false"
      aria-labelledby="confirmation-title"
      class="panel mb-5 border-amber-400"
    >
      <h2 id="confirmation-title" class="font-semibold">Cancel this run?</h2>
      <p class="my-3 text-sm">
        Further work will stop. Completed results will be kept. In-flight provider calls may finish.
      </p>
      <button class="btn-primary mr-3" :disabled="store.busy" @click="cancelRun">
        Yes, cancel run</button
      ><button class="btn-secondary" @click="confirmAction = false">Keep working</button>
    </section>
    <ApplicationStepper
      :run="store.run"
      :loading="store.running"
      :editing="editing"
      :navigable-steps="navigableSteps"
      @navigate="navigate"
    />
    <ErrorState
      v-if="store.run.status === 'error'"
      :title="store.run.profile ? 'Search needs attention' : 'Resume could not be read'"
      :message="store.run.error || 'Please retry.'"
      ><button
        v-if="store.run.profile && !store.run.scrape_errors?.length"
        class="btn-secondary"
        :disabled="store.running"
        @click="edit"
      >
        {{
          hasResults ? 'Review search and find more jobs' : 'Review profile and retry scraping'
        }}</button
      ><RouterLink v-if="!store.run.profile" to="/" class="btn-secondary"
        >Try another PDF</RouterLink
      ></ErrorState
    >
    <p v-if="store.run.status === 'cancelled'" role="status" class="panel mb-4">
      Run cancelled.
      {{
        store.running
          ? 'Waiting for in-flight requests to finish.'
          : hasResults
            ? 'Your results are kept. Use Find more jobs to continue.'
            : 'You can review your profile and start again.'
      }}
    </p>
    <section
      v-if="store.run.scrape_errors?.length"
      class="mb-4 rounded-xl bg-amber-50 dark:bg-amber-950 p-4 text-sm text-amber-900 dark:text-amber-300"
    >
      <h2 class="font-semibold">Some job-board searches failed</h2>
      <p v-for="(message, index) in store.run.scrape_errors" :key="index">{{ message }}</p>
      <button
        v-if="!store.running"
        class="btn-secondary mt-3"
        :disabled="store.busy"
        @click="store.action('retry-scraping')"
      >
        Retry scraping
      </button>
    </section>
    <p
      v-if="
        store.run.status === 'complete' &&
        store.run.saved_profile_id &&
        !store.run.profile_save_error
      "
      role="status"
      class="panel mb-4"
    >
      Your resume profile and search preferences are saved. You can return from Saved resumes.
    </p>
    <p
      v-if="store.run.profile_save_error"
      role="alert"
      class="panel mb-4 text-amber-900 dark:text-amber-200"
    >
      {{ store.run.profile_save_error }}
    </p>
    <SaveProfile
      :run-id="store.runId"
      :saved-profile-id="store.run.saved_profile_id"
      :saved-profile-name="store.run.saved_profile_name"
      v-if="store.run.profile && !store.running"
      :profile="
        editing || store.run.status === 'awaiting_search' || store.run.status === 'cancelled'
          ? profile.draft
          : store.run.profile
      "
      :preferences="
        editing || store.run.status === 'awaiting_search' || store.run.status === 'cancelled'
          ? profile.preferences
          : (store.run.preferences as Partial<Preferences> | undefined)
      "
    />
    <ProfileReview
      v-if="
        store.run.profile &&
        !store.running &&
        (store.run.status === 'awaiting_search' ||
          (store.run.status === 'cancelled' && !hasResults) ||
          editing)
      "
      :models="store.modelOptions"
      :disabled="store.busy"
      :search-only="findingMore"
      @confirm="confirm"
    />
    <JobDashboard
      v-if="!editing && (hasResults || store.run.phase >= 4 || store.run.status === 'complete')"
      :run-id="store.runId"
      :jobs="store.run.recommendations || []"
      :excluded-jobs="store.run.excluded_recommendations || []"
      :evaluation-model-id="store.run.evaluation_model_id || ''"
      :evaluation-options="store.modelOptions"
      :evaluation-errors="store.run.evaluation_errors || []"
      :running="store.running"
      :retrying-evaluations="
        store.activeAction === 'retry-evaluation' ||
        (store.running && store.run.message === 'Retrying failed evaluations only')
      "
      :busy="store.busy"
      :excel-url="`/api/searches/${store.runId}/exports/relevant_jobs.xlsx`"
      @retry-evaluation="store.action('retry-evaluation')"
    />
    <EmptyState
      v-else-if="
        !store.run.profile && store.run.status !== 'running' && store.run.status !== 'error'
      "
      title="No profile available"
      message="Upload a resume to create a profile."
      ><RouterLink to="/" class="btn-primary">Upload resume</RouterLink></EmptyState
    >
  </template>
</template>

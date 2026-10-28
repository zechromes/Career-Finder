<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useJobsStore, type DismissalInput } from '../stores/jobs'
import { useSnackbarStore } from '../stores/snackbar'
const store = useJobsStore()
const snackbar = useSnackbarStore()
const dialog = ref<HTMLDialogElement | null>(null)
const reason = ref<DismissalInput['reason'] | ''>('')
const minimum = ref<number | null>(null)
const currency = ref<NonNullable<DismissalInput['currency']>>('AUD')
const period = ref<NonNullable<DismissalInput['period']>>('year')
let previousFocus: HTMLElement | null = null
watch(
  () => store.dismissTarget,
  async (job) => {
    if (job) {
      previousFocus = document.activeElement as HTMLElement
      reason.value = ''
      minimum.value = null
      currency.value = 'AUD'
      period.value = 'year'
      await nextTick()
      if (store.dismissTarget) dialog.value?.showModal()
    } else {
      dialog.value?.close()
      await nextTick()
      if (previousFocus?.isConnected) previousFocus.focus()
      else document.querySelector<HTMLElement>('#results-heading')?.focus()
    }
  },
)
function confirm() {
  const job = store.dismissTarget
  if (!job) return
  if (reason.value === 'salary' && (!minimum.value || minimum.value <= 0)) return
  const details: DismissalInput | null = reason.value
    ? {
        reason: reason.value,
        ...(reason.value === 'salary'
          ? { minimum_salary: minimum.value, currency: currency.value, period: period.value }
          : {}),
      }
    : null
  store.dismiss(job, details)
  snackbar.show(
    details && details.reason !== 'other'
      ? 'Job dismissed. Preference saved for future searches.'
      : 'Job dismissed.',
  )
}
</script>

<template>
  <Teleport to="body">
    <dialog
      ref="dialog"
      aria-labelledby="dismiss-title"
      aria-describedby="dismiss-description"
      class="w-[calc(100%-2rem)] max-w-lg rounded-xl border border-slate-300 bg-white p-6 text-slate-900 shadow-xl dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
      @cancel.prevent="store.dismissTarget = null"
    >
      <form @submit.prevent="confirm">
        <h2 id="dismiss-title" class="text-xl font-bold">Dismiss this job</h2>
        <p class="mt-2 text-sm">
          {{ store.dismissTarget?.title }} at {{ store.dismissTarget?.company }}
        </p>
        <p id="dismiss-description" class="mt-3 text-sm text-slate-600 dark:text-slate-300">
          Optionally tell us why. Matching jobs will rank lower in future searches; fit scores stay
          unchanged. Restore this job or remove its preference later to undo the feedback.
        </p>
        <label for="dismiss-reason" class="mt-4 block text-sm font-medium">Reason (optional)</label>
        <select id="dismiss-reason" v-model="reason" class="field mt-1" autofocus>
          <option value="">Just dismiss — don't change preferences</option>
          <option value="role">Not interested in this role</option>
          <option value="location">Wrong location</option>
          <option value="seniority">Wrong seniority</option>
          <option value="salary">Salary too low</option>
          <option value="other">Other — record only</option>
        </select>
        <p v-if="reason === 'role'" class="mt-2 text-sm">Fewer jobs with this same role title.</p>
        <p v-if="reason === 'location'" class="mt-2 text-sm">
          Fewer jobs with this same stated location. Unknown locations are unaffected.
        </p>
        <p v-if="reason === 'seniority'" class="mt-2 text-sm">
          Fewer jobs at the level explicitly named in this title. Unmarked or mixed-level titles are
          unaffected.
        </p>
        <fieldset v-if="reason === 'salary'" class="mt-4 space-y-3">
          <legend class="text-sm font-medium">Your minimum acceptable pay</legend>
          <label class="block text-sm"
            >Minimum amount
            <input
              v-model.number="minimum"
              type="number"
              min="0.01"
              max="10000000"
              step="0.01"
              required
              class="field mt-1"
            />
          </label>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label for="dismiss-currency" class="text-sm">Currency</label>
              <select id="dismiss-currency" v-model="currency" class="field mt-1">
                <option v-for="code in ['AUD', 'USD', 'GBP', 'EUR', 'CAD', 'NZD']" :key="code">
                  {{ code }}
                </option>
              </select>
            </div>
            <div>
              <label for="dismiss-period" class="text-sm">Pay period</label>
              <select id="dismiss-period" v-model="period" class="field mt-1">
                <option value="year">Per year</option>
                <option value="hour">Per hour</option>
              </select>
            </div>
          </div>
          <p class="text-sm">
            Only clearly stated salary ranges wholly below your minimum in the same currency and
            period rank lower. Missing or ambiguous pay is unaffected.
          </p>
        </fieldset>
        <div class="mt-6 flex justify-end gap-3">
          <button type="button" class="btn-secondary" @click="store.dismissTarget = null">
            Cancel
          </button>
          <button type="submit" class="btn-primary">Dismiss job</button>
        </div>
      </form>
    </dialog>
  </Teleport>
</template>
<style scoped>
dialog::backdrop {
  background: rgb(15 23 42 / 55%);
}
</style>

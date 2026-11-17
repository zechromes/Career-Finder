<!-- Map backend progress to navigable stages while disabling unavailable transitions. -->
<script setup lang="ts">
import { computed } from 'vue'
import { CheckIcon } from '@heroicons/vue/24/outline'
import type { Run } from '../types/domain'

const props = defineProps<{
  run?: Run | null
  loading?: boolean
  editing?: boolean
  navigableSteps?: number[]
}>()
const emit = defineEmits<{ navigate: [step: number] }>()
const steps = [
  { title: 'Upload resume', detail: 'Turn your PDF into a career profile.' },
  { title: 'Review your profile', detail: 'Confirm your experience, roles and locations.' },
  { title: 'Find opportunities', detail: 'Collect openings, match skills and evaluate fit.' },
  { title: 'Explore results', detail: 'Review your matches and export your shortlist.' },
]
const currentStep = computed(() => {
  if (props.editing) return 1
  if (!props.run) return 0
  if (props.run.status === 'complete') return 3
  if (props.run.status === 'awaiting_search') return 1
  if (props.run.phase >= 2) return 2
  return 0
})
// Derive each stage’s completed, active, or upcoming appearance.
function state(index: number) {
  if (index < currentStep.value || (props.run?.status === 'complete' && !props.editing))
    return 'done'
  if (index > currentStep.value) return 'pending'
  if (props.run?.status === 'error' && !props.editing) return 'failed'
  if (props.run?.status === 'cancelled' && !props.editing) return 'paused'
  return 'active'
}
const progressPercent = computed(() => {
  const run = props.run
  // A retry reports its own counters; the search-wide ones are already near 100%.
  const [done, total] = run?.retry_total
    ? [run.retry_done, run.retry_total]
    : [run?.evaluated_jobs, run?.evaluation_total]
  if (run?.phase !== 4 || !total) return undefined
  return Math.min(100, Math.max(0, Math.round((100 * (done || 0)) / total)))
})
const labels = {
  done: 'Complete',
  pending: 'Up next',
  active: 'Current stage',
  failed: 'Needs attention',
  paused: 'Paused',
}
</script>

<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <section aria-label="Application timeline" class="panel mb-5">
    <p class="eyebrow">Your journey</p>
    <h2 class="mb-6 mt-2 text-xl font-bold text-slate-900 dark:text-slate-100">
      From resume to opportunity
    </h2>
    <ol class="journey" tabindex="0" aria-label="Scroll horizontally to view all stages">
      <li
        v-for="(step, index) in steps"
        :key="step.title"
        class="journey-stage"
        :class="`is-${state(index)}`"
        :aria-current="index === currentStep && run?.status !== 'complete' ? 'step' : undefined"
      >
        <div class="journey-marker" aria-hidden="true">
          <CheckIcon v-if="state(index) === 'done'" class="h-5 w-5" /><span v-else
            >0{{ index + 1 }}</span
          >
        </div>
        <div class="journey-card">
          <div class="flex flex-col items-center gap-2">
            <h3 class="text-sm font-bold text-slate-900 dark:text-slate-100">
              <button
                v-if="navigableSteps?.includes(index)"
                type="button"
                class="rounded underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
                :aria-current="index === currentStep ? 'step' : undefined"
                @click="emit('navigate', index)"
              >
                {{ step.title }}</button
              ><template v-else>{{ step.title }}</template>
            </h3>
            <span class="journey-status"
              ><span
                v-if="loading && state(index) === 'active'"
                aria-hidden="true"
                class="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none"
              />{{ labels[state(index)] }}</span
            >
          </div>
          <p class="mt-1 text-sm text-slate-600 dark:text-slate-300">{{ step.detail }}</p>
        </div>
      </li>
    </ol>
    <div v-if="run" class="mt-5 rounded-xl bg-slate-50 dark:bg-slate-950 px-4 py-3">
      <div
        v-if="run.status === 'running'"
        role="progressbar"
        :aria-label="run.phase === 4 ? 'Job evaluation progress' : 'Job search progress'"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-valuenow="progressPercent"
        :aria-valuetext="run.message || 'Working…'"
        class="mb-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
      >
        <div
          class="h-full rounded-full bg-indigo-600 dark:bg-indigo-400"
          :class="
            progressPercent === undefined
              ? 'progress-indeterminate'
              : 'transition-[width] motion-reduce:transition-none'
          "
          :style="{ width: progressPercent === undefined ? '35%' : `${progressPercent}%` }"
        />
      </div>
      <p aria-live="polite" class="text-sm text-slate-700 dark:text-slate-200">
        {{ run.message
        }}<span v-if="run.phase === 4 && run.retry_total">
          · {{ run.retry_done || 0 }} of {{ run.retry_total }} assessments retried</span
        ><span v-else-if="run.phase === 4">
          · {{ run.evaluated_jobs || 0 }} of {{ run.evaluation_total || 0 }} evaluated</span
        ><span v-else-if="run.phase === 2"> · {{ run.jobs_found || 0 }} postings found</span
        ><span v-else-if="run.phase === 3">
          · {{ run.jobs_screened || 0 }} candidates for matching</span
        >
      </p>
      <p
        v-if="run.status === 'awaiting_search'"
        class="mt-2 text-sm font-semibold text-teal-700 dark:text-teal-300"
      >
        Profile review — confirm your details before scraping starts.
      </p>
    </div>
  </section>
</template>

<!-- Component presentation and interaction styling. -->
<style scoped>
.progress-indeterminate {
  animation: search-progress 1.6s ease-in-out infinite alternate;
}
@keyframes search-progress {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(185%);
  }
}
@media (prefers-reduced-motion: reduce) {
  .progress-indeterminate {
    animation: none;
  }
}

.journey {
  display: grid;
  grid-template-columns: repeat(4, minmax(14rem, 1fr));
  gap: 1rem;
  overflow-x: auto;
  list-style: none;
  margin: 0;
  padding: 0.25rem 0.25rem 0.75rem;
}
.journey-stage {
  position: relative;
  display: grid;
  grid-template-rows: 2.5rem 1fr;
  gap: 1rem;
  min-width: 0;
  text-align: center;
}

.journey-stage:not(:last-child)::before {
  content: '';
  position: absolute;
  top: calc(1.25rem - 1px);
  left: calc(50% + 1.25rem);
  width: calc(100% + 1rem - 2.5rem);
  height: 2px;
  background: #e2e8f0;
}
.journey-marker {
  margin-inline: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border: 1px solid #cbd5e1;
  border-radius: 50%;
  background: #f8fafc;
  color: #64748b;
  font-size: 0.75rem;
  font-weight: 700;
}
.journey-card {
  padding: 1.25rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.75rem;
}
.journey-status {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.6875rem;
  font-weight: 600;
  color: #64748b;
}
.is-done::before {
  background: #0f766e !important;
}
.is-done .journey-marker {
  color: white;
  background: #0f766e;
  border-color: #0f766e;
}
.is-done .journey-status {
  color: #0f766e;
}
.is-active .journey-marker {
  color: white;
  background: #4f46e5;
  border-color: #4f46e5;
  box-shadow: 0 0 0 4px #eef2ff;
}
.is-active .journey-card {
  background: #eef2ff;
  border-color: #c7d2fe;
}
.is-active .journey-status {
  color: #4338ca;
}
.is-failed .journey-marker,
.is-failed .journey-status {
  color: #be123c;
  border-color: #fecdd3;
}
.is-paused .journey-marker,
.is-paused .journey-status {
  color: #92400e;
  border-color: #fcd34d;
}

.dark .journey-marker {
  background: #1e293b;
  border-color: #475569;
  color: #cbd5e1;
}
.dark .journey-card {
  border-color: #334155;
}
.dark .journey-status {
  color: #cbd5e1;
  background: transparent;
}
.dark .journey-stage:not(:last-child)::before {
  background: #334155;
}
.dark .is-done::before {
  background: #0d9488;
}
.dark .is-done .journey-marker {
  background: #0f766e;
  border-color: #0f766e;
  color: white;
}
.dark .is-done .journey-status {
  color: #5eead4;
}
.dark .is-active .journey-marker {
  background: #4f46e5;
  border-color: #818cf8;
  color: white;
  box-shadow: 0 0 0 4px #1e1b4b;
}
.dark .is-active .journey-card {
  background: #1e1b4b;
  border-color: #818cf8;
}
.dark .is-active .journey-status {
  color: #eef2ff;
  background: #3730a3;
  border-radius: 999px;
  padding: 0.25rem 0.625rem;
  font-size: 0.75rem;
}
.dark .is-failed .journey-marker,
.dark .is-failed .journey-status {
  background: #4c0519;
  border-color: #9f1239;
  color: #fda4af;
}
.dark .is-paused .journey-marker,
.dark .is-paused .journey-status {
  background: #451a03;
  border-color: #92400e;
  color: #fcd34d;
}
</style>

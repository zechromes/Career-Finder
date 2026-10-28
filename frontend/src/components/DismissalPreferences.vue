<script setup lang="ts">
import { nextTick } from 'vue'
import { useJobsStore } from '../stores/jobs'
const store = useJobsStore()
async function forget(key: string) {
  store.forgetFeedback(key)
  await nextTick()
  document.getElementById('results-heading')?.focus()
}
const labels = {
  role: 'Same role title',
  location: 'Same location',
  seniority: 'Same explicit seniority',
  salary: 'Below minimum pay',
  other: 'Other (record only)',
}
</script>
<template>
  <details
    v-if="Object.keys(store.feedback).length"
    class="my-4 rounded-xl border border-slate-200 p-4 dark:border-slate-700"
  >
    <summary class="cursor-pointer font-medium">
      Dismissal preferences ({{ Object.keys(store.feedback).length }})
    </summary>
    <p class="my-3 text-sm text-slate-600 dark:text-slate-300">
      These preferences rank matching jobs lower on your next search. They do not change fit scores
      or exclude jobs.
    </p>
    <ul class="space-y-3">
      <li
        v-for="(item, key) in store.feedback"
        :key="key"
        class="flex flex-wrap items-center justify-between gap-3"
      >
        <span class="text-sm"
          ><strong>{{ labels[item.reason] }}</strong> — {{ item.title }}
          <span v-if="item.reason === 'location'">
            · {{ item.location || 'Unknown location (no ranking effect)' }}</span
          >
          <span v-if="item.reason === 'salary'">
            · {{ item.minimum_salary }} {{ item.currency }} / {{ item.period }}</span
          >
        </span>
        <button
          class="btn-secondary"
          type="button"
          :aria-label="`Remove preference for ${item.title}`"
          @click="forget(key)"
        >
          Remove preference
        </button>
      </li>
    </ul>
  </details>
</template>

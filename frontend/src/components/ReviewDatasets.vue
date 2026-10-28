<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../stores/pipeline'
import type { components } from '../types/api'
const props = defineProps<{ sourceId: string; disabled?: boolean }>()
const rows = ref<components['schemas']['ReviewDatasetSummary'][]>([])
const error = ref('')
const busy = ref(false)
const pendingDelete = ref('')
async function load() {
  try {
    rows.value = await api('/api/review-datasets')
  } catch (cause) {
    error.value = (cause as Error).message
  }
}
async function create() {
  busy.value = true
  error.value = ''
  try {
    await api('/api/review-datasets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_id: props.sourceId }),
    })
    await load()
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
// Delete the confirmed snapshot and its reviews, then clear the pending selection.
async function remove(id: string) {
  busy.value = true
  error.value = ''
  try {
    await api(`/api/review-datasets/${id}`, { method: 'DELETE' })
    pendingDelete.value = ''
    await load()
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
onMounted(load)
</script>
<template>
  <section
    aria-label="Human review datasets"
    class="space-y-3 rounded-xl border border-slate-200 p-5 dark:border-slate-700"
  >
    <h2 class="text-xl font-semibold">Review datasets</h2>
    <p>
      A review dataset is a saved copy of a search's jobs, including ones the app did not pick, for
      you to label. Open one to start labeling. It contains your profile text and stays on this
      server until you delete it.
    </p>
    <p v-if="error" role="alert">{{ error }}</p>
    <button
      class="btn-secondary"
      type="button"
      :disabled="!sourceId || disabled || busy"
      @click="create"
    >
      {{ busy ? 'Preparing dataset…' : 'Create review dataset' }}
    </button>
    <p v-if="!rows.length">No review datasets yet. Choose a workspace above to prepare one.</p>
    <ul class="space-y-2">
      <li v-for="row in rows" :key="row.id">
        <RouterLink
          class="inline-block py-2 text-indigo-700 underline dark:text-indigo-300"
          :to="`/eval/datasets/${row.id}`"
          >Review dataset · {{ new Date(row.created_at * 1000).toLocaleString() }} ·
          {{ row.job_count }} jobs</RouterLink
        >
        <p class="text-sm">
          {{ row.outside_shortlist }} outside the previous shortlist · {{ row.reviewed_jobs }} fit
          labels saved
        </p>
        <button
          v-if="pendingDelete !== row.id"
          class="btn-secondary mt-1"
          type="button"
          :disabled="busy"
          :aria-label="`Delete review dataset from ${new Date(row.created_at * 1000).toLocaleString()}`"
          @click="pendingDelete = row.id"
        >
          Delete review dataset
        </button>
        <div v-else role="alert" class="mt-1">
          <p>
            Delete this review dataset and all {{ row.reviewed_jobs }} saved reviews? This cannot be
            undone. The source workspace is not affected.
          </p>
          <button class="btn-secondary mt-2" type="button" :disabled="busy" @click="remove(row.id)">
            Confirm delete
          </button>
          <button
            class="btn-secondary ml-2 mt-2"
            type="button"
            :disabled="busy"
            @click="pendingDelete = ''"
          >
            Keep dataset
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>

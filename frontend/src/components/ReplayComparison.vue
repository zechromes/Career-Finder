<!-- Re-runs the frozen search's shortlist under each seniority rule, scored with your labels. -->
<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../stores/pipeline'
import type { components } from '../types/api'
type S = components['schemas']
const props = defineProps<{ datasetId: string; bundle: S['ReviewBundle'] }>()
const busy = ref(false)
const error = ref('')
const result = ref<S['ReplayResult']>()
const percent = (value?: number | null) =>
  value == null ? 'Not available' : `${(value * 100).toFixed(0)}%`
const title = (id: string) => props.bundle.dataset.jobs.find((job) => job.id === id)?.title || id

async function run() {
  busy.value = true
  error.value = ''
  try {
    result.value = await api<S['ReplayResult']>(`/api/review-datasets/${props.datasetId}/replay`, {
      method: 'POST',
    })
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <section aria-label="Replay retrieval" class="space-y-3">
    <h3 class="font-semibold">Replay with each seniority rule</h3>
    <p class="text-sm">
      Re-ranks this dataset's frozen job pool under the earlier and current seniority rules and
      scores both shortlists against your labels. No AI assessments run. The first replay sends your
      role and profile queries to OpenAI for embedding (a fraction of a cent) and needs the original
      search; the ranking is then saved with the dataset, so later replays are free.
    </p>
    <button type="button" class="btn-secondary" :disabled="busy" @click="run">
      {{ busy ? 'Replaying…' : 'Replay retrieval' }}
    </button>
    <p v-if="error" role="alert" class="text-rose-700 dark:text-rose-300">{{ error }}</p>
    <div v-if="result" class="space-y-2" role="status">
      <div class="overflow-x-auto" tabindex="0" role="region" aria-label="Replay results">
        <table class="w-full text-left text-sm">
          <thead>
            <tr>
              <th scope="col" class="py-1 pr-3">Rule</th>
              <th scope="col" class="py-1 pr-3">Good fits shortlisted (recall)</th>
              <th scope="col" class="py-1 pr-3">Precision on labeled</th>
              <th scope="col" class="py-1 pr-3">Good fits added</th>
              <th scope="col" class="py-1 pr-3">Not-fits added</th>
              <th scope="col" class="py-1 pr-3">Matches original shortlist</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rule in result.rules" :key="rule.rule">
              <th scope="row" class="py-1 pr-3 font-medium">{{ rule.name }}</th>
              <td class="py-1 pr-3">{{ percent(rule.metrics.observed_recall_at_k) }}</td>
              <td class="py-1 pr-3">{{ percent(rule.metrics.precision_on_labeled) }}</td>
              <td class="py-1 pr-3">{{ rule.good_fits_added.length }}</td>
              <td class="py-1 pr-3">{{ rule.not_fits_added.length }}</td>
              <td class="py-1 pr-3">{{ percent(rule.matches_original) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <template v-for="rule in result.rules" :key="rule.rule">
        <div v-if="rule.good_fits_added.length || rule.not_fits_added.length">
          <h4 class="font-semibold">Added to the shortlist by "{{ rule.name }}"</h4>
          <ul class="list-disc space-y-1 pl-6 text-sm">
            <li v-for="id in rule.good_fits_added" :key="id">{{ title(id) }} · your good fit</li>
            <li v-for="id in rule.not_fits_added" :key="id">{{ title(id) }} · not a fit</li>
          </ul>
        </div>
      </template>
      <p class="text-sm">
        Top {{ result.top_k }} per search across {{ result.searches }} search(es), ranked with
        {{ result.embedding_model }}.
      </p>
      <ul class="list-disc space-y-1 pl-6 text-sm">
        <li v-for="note in result.limitations" :key="note">{{ note }}</li>
      </ul>
    </div>
  </section>
</template>

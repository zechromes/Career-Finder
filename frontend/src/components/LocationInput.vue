<!-- Request debounced location suggestions and discard stale responses. -->
<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import ChipInput from './ChipInput.vue'
import { api } from '../stores/pipeline'
const locations = defineModel<string[]>({ default: () => [] })
// Suggestion results and request state are independent of the selected location chips.
const suggestions = ref<{ label: string; value: string }[]>([])
const loading = ref(false)
const message = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
let controller: AbortController | undefined
let version = 0
// Debounce lookups and cancel obsolete requests as the location query changes.
function suggest(value: string) {
  const token = ++version
  clearTimeout(timer)
  controller?.abort()
  suggestions.value = []
  loading.value = false
  message.value = ''
  const query = value.trim()
  if (query.length < 2) return
  loading.value = true
  timer = setTimeout(async () => {
    const request = new AbortController()
    controller = request
    try {
      const data = await api<{ label: string; value: string }[]>(
        `/api/locations/suggest?q=${encodeURIComponent(query)}`,
        { signal: request.signal },
      )
      if (token !== version) return
      suggestions.value = data
      if (!data.length) message.value = 'No suggestions found. Press Enter to use your location.'
    } catch {
      if (token === version)
        message.value = 'Suggestions unavailable. You can still enter a location.'
    } finally {
      if (token === version) loading.value = false
    }
  }, 500)
}
onBeforeUnmount(() => {
  version++
  clearTimeout(timer)
  controller?.abort()
})
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <!-- One root keeps the hint under the input in any grid or flex layout. -->
  <div>
    <ChipInput
      v-model="locations"
      label="Locations"
      placeholder="City or country (optional)"
      autocomplete
      :suggestions="suggestions"
      @suggest="suggest"
    />
    <p role="status" class="mt-1 text-xs text-slate-600 dark:text-slate-300">
      {{ loading ? 'Finding locations…' : message || 'Leave empty to search worldwide.' }}
    </p>
  </div>
</template>

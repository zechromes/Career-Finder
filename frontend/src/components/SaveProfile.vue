<!-- Create or update a saved resume without creating duplicates on repeated saves. -->
<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../stores/pipeline'
import type { Profile, Preferences } from '../types/domain'
const props = defineProps<{
  runId: string
  profile: Profile
  preferences?: Partial<Preferences>
  savedProfileId?: string | null
  savedProfileName?: string
}>()
const name = ref('')
const savedId = ref<string | null>(null)
watch(
  () => [props.runId, props.savedProfileId, props.savedProfileName],
  () => {
    savedId.value = props.savedProfileId || null
    name.value = props.savedProfileName || ''
  },
  { immediate: true },
)
const busy = ref(false)
const message = ref('')
const error = ref('')
// Reuse the saved identifier on updates and display save failures locally.
async function save() {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    const result = await api<{ id: string; resume_available: boolean }>(
      savedId.value ? `/api/profiles/${savedId.value}` : '/api/profiles',
      {
        method: savedId.value ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.value.trim(),
          ...(savedId.value ? {} : { source_run_id: props.runId }),
          profile: props.profile,
          preferences: props.preferences?.queries?.length ? props.preferences : null,
        }),
      },
    )
    savedId.value = result.id
    message.value = result.resume_available
      ? 'Resume and profile saved. You can continue from Saved resumes.'
      : 'Profile and preferences saved. This workspace has no original PDF.'
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <section class="panel mb-5" aria-label="Save reusable profile">
    <h2 class="text-lg font-semibold">Save this resume for next time</h2>
    <p class="mt-2 text-sm text-slate-600 dark:text-slate-300">
      Your profile, available PDF, and search preferences are saved automatically when results are
      ready. You can also save now; saved resumes stay until you delete them.
    </p>
    <form class="mt-4 flex flex-wrap items-end gap-3" @submit.prevent="save">
      <label class="flex-1"
        ><span class="field-label">Saved resume name</span
        ><input
          v-model="name"
          maxlength="100"
          required
          class="field"
          placeholder="e.g. Software engineering" /></label
      ><button class="btn-secondary" :disabled="busy || !name.trim()">
        {{ busy ? 'Saving…' : savedId ? 'Save changes' : 'Save resume' }}</button
      ><RouterLink to="/profiles" class="btn-secondary">Manage saved resumes</RouterLink>
    </form>
    <p v-if="message" role="status" class="mt-3 text-sm">{{ message }}</p>
    <p v-if="error" role="alert" class="mt-3 text-sm text-rose-700 dark:text-rose-300">
      {{ error }}
    </p>
  </section>
</template>

<!-- Accept a resume for OpenAI extraction, then navigate to the created workspace. -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { usePipelineStore } from '../stores/pipeline'
import UploadZone from '../components/UploadZone.vue'
import ErrorState from '../components/ErrorState.vue'
import ApplicationStepper from '../components/ApplicationStepper.vue'
const store = usePipelineStore()
const router = useRouter()
const file = ref<File | null>(null)
const priorRun = ref('')
onMounted(async () => {
  store.stop()
  try {
    priorRun.value = sessionStorage.getItem('careerActiveRunId') || ''
    await store.loadModels()
  } catch (cause) {
    store.error = (cause as Error).message
  }
})
// Upload the chosen file and navigate only after the server returns a run ID.
async function upload() {
  if (file.value) {
    const id = await store.upload(file.value, 'openai')
    if (id) await router.push(`/run/${id}`)
  }
}
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <ApplicationStepper :loading="store.busy" />
  <section class="panel w-full">
    <p class="eyebrow">Find your next opportunity</p>
    <h1 class="mt-2 text-3xl font-bold">Start with your resume</h1>
    <p class="mb-6 mt-3 text-slate-600 dark:text-slate-300">
      Upload a PDF. Review and correct your profile before we search for jobs.
    </p>
    <div class="mb-6 rounded-xl border border-indigo-200 p-4 dark:border-indigo-800">
      <h2 class="font-semibold">Already saved a resume?</h2>
      <p class="mt-2 text-sm text-slate-600 dark:text-slate-300">
        Continue with a saved resume, or upload a new resume below.
      </p>
      <RouterLink to="/profiles" class="btn-secondary mt-3"
        >Continue with a saved resume</RouterLink
      >
    </div>
    <UploadZone v-model="file" :disabled="store.busy" />
    <p class="mt-5 text-sm text-slate-600 dark:text-slate-300">
      Profile extraction · Powered by OpenAI
    </p>
    <p class="mt-4 text-sm text-slate-600 dark:text-slate-300">
      Uploading sends your resume to this server and resume text to OpenAI for profile extraction. Run
      data is retained for 7 days or until you delete it. Scanned pages use local OCR.
      <RouterLink to="/privacy" class="underline text-indigo-700 dark:text-indigo-300"
        >Privacy details</RouterLink
      >
    </p>
    <ErrorState v-if="store.error" title="Upload or connection problem" :message="store.error"
      ><button
        class="btn-secondary"
        @click="
          store
            .loadModels()
            .then(() => (store.error = ''))
            .catch((error) => (store.error = error.message))
        "
      >
        Retry connection
      </button></ErrorState
    >
    <button
      class="btn-primary mt-6 w-full"
      :disabled="!file || store.busy || !store.profileOptions.length"
      @click="upload"
    >
      {{ store.busy ? 'Uploading and extracting profile…' : 'Upload and extract profile' }}
    </button>
    <RouterLink
      v-if="priorRun"
      :to="`/run/${priorRun}`"
      class="mt-4 block text-center text-sm text-indigo-700 dark:text-indigo-300 underline"
      >Return to your previous run</RouterLink
    >
  </section>
</template>

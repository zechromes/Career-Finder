<!-- Validate PDF selection from the file picker or drag-and-drop interaction. -->
<script setup lang="ts">
import { ref, watch } from 'vue'
import { ArrowUpTrayIcon, DocumentTextIcon } from '@heroicons/vue/24/outline'
const props = defineProps<{ disabled?: boolean }>()
const file = defineModel<File | null>({ default: null })
const input = ref<HTMLInputElement | null>(null)
const dragging = ref(false)
const error = ref('')
watch(file, (value) => {
  if (!value && input.value) input.value.value = ''
})
// Reject unsupported or oversized files before emitting a resume selection.
function choose(candidate?: File) {
  if (props.disabled || !candidate) return
  let reason = ''
  if (
    !candidate.name.toLowerCase().endsWith('.pdf') ||
    (candidate.type && candidate.type !== 'application/pdf')
  )
    reason = 'Please choose a PDF resume (.pdf and PDF file type).'
  else if (!candidate.size) reason = 'This file is empty. Choose a PDF containing your resume.'
  else if (candidate.size > 5 * 1024 * 1024)
    reason = 'This file exceeds 5 MB. Choose a smaller PDF.'
  error.value = reason
  file.value = reason ? null : candidate
}
// Open the native file picker only when uploads are enabled.
function open() {
  if (!props.disabled) input.value?.click()
}
// Clear drag feedback and validate the first dropped file.
function drop(event: DragEvent) {
  dragging.value = false
  choose(event.dataTransfer?.files[0])
}
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <div
    role="button"
    :tabindex="disabled ? -1 : 0"
    :aria-disabled="disabled"
    aria-label="Browse files to upload a PDF resume"
    aria-describedby="upload-help"
    class="flex min-h-52 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center"
    :class="
      disabled
        ? 'cursor-not-allowed opacity-60'
        : dragging
          ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-950'
          : 'border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-950'
    "
    @click="open"
    @keydown.enter.prevent="open"
    @keydown.space.prevent="open"
    @dragover.prevent="dragging = !disabled"
    @dragleave.prevent="dragging = false"
    @drop.prevent="drop"
  >
    <input
      ref="input"
      type="file"
      accept=".pdf,application/pdf"
      class="hidden"
      tabindex="-1"
      :disabled="disabled"
      @click.stop
      @change="choose(($event.target as HTMLInputElement).files?.[0])"
    />
    <component
      :is="file ? DocumentTextIcon : ArrowUpTrayIcon"
      class="mb-3 h-9 w-9 text-indigo-600 dark:text-indigo-300"
      aria-hidden="true"
    />
    <strong>{{ file?.name || 'Drop your PDF resume here' }}</strong>
    <span class="mt-3 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white"
      >Browse Files</span
    >
    <span id="upload-help" class="mt-3 text-sm text-slate-600 dark:text-slate-300"
      >PDF · Up to 5 MB and 20 pages · Scans supported with OCR</span
    >
    <span v-if="error" role="alert" class="mt-3 text-sm text-rose-700 dark:text-rose-300">{{
      error
    }}</span>
  </div>
</template>

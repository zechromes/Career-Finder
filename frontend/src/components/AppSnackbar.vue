<script setup lang="ts">
import { XMarkIcon } from '@heroicons/vue/24/outline'
import { useSnackbarStore } from '../stores/snackbar'
const snackbar = useSnackbarStore()
</script>

<template>
  <div class="pointer-events-none fixed inset-x-4 bottom-6 z-[100] flex justify-start">
    <div
      v-show="snackbar.message"
      class="pointer-events-auto flex w-full max-w-md items-center gap-4 rounded-xl bg-slate-900 px-4 py-2 text-white shadow-xl ring-1 ring-white/20 dark:bg-slate-100 dark:text-slate-900"
    >
      <div role="status" aria-live="polite" aria-atomic="true" class="min-w-0 flex-1 text-sm">
        <span :key="snackbar.revision">{{ snackbar.message }}</span>
      </div>
      <button
        type="button"
        aria-label="Dismiss notification"
        class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 dark:hover:bg-slate-200"
        @click="snackbar.dismiss"
      >
        <XMarkIcon class="h-5 w-5" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>

<!-- Present a readable error message and optional recovery controls. -->
<script setup lang="ts">
defineProps<{ title?: string; message: string }>()
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <section
    role="alert"
    class="my-4 rounded-xl border border-rose-200 dark:border-rose-800 bg-rose-50 dark:bg-rose-950 p-5 text-rose-900 dark:text-rose-300"
  >
    <h2 class="font-semibold">{{ title || 'We couldn’t finish that step' }}</h2>
    <p class="mt-2 whitespace-pre-line text-sm">{{ message }}</p>
    <div class="mt-3"><slot /></div>
  </section>
</template>

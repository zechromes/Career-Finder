<!-- Present an empty-state explanation with an optional recovery action. -->
<script setup lang="ts">
defineProps<{ title: string; message: string }>()
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <section
    class="rounded-xl border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-8 text-center"
  >
    <h2 class="text-lg font-semibold">{{ title }}</h2>
    <p class="mx-auto mt-2 max-w-xl text-sm text-slate-600 dark:text-slate-300">{{ message }}</p>
    <div class="mt-4"><slot /></div>
  </section>
</template>

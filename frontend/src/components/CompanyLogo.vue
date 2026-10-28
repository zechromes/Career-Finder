<!-- Use a safe logo URL or fall back to company initials when the image is unavailable. -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
const props = defineProps<{ company?: string; src?: string }>()
const failed = ref(false)
// Validate URL schemes before allowing the browser to load an external image.
const source = computed(() => {
  try {
    const url = new URL(props.src || '')
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : ''
  } catch {
    return ''
  }
})
watch(source, () => {
  failed.value = false
})
const initials = computed(
  () =>
    (props.company || '')
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((word) => word[0] || '')
      .join('')
      .toUpperCase() || '?',
)
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <span
    aria-hidden="true"
    class="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-slate-200 bg-white text-sm font-bold text-indigo-700 dark:border-slate-600"
  >
    <img
      v-if="source && !failed"
      :src="source"
      alt=""
      width="48"
      height="48"
      loading="lazy"
      decoding="async"
      referrerpolicy="no-referrer"
      class="h-full w-full object-contain p-1.5"
      @error="failed = true"
    />
    <span v-else>{{ initials }}</span>
  </span>
</template>

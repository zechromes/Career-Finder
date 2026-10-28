<!-- Apply the browser’s selected theme and remember it across visits. -->
<script setup lang="ts">
import { ref } from 'vue'
import { MoonIcon, SunIcon } from '@heroicons/vue/24/outline'

const dark = ref(document.documentElement.classList.contains('dark'))
// Update the root theme class and persist the user’s preference.
function toggle() {
  dark.value = !dark.value
  document.documentElement.classList.toggle('dark', dark.value)
  document.documentElement.style.colorScheme = dark.value ? 'dark' : 'light'
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', dark.value ? '#020617' : '#F8FAFC')
  try {
    localStorage.setItem('careerTheme', dark.value ? 'dark' : 'light')
  } catch {
    /* The switch still works when storage is unavailable. */
  }
}
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <button
    type="button"
    class="btn-secondary shrink-0 gap-2"
    :aria-pressed="dark"
    aria-label="Dark theme"
    @click="toggle"
  >
    <SunIcon v-if="dark" class="h-5 w-5" aria-hidden="true" />
    <MoonIcon v-else class="h-5 w-5" aria-hidden="true" />
    <span>{{ dark ? 'Light theme' : 'Dark theme' }}</span>
  </button>
</template>

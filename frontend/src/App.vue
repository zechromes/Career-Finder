<!-- Provide the shared navigation, theme, and routed application content. -->
<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import ThemeToggle from './components/ThemeToggle.vue'
import AppSnackbar from './components/AppSnackbar.vue'
import DismissJobDialog from './components/DismissJobDialog.vue'
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <div class="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-8">
    <header class="mb-8 flex flex-wrap items-center justify-between gap-4">
      <RouterLink
        to="/"
        class="font-display text-2xl font-bold tracking-tight text-indigo-700 dark:text-indigo-300"
        >Career Finder</RouterLink
      >
      <nav aria-label="Main navigation" class="flex items-center gap-4">
        <RouterLink to="/settings" class="btn-secondary">Settings</RouterLink>
        <ThemeToggle />
      </nav>
    </header>
    <main id="main"><RouterView /></main>
    <AppSnackbar />
    <DismissJobDialog />
    <footer
      class="mt-10 flex justify-between border-t border-slate-200 dark:border-slate-700 py-5 text-xs text-slate-600 dark:text-slate-300"
    >
      <span>Career Finder</span
      ><RouterLink to="/privacy" class="underline">Privacy &amp; data retention</RouterLink>
    </footer>
  </div>
</template>

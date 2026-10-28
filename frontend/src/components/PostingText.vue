<!-- Render supported inline emphasis and links as Vue nodes instead of injecting raw HTML. -->
<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ text: string }>()
// Recognize a limited inline syntax; all remaining source text stays escaped.
const parts = computed(() =>
  props.text
    .split(/(\*\*[^*]+\*\*|__[^_]+__|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g)
    .filter(Boolean)
    .map((text) => {
      const link = text.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/)
      if (link) return { kind: 'link', text: link[1], href: link[2] }
      if (/^(\*\*|__)/.test(text)) return { kind: 'bold', text: text.slice(2, -2), href: '' }
      return { kind: 'text', text, href: '' }
    }),
)
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <template v-for="(part, i) in parts" :key="i"
    ><strong v-if="part.kind === 'bold'" class="font-semibold text-slate-950 dark:text-white">{{
      part.text
    }}</strong
    ><a
      v-else-if="part.kind === 'link'"
      :href="part.href"
      target="_blank"
      rel="noopener noreferrer"
      class="text-indigo-700 underline underline-offset-2 dark:text-indigo-300"
      >{{ part.text }}</a
    ><template v-else>{{ part.text }}</template></template
  >
</template>

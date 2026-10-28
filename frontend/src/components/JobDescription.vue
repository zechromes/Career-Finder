<!-- Split posting text into readable headings, paragraphs, and lists. -->
<script setup lang="ts">
import { computed } from 'vue'
import PostingText from './PostingText.vue'
const props = defineProps<{ text?: string }>()
// Render common posting formatting as Vue text nodes; source HTML is never executed.
const blocks = computed(() => {
  const result: {
    kind: 'heading' | 'paragraph' | 'list' | 'ordered'
    lines: string[]
    start?: number
  }[] = []
  let paragraphBreak = false
  for (const raw of (props.text || '').replace(/\r\n/g, '\n').split('\n')) {
    const line = raw.trim()
    if (!line) {
      paragraphBreak = true
      continue
    }
    if (/^(?:[-*•]\s*)?(?:undefined|null)$/i.test(line) || /^(?:-{3,}|_{3,}|\*{3,})$/.test(line))
      continue
    const heading = line.match(/^#{1,6}\s+(.+?)\s*#*$/) || line.match(/^\*\*(.+?)\*\*:?$/)
    const bullet = line.match(/^(?:[-*•]|\d+[.)])\s+(.+)$/)
    const ordered = line.match(/^(\d+)[.)]\s+/)
    const kind = heading ? 'heading' : ordered ? 'ordered' : bullet ? 'list' : 'paragraph'
    const text = heading?.[1] || bullet?.[1] || line
    const previous = result[result.length - 1]
    if (
      kind !== 'heading' &&
      previous?.kind === kind &&
      previous.lines.length &&
      (kind !== 'paragraph' || !paragraphBreak)
    )
      previous.lines.push(text)
    else result.push({ kind, lines: [text], start: ordered ? Number(ordered[1]) : undefined })
    paragraphBreak = false
  }
  return result.filter((block) => block.lines.length)
})
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <div
    class="posting-description break-words text-base leading-7 text-slate-700 dark:text-slate-200 [overflow-wrap:anywhere]"
  >
    <template v-for="(block, index) in blocks" :key="index">
      <h3
        v-if="block.kind === 'heading'"
        class="text-lg font-semibold text-slate-950 dark:text-white"
      >
        <PostingText :text="block.lines[0]" />
      </h3>
      <component
        :is="block.kind === 'ordered' ? 'ol' : 'ul'"
        v-else-if="block.kind === 'list' || block.kind === 'ordered'"
        :start="block.start"
        class="list-inside"
        :class="block.kind === 'ordered' ? 'list-decimal' : 'list-disc'"
        ><li v-for="(line, i) in block.lines" :key="i"><PostingText :text="line" /></li
      ></component>
      <p v-else><PostingText :text="block.lines.join(' ')" /></p>
    </template>
    <p v-if="!blocks.length">The source did not return a job description.</p>
  </div>
</template>

<!-- Component presentation and interaction styling. -->
<style scoped>
.posting-description {
  max-width: 90ch;
}
.posting-description > * + * {
  margin-top: 1rem;
}
.posting-description > h3 {
  font-size: 1.125rem;
  line-height: 1.6;
}
.posting-description > * + h3 {
  margin-top: 2rem;
}
.posting-description > h3 + * {
  margin-top: 0.625rem;
}
.posting-description > ul,
.posting-description > ol {
  list-style-position: outside;
  padding-left: 1.25rem;
}
.posting-description li + li {
  margin-top: 0.5rem;
}
.posting-description li::marker {
  color: #818cf8;
}
</style>

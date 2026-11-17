<!-- Resume sheet in the UNSW Employability guide's layout, kept ATS-friendly: one column in
reading order, bold capital headings, Arial, no tables, icons or graphics. Used for the preview
and for printing. -->
<script setup lang="ts">
import { computed } from 'vue'
import type { components } from '../types/api'
const props = defineProps<{ resume: components['schemas']['TailoredResume'] }>()
const sectionHeading = 'mt-4 border-b border-[#111] pb-0.5 text-[0.95rem] font-bold uppercase'
type Section = components['schemas']['TailoredSection']
// Sections in order, with Technical Skills placed before Interests and Referees.
const CLOSING = ['Interests', 'Referees']
const blocks = computed(() => {
  const sections = props.resume.sections || []
  return [
    ...sections.filter((section) => !CLOSING.includes(section.title)),
    ...(props.resume.skills?.length ? ['skills' as const] : []),
    ...sections.filter((section) => CLOSING.includes(section.title)),
  ] as (Section | 'skills')[]
})
// Email, phone and web addresses become links; anything else stays text.
const contactItems = computed(() =>
  (props.resume.contact || []).map((text) => {
    const value = text.trim()
    if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) return { text: value, href: `mailto:${value}` }
    if (/^\+?[\d\s().-]{7,}$/.test(value))
      return { text: value, href: `tel:${value.replace(/[^\d+]/g, '')}` }
    if (/^(https?:\/\/|www\.)|^[\w-]+(\.[\w-]+)+\/\S*$/i.test(value))
      return {
        text: value.replace(/^https?:\/\//, ''),
        href: /^https?:/i.test(value) ? value : `https://${value}`,
      }
    return { text: value, href: '' }
  }),
)
</script>
<template>
  <article class="ats-sheet bg-white text-[#111]">
    <h3 class="text-[1.75rem] font-bold leading-tight">{{ resume.name }}</h3>
    <p v-if="contactItems.length" class="mt-1 break-words text-sm">
      <template v-for="(item, index) in contactItems" :key="item.text"
        ><template v-if="index"> | </template
        ><a v-if="item.href" :href="item.href" class="text-inherit no-underline">{{ item.text }}</a
        ><template v-else>{{ item.text }}</template></template
      >
    </p>
    <template v-if="resume.profile_points?.length || resume.summary">
      <h4 :class="sectionHeading">Career Profile</h4>
      <ul
        v-if="resume.profile_points?.length"
        class="mt-1.5 list-[square] space-y-0.5 pl-5 text-sm leading-6"
      >
        <li v-for="point in resume.profile_points" :key="point">{{ point }}</li>
      </ul>
      <p v-else class="mt-1.5 text-sm leading-6">{{ resume.summary }}</p>
    </template>
    <template v-for="(block, blockIndex) in blocks" :key="blockIndex">
      <template v-if="block === 'skills'">
        <h4 :class="sectionHeading">Technical Skills</h4>
        <p class="mt-1.5 text-sm leading-6">{{ (resume.skills || []).join(', ') }}</p>
      </template>
      <template v-else>
        <h4 :class="sectionHeading">{{ block.title }}</h4>
        <div v-for="(entry, index) in block.entries" :key="index" class="resume-entry mt-2.5">
          <!-- Title then dates on one line: the guide right-aligns dates, and they follow the
          title in reading order, so ATS parsers keep them together. -->
          <p class="flex justify-between gap-4 text-sm font-bold">
            <!-- The space keeps title and dates apart in the PDF's extracted text. -->
            <span>{{ entry.heading }}</span>{{ ' ' }}<span v-if="entry.dates" class="shrink-0 whitespace-nowrap font-normal">{{ entry.dates }}</span>
          </p>
          <p v-if="entry.organization || entry.location" class="text-sm font-bold">
            {{ [entry.organization, entry.location].filter(Boolean).join(', ') }}
          </p>
          <ul
            v-if="entry.bullets?.length"
            class="mt-1 list-[square] space-y-0.5 pl-5 text-sm leading-6"
          >
            <li v-for="bullet in entry.bullets" :key="bullet">{{ bullet }}</li>
          </ul>
        </div>
      </template>
    </template>
  </article>
</template>

<style>
/* Arial at 10 to 11 points, as the guide recommends; every ATS and PDF reader handles it. */
.ats-sheet {
  font-family: Arial, Helvetica, 'Liberation Sans', sans-serif;
}
</style>

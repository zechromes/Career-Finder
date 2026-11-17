<!-- Generate, preview, print and copy a resume tailored to one job from the user's own resume. -->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api, usePipelineStore } from '../stores/pipeline'
import { jobKey } from '../stores/jobs'
import ResumeSheet from './ResumeSheet.vue'
import type { components } from '../types/api'
import type { Job } from '../types/domain'
type Resume = components['schemas']['TailoredResume']
type Section = components['schemas']['TailoredSection']
const props = defineProps<{ job: Job; runId: string }>()
const store = usePipelineStore()
const generated = ref<Resume | null>(null)
const busy = ref(false)
const error = ref('')
const copied = ref('')
watch(
  () => jobKey(props.job),
  () => {
    generated.value = null
    error.value = ''
    copied.value = ''
  },
)
const resume = computed(() => generated.value || props.job.tailored_resume || null)
async function generate() {
  busy.value = true
  error.value = ''
  copied.value = ''
  try {
    const result = await api<Resume>(`/api/searches/${props.runId}/tailored-resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: jobKey(props.job) }),
    })
    generated.value = result
    // Keep the loaded results in step with what the server saved for this job.
    for (const row of [
      ...(store.run?.recommendations || []),
      ...(store.run?.excluded_recommendations || []),
    ])
      if (jobKey(row) === jobKey(props.job)) row.tailored_resume = result
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
// Same order and wording as the sheet, for pasting into application forms.
function plainText(value: Resume) {
  const closing = ['Interests', 'Referees']
  const section = (item: Section) => [
    '',
    item.title.toUpperCase(),
    ...(item.entries || []).flatMap((entry) =>
      [
        [entry.heading, entry.dates].filter(Boolean).join(' | '),
        [entry.organization, entry.location].filter(Boolean).join(', '),
        ...(entry.bullets || []).map((bullet) => `• ${bullet}`),
      ].filter(Boolean),
    ),
  ]
  const sections = value.sections || []
  const profile = value.profile_points?.length
    ? value.profile_points.map((point) => `• ${point}`)
    : value.summary
      ? [value.summary]
      : []
  return [
    value.name,
    value.contact?.join(' | '),
    ...(profile.length ? ['', 'CAREER PROFILE', ...profile] : []),
    ...sections.filter((item) => !closing.includes(item.title)).flatMap(section),
    ...(value.skills?.length ? ['', 'TECHNICAL SKILLS', value.skills.join(', ')] : []),
    ...sections.filter((item) => closing.includes(item.title)).flatMap(section),
  ]
    .filter((line) => line !== undefined)
    .join('\n')
    .trim()
}
// The browser's print dialog offers Save as PDF. While it is open only the print copy shows,
// the page title (the PDF's title and file name) is the resume's, and the page margin is zero:
// browsers draw their date, title and URL headers inside that margin, so none fit. The sheet
// supplies its own margins on every page instead.
let finishPrint: (() => void) | null = null
function printResume() {
  if (!resume.value || finishPrint) return
  const title = document.title
  const page = document.createElement('style')
  page.textContent = '@page { margin: 0; }'
  document.head.append(page)
  document.documentElement.classList.add('printing-resume')
  document.title = [resume.value.name, 'Resume'].filter(Boolean).join(' ')
  finishPrint = () => {
    page.remove()
    document.documentElement.classList.remove('printing-resume')
    document.title = title
    window.removeEventListener('afterprint', finishPrint!)
    finishPrint = null
  }
  window.addEventListener('afterprint', finishPrint)
  window.print()
}
onBeforeUnmount(() => finishPrint?.())
async function copy() {
  if (!resume.value) return
  try {
    await navigator.clipboard.writeText(plainText(resume.value))
    copied.value = 'Copied to the clipboard.'
  } catch {
    copied.value = 'Copy was blocked. Select the text in the preview instead.'
  }
}
const generatedOn = computed(() =>
  resume.value?.generated_at
    ? new Date(resume.value.generated_at * 1000).toLocaleString()
    : '',
)
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <section class="panel" aria-labelledby="tailored-heading">
    <div class="flex flex-wrap items-start justify-between gap-4 print:hidden">
      <div class="min-w-0 max-w-prose">
        <p class="eyebrow">For this job</p>
        <h2 id="tailored-heading" class="mt-2 text-2xl font-bold">Tailored resume</h2>
        <p class="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Built only from your resume: Claude picks, orders and rewords what you already have for
          {{ job.company || 'this role' }}. It never adds skills, years or results.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          :class="resume ? 'btn-secondary' : 'btn-primary'"
          :disabled="busy"
          :aria-busy="busy"
          @click="generate"
        >
          <span
            v-if="busy"
            aria-hidden="true"
            class="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent motion-reduce:animate-none"
          />
          {{ busy ? 'Writing…' : resume ? 'Regenerate' : 'Generate tailored resume' }}
        </button>
        <template v-if="resume">
          <button type="button" class="btn-primary" :disabled="busy" @click="printResume">
            Download PDF
          </button>
          <button type="button" class="btn-secondary" :disabled="busy" @click="copy">
            Copy text
          </button>
        </template>
      </div>
    </div>
    <p v-if="busy" role="status" class="mt-4 text-sm text-slate-600 dark:text-slate-300 print:hidden">
      Writing your resume with Claude. This can take up to a minute.
    </p>
    <p
      v-if="error"
      role="alert"
      class="mt-4 rounded-xl bg-rose-50 p-4 text-sm text-rose-900 dark:bg-rose-950 dark:text-rose-200 print:hidden"
    >
      {{ error }}
    </p>
    <p v-if="copied" role="status" class="mt-4 text-sm print:hidden">{{ copied }}</p>
    <p
      v-if="!resume && !busy"
      class="mt-6 rounded-xl border border-dashed border-slate-300 p-5 text-sm dark:border-slate-700 print:hidden"
    >
      No tailored resume yet. Generate one to see it here; it is saved with this job.
    </p>
    <template v-if="resume">
      <div class="mt-6 grid gap-4 md:grid-cols-2 print:hidden">
        <section
          v-if="resume.unverified?.length"
          class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          <h3 class="font-semibold">Check before sending</h3>
          <p class="mt-1">These name a skill or figure not found in your resume. Remove them unless they are true.</p>
          <ul class="mt-2 list-disc space-y-1 pl-5">
            <li v-for="line in resume.unverified" :key="line">{{ line }}</li>
          </ul>
        </section>
        <section
          v-if="resume.gaps?.length"
          class="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm dark:border-slate-700 dark:bg-slate-950"
        >
          <h3 class="font-semibold">Not shown on your resume</h3>
          <p class="mt-1 text-slate-600 dark:text-slate-300">
            The job asks for these and your resume has no evidence. They are left out; cover them in a
            cover letter or interview if you have the experience.
          </p>
          <ul class="mt-2 flex flex-wrap gap-2" aria-label="Requirements not shown on your resume">
            <li
              v-for="gap in resume.gaps"
              :key="gap"
              class="rounded-full bg-white px-3 py-1 text-xs font-medium ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-700"
            >
              {{ gap }}
            </li>
          </ul>
        </section>
      </div>
      <!-- White paper in both themes; the print copy below is what the PDF contains. -->
      <ResumeSheet
        id="tailored-resume-print"
        aria-label="Tailored resume preview"
        :resume="resume"
        class="mx-auto mt-6 max-w-[50rem] rounded-xl border border-slate-200 px-6 py-8 shadow-sm sm:px-12 sm:py-10 dark:border-slate-700"
      />
      <Teleport to="body">
        <div class="resume-print-root"><ResumeSheet :resume="resume" /></div>
      </Teleport>
      <p class="mt-3 text-xs text-slate-600 dark:text-slate-300 print:hidden">
        Generated {{ generatedOn }} with {{ resume.model || 'Claude' }}. Read it through before you
        send it.
      </p>
    </template>
  </section>
</template>

<!-- Printing (Download PDF) shows only the teleported copy, on plain paper with no browser
headers. Scoped to html.printing-resume so printing any other page is unchanged. -->
<style>
.resume-print-root {
  display: none;
}
@media print {
  html.printing-resume body > :not(.resume-print-root) {
    display: none !important;
  }
  html.printing-resume .resume-print-root {
    display: block;
  }
  html.printing-resume .resume-print-root .ats-sheet {
    padding: 14mm 16mm;
    font-size: 10.5pt;
    color: #000;
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
    /* Repeat the margins on every page of a multi-page resume. */
    box-decoration-break: clone;
    -webkit-box-decoration-break: clone;
  }
  html.printing-resume .resume-entry {
    break-inside: avoid;
  }
}
</style>

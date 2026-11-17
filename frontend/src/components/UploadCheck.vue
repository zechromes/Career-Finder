<!-- Show the free upload check: how faithfully the resume was read into the profile. -->
<script setup lang="ts">
import type { components } from '../types/api'
defineProps<{ report: components['schemas']['UploadCheck'] }>()
</script>
<template>
  <section aria-labelledby="upload-check-title" class="space-y-4">
    <h3 id="upload-check-title" class="text-lg font-semibold">Profile check</h3>
    <p>
      Compares the profile with the resume's own text, without another model call. A flag is a
      prompt to look, not proof of an error.
    </p>
    <dl class="grid gap-3 sm:grid-cols-2">
      <div class="panel">
        <dt class="font-semibold">Missing core fields</dt>
        <dd>{{ report.missing_fields.join(', ') || 'None' }}</dd>
      </div>
      <div class="panel">
        <dt class="font-semibold">Resume sections that came back empty</dt>
        <dd>{{ report.empty_sections.join(', ') || 'None' }}</dd>
      </div>
      <div class="panel">
        <dt class="font-semibold">Skills not found in the resume text</dt>
        <dd>{{ report.skills_not_in_resume.join(', ') || 'None' }}</dd>
      </div>
      <div class="panel">
        <dt class="font-semibold">Years of experience</dt>
        <dd>{{ report.years_check || 'Consistent with the dated jobs' }}</dd>
      </div>
    </dl>
    <div class="panel">
      <h4 class="font-semibold">
        Entries with words not in the resume ({{ report.unsupported_entries.length }} of
        {{ report.entries_checked }} checked)
      </h4>
      <p class="text-sm text-slate-600 dark:text-slate-300">
        Under 60% of an entry's words appear in the resume text: it may be reworded, merged or
        invented.
      </p>
      <ul v-if="report.unsupported_entries.length" class="mt-2 space-y-2">
        <li v-for="(item, index) in report.unsupported_entries" :key="index">
          <span class="font-semibold">{{ item.field }}</span> ·
          {{ Math.round(item.found_share * 100) }}% found: {{ item.entry }}
        </li>
      </ul>
      <p v-else class="mt-2">None</p>
    </div>
  </section>
</template>

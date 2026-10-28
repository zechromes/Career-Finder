<!-- Edit structured timeline fields while preserving the stored entry format. -->
<script setup lang="ts">
import { ref } from 'vue'
import { displayTimelineEntry as display, updateTimelineField } from '../utils/profileTimeline'
import {
  AcademicCapIcon,
  BriefcaseIcon,
  PencilSquareIcon,
  PlusIcon,
  TrashIcon,
} from '@heroicons/vue/24/outline'
const props = defineProps<{
  modelValue?: string[]
  label: string
  entryLabel: string
  placeholder: string
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
const editing = ref<number | null>(null)
// Replace one field in the selected stored timeline entry.
function update(index: number, value: string) {
  const entries = [...(props.modelValue || [])]
  entries[index] = value
  emit('update:modelValue', entries)
}
// Append an editable entry to the timeline model.
function add() {
  editing.value = (props.modelValue || []).length
  emit('update:modelValue', [...(props.modelValue || []), ''])
}
// Remove the selected entry from the timeline model.
function remove(index: number) {
  editing.value = null
  emit(
    'update:modelValue',
    (props.modelValue || []).filter((_, position) => position !== index),
  )
}
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <section
    :aria-label="label"
    class="min-w-0 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900 sm:p-5"
  >
    <div
      class="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4 dark:border-slate-800"
    >
      <div class="flex items-center gap-3">
        <span
          class="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
          ><component
            :is="label === 'Education' ? AcademicCapIcon : BriefcaseIcon"
            class="h-5 w-5"
            aria-hidden="true"
        /></span>
        <h3 class="text-base font-semibold">{{ label }}</h3>
      </div>
      <button
        type="button"
        class="btn-secondary text-xs"
        :aria-label="`Add ${entryLabel}`"
        @click="add"
      >
        <PlusIcon class="mr-1 h-4 w-4" aria-hidden="true" />Add entry
      </button>
    </div>
    <ol v-if="modelValue?.length" class="history-list">
      <li v-for="(entry, index) in modelValue" :key="index" class="history-entry">
        <span class="history-dot" aria-hidden="true" />
        <div class="min-w-0 pb-6">
          <div class="mb-2 flex min-h-7 flex-wrap items-center justify-between gap-2">
            <span
              class="text-xs font-semibold tracking-wide text-indigo-700 dark:text-indigo-300"
              >{{ display(entry).date || 'Dates not provided' }}</span
            >
            <div class="flex gap-1">
              <button
                type="button"
                class="rounded-md p-1 text-slate-500 hover:text-indigo-700 dark:text-slate-400 dark:hover:text-indigo-300"
                :aria-label="`Edit ${entryLabel} ${index + 1}`"
                :aria-expanded="editing === index"
                @click="editing = editing === index ? null : index"
              >
                <PencilSquareIcon class="h-4 w-4" aria-hidden="true" />
              </button>
              <button
                type="button"
                class="rounded-md p-1 text-slate-500 hover:text-rose-700 dark:text-slate-400 dark:hover:text-rose-300"
                :aria-label="`Remove ${entryLabel} ${index + 1}`"
                @click="remove(index)"
              >
                <TrashIcon class="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </div>
          <template v-if="editing !== index">
            <h4
              class="break-words text-base font-semibold leading-6 text-slate-900 dark:text-slate-100"
            >
              {{ display(entry).title }}
            </h4>
            <p
              v-if="display(entry).company"
              class="mt-1 break-words text-sm font-medium text-slate-700 dark:text-slate-200"
            >
              {{ display(entry).company }}
            </p>
            <div v-if="label === 'Work history'" class="mt-3">
              <h5 class="text-xs font-semibold text-slate-700 dark:text-slate-200">
                Responsibilities &amp; achievements
              </h5>
              <p
                v-if="display(entry).detail"
                class="mt-1 whitespace-pre-line break-words text-sm leading-6 text-slate-600 dark:text-slate-300"
              >
                {{ display(entry).detail }}
              </p>
              <button
                v-else
                type="button"
                class="mt-1 text-sm text-indigo-700 underline dark:text-indigo-300"
                @click="editing = index"
              >
                Add experience description
              </button>
            </div>
            <p
              v-else-if="display(entry).detail"
              class="mt-1 whitespace-pre-line break-words text-sm leading-6 text-slate-600 dark:text-slate-300"
            >
              {{ display(entry).detail }}
            </p>
          </template>
          <div v-else>
            <div v-if="label === 'Work history'" class="space-y-3">
              <label
                v-for="field in ['title', 'company', 'date'] as const"
                :key="field"
                class="block"
              >
                <span class="field-label">{{
                  field === 'title' ? 'Role' : field === 'company' ? 'Company' : 'Dates'
                }}</span>
                <input
                  :value="display(entry)[field] === 'New entry' ? '' : display(entry)[field]"
                  class="field"
                  @input="
                    update(
                      index,
                      updateTimelineField(entry, field, ($event.target as HTMLInputElement).value),
                    )
                  "
                />
              </label>
              <label class="block"
                ><span class="field-label">Experience description</span>
                <textarea
                  :value="display(entry).detail"
                  rows="4"
                  class="field block resize-y text-sm leading-6"
                  placeholder="Describe your responsibilities, projects and achievements in this role."
                  @input="
                    update(
                      index,
                      updateTimelineField(
                        entry,
                        'detail',
                        ($event.target as HTMLTextAreaElement).value,
                      ),
                    )
                  "
                />
              </label>
            </div>
            <textarea
              v-else
              :value="entry"
              :aria-label="`${entryLabel} ${index + 1}`"
              :placeholder="placeholder"
              rows="3"
              class="field block resize-y text-sm leading-6"
              :class="{ 'border-amber-500': !entry.trim() }"
              @input="update(index, ($event.target as HTMLTextAreaElement).value)"
            />
            <p class="mt-2 text-xs text-slate-500 dark:text-slate-400">
              {{ label === 'Education' ? 'Qualification | Institution' : 'Role | Company' }} |
              January 2022 – March 2024 | Details. Use only dates provided in your resume.
            </p>
            <button type="button" class="btn-secondary mt-2 text-xs" @click="editing = null">
              Done editing
            </button>
          </div>
        </div>
      </li>
    </ol>
    <p
      v-else
      class="rounded-lg border border-dashed border-amber-500 p-4 text-sm text-slate-600 dark:text-slate-300"
    >
      No entries found in your resume. Add an entry to complete your {{ label.toLowerCase() }}.
    </p>
  </section>
</template>
<!-- Component presentation and interaction styling. -->
<style scoped>
.history-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.history-entry {
  position: relative;
  display: grid;
  grid-template-columns: 1rem minmax(0, 1fr);
  gap: 1rem;
}
.history-entry:not(:last-child)::before {
  content: '';
  position: absolute;
  left: calc(0.5rem - 1px);
  top: 1rem;
  bottom: -0.75rem;
  width: 2px;
  background: #e2e8f0;
}
.history-dot {
  position: relative;
  z-index: 1;
  margin-top: 0.5rem;
  width: 1rem;
  height: 1rem;
  border: 3px solid #818cf8;
  border-radius: 50%;
  background: white;
}
.history-entry:last-child > div {
  padding-bottom: 0;
}
.dark .history-dot {
  background: #0f172a;
  border-color: #a5b4fc;
}
.dark .history-entry:not(:last-child)::before {
  background: #334155;
}
</style>

<!-- Edit a list of values with suggestions and keyboard selection. -->
<script setup>
import { computed, ref, useId, watch } from 'vue'
import { XMarkIcon } from '@heroicons/vue/24/outline'

const values = defineModel({ type: Array, default: () => [] })
const draft = ref('')
const listId = useId()
const active = ref(-1)
const dismissed = ref(false)
const props = defineProps({
  label: { type: String, required: true },
  placeholder: { type: String, default: 'Type and press Enter' },
  autocomplete: { type: Boolean, default: false },
  suggestions: { type: Array, default: () => [] },
})
const emit = defineEmits(['suggest'])

const matchingSuggestions = computed(() => {
  const search = draft.value.trim().toLowerCase()
  if (!search || dismissed.value) return []
  return props.suggestions
    .filter((suggestion) => {
      const value = suggestion.value || suggestion
      return value.toLowerCase().includes(search) && !values.value.includes(value)
    })
    .slice(0, 5)
})

watch(draft, () => {
  active.value = -1
  dismissed.value = false
})
watch(
  () => props.suggestions,
  () => {
    active.value = -1
  },
)

// Commit a nonempty draft value without adding a duplicate chip.
function addDraft() {
  const value = draft.value.trim().replace(/,$/, '')
  if (value && !values.value.includes(value)) values.value.push(value)
  draft.value = ''
  emit('suggest', '')
}

// Remove one chip while retaining the order of the remaining selections.
function removeValue(index) {
  values.value.splice(index, 1)
}

// Commit a suggestion and reset the input’s active selection.
function selectSuggestion(suggestion) {
  const value = suggestion.value || suggestion
  if (!values.value.includes(value)) values.value.push(value)
  draft.value = ''
  emit('suggest', '')
}

// Implement keyboard selection and dismissal for the suggestion list.
function handleKeydown(event) {
  if (event.key === 'Escape') {
    dismissed.value = true
    active.value = -1
    return
  }
  if (['ArrowDown', 'ArrowUp'].includes(event.key) && matchingSuggestions.value.length) {
    event.preventDefault()
    active.value =
      (active.value + (event.key === 'ArrowDown' ? 1 : -1) + matchingSuggestions.value.length) %
      matchingSuggestions.value.length
    return
  }
  if (event.key === 'Enter' && active.value >= 0 && matchingSuggestions.value[active.value]) {
    event.preventDefault()
    selectSuggestion(matchingSuggestions.value[active.value])
    return
  }
  if (event.key === 'Enter' || (event.key === ',' && !props.autocomplete)) {
    event.preventDefault()
    addDraft()
  }
  if (event.key === 'Backspace' && !draft.value && values.value.length) {
    removeValue(values.value.length - 1)
  }
}
</script>

<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <div>
    <span class="field-label">{{ label }}</span>
    <div
      class="min-h-12 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 focus-within:border-indigo-600 focus-within:ring-2 focus-within:ring-indigo-100"
    >
      <div class="flex flex-wrap items-center gap-2">
        <span
          v-for="(value, index) in values"
          :key="value"
          class="inline-flex items-center gap-1 rounded-full bg-indigo-50 dark:bg-indigo-950 px-3 py-1.5 font-mono text-xs font-semibold text-indigo-700 dark:text-indigo-300"
        >
          {{ value }}
          <button
            type="button"
            class="rounded-full hover:text-coral"
            :aria-label="`Remove ${value}`"
            @click="removeValue(index)"
          >
            <XMarkIcon class="h-3.5 w-3.5" />
          </button>
        </span>
        <div class="relative min-w-32 flex-1">
          <input
            :role="autocomplete ? 'combobox' : undefined"
            :aria-autocomplete="autocomplete ? 'list' : undefined"
            :aria-expanded="autocomplete ? !!matchingSuggestions.length : undefined"
            :aria-controls="autocomplete ? listId : undefined"
            :aria-activedescendant="
              active >= 0 && matchingSuggestions.length ? `${listId}-${active}` : undefined
            "
            :aria-label="label"
            v-model="draft"
            class="w-full border-0 bg-transparent px-1 py-1 text-sm outline-none"
            :placeholder="values.length ? 'Add another…' : placeholder"
            @input="emit('suggest', draft)"
            @blur="addDraft"
            @keydown="handleKeydown"
          />
          <div
            v-if="matchingSuggestions.length"
            :id="listId"
            role="listbox"
            :aria-label="`${label} suggestions`"
            class="absolute left-0 right-0 top-10 z-20 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-1 text-left shadow-lg"
          >
            <button
              v-for="(suggestion, index) in matchingSuggestions"
              :id="`${listId}-${index}`"
              role="option"
              :aria-selected="active === index"
              :class="active === index ? 'bg-indigo-50 dark:bg-indigo-950' : ''"
              tabindex="-1"
              :key="suggestion.value || suggestion"
              type="button"
              class="block w-full rounded-md px-3 py-2 text-left text-xs hover:bg-indigo-50 dark:hover:bg-indigo-950"
              @mousedown.prevent
              @click="selectSuggestion(suggestion)"
            >
              {{ suggestion.label || suggestion.value || suggestion }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <p class="mt-1 text-[11px] text-slate-600 dark:text-slate-300">
      {{
        autocomplete
          ? 'Type a city or country. Use arrow keys to choose, then Enter. Custom locations are also accepted.'
          : 'Press Enter or comma to add another.'
      }}
    </p>
  </div>
</template>

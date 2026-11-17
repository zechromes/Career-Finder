<!-- Segmented tab strip with roving focus; pass idPrefix when panels use `${idPrefix}-panel-${value}` ids. -->
<script setup lang="ts">
const props = defineProps<{
  tabs: readonly { value: string; label: string }[]
  modelValue: string
  label: string
  idPrefix?: string
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const tabId = (value: string) => (props.idPrefix ? `${props.idPrefix}-tab-${value}` : undefined)

// Arrow, Home and End keys move selection and focus, per the ARIA tabs pattern.
function navigate(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const count = props.tabs.length
  const index = props.tabs.findIndex((tab) => tab.value === props.modelValue)
  const next =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? count - 1
        : (index + (event.key === 'ArrowRight' ? 1 : -1) + count) % count
  emit('update:modelValue', props.tabs[next].value)
  const buttons = (event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('[role="tab"]')
  buttons[next]?.focus()
}
</script>

<template>
  <div
    role="tablist"
    :aria-label="label"
    class="inline-flex max-w-full flex-wrap gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800"
    @keydown="navigate"
  >
    <button
      v-for="tab in tabs"
      :id="tabId(tab.value)"
      :key="tab.value"
      type="button"
      role="tab"
      :aria-selected="modelValue === tab.value"
      :aria-controls="idPrefix ? `${idPrefix}-panel-${tab.value}` : undefined"
      :tabindex="modelValue === tab.value ? 0 : -1"
      :disabled="disabled"
      class="min-h-11 rounded-lg px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50"
      :class="
        modelValue === tab.value
          ? 'bg-white text-indigo-700 shadow-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:text-indigo-300 dark:ring-slate-700'
          : 'text-slate-600 hover:bg-white/60 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-900/60 dark:hover:text-white'
      "
      @click="emit('update:modelValue', tab.value)"
    >
      {{ tab.label }}
    </button>
  </div>
</template>

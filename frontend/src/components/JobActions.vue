<!-- Manage browser-local job flags and a keyboard-accessible floating actions menu. -->
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import {
  EllipsisHorizontalIcon,
  BookmarkIcon,
  LinkIcon,
  EyeSlashIcon,
  CheckCircleIcon,
} from '@heroicons/vue/24/outline'
import type { Job } from '../types/domain'
import { useJobsStore } from '../stores/jobs'
import type { JobAction } from '../stores/jobs'
import { useSnackbarStore } from '../stores/snackbar'
const props = defineProps<{ job: Job; inline?: boolean }>()
const store = useJobsStore()
const snackbar = useSnackbarStore()
function toggleAction(action: JobAction) {
  if (action === 'dismissed' && !flags.value.dismissed) {
    close(true)
    store.dismissTarget = props.job
    return
  }
  store.toggle(props.job, action)
  const messages = {
    saved: ['Removed from saved jobs.', 'Saved.'],
    dismissed: ['Job restored.', 'Job dismissed.'],
    applied: ['Applied status removed.', 'Job marked as applied.'],
  }
  snackbar.show(store.storageError || messages[action][flags.value[action] ? 1 : 0]!)
}
const flags = computed(() => store.flags(props.job))
const id = useId()
const open = ref(false)
let pointerInside = false
let openedScroll = { x: 0, y: 0 }
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const position = ref({ top: '0px', left: '0px' })
const message = ref('')
const failed = ref(false)
const url = computed(() => {
  try {
    const value = new URL(props.job.apply_url || '')
    return ['https:', 'http:'].includes(value.protocol) ? value.href : ''
  } catch {
    return ''
  }
})
const actions = [
  { key: 'saved', label: 'Save', active: 'Saved', icon: BookmarkIcon },
  { key: 'dismissed', label: 'Dismiss', active: 'Dismissed', icon: EyeSlashIcon },
  { key: 'applied', label: 'Mark as applied', active: 'Applied', icon: CheckCircleIcon },
] as const
// Open or close the menu and position it relative to the trigger.
async function toggle() {
  open.value = !open.value
  if (open.value) {
    openedScroll = { x: window.scrollX, y: window.scrollY }
    const bounds = trigger.value!.getBoundingClientRect()
    position.value = {
      top: `${Math.max(8, Math.min(bounds.bottom + 6, window.innerHeight - 340))}px`,
      left: `${Math.max(8, Math.min(bounds.right - 240, window.innerWidth - 248))}px`,
    }
    await nextTick()
    root.value
      ?.querySelector<HTMLButtonElement>('[data-actions] button')
      ?.focus({ preventScroll: true })
  }
}
// Dismiss the floating menu and optionally restore focus to its trigger.
function close(restore = false) {
  open.value = false
  if (restore) trigger.value?.focus()
}
// Close the menu when a pointer interaction occurs outside its root.
function outside(event: Event) {
  pointerInside = !!root.value?.contains(event.target as Node)
  if (!pointerInside) close()
}
function releasePointer() {
  pointerInside = false
}
function leaveFocus(event: FocusEvent) {
  // A pointer click may blur the focused button without focusing its target.
  // Keep the menu mounted until that click reaches the chosen action.
  if (pointerInside) return
  if (!root.value?.contains(event.relatedTarget as Node)) close()
}
// Dismiss the floating menu when its screen position may have changed.
function scroll(event: Event) {
  // A scroll queued while bringing the trigger into view may arrive after opening.
  if (
    event.type === 'scroll' &&
    window.scrollX === openedScroll.x &&
    window.scrollY === openedScroll.y
  )
    return
  close()
}
// Copy the application URL and announce clipboard success or failure.
async function copyLink() {
  try {
    await navigator.clipboard.writeText(url.value)
    message.value = ''
    failed.value = false
    snackbar.show('Link copied to clipboard.')
  } catch {
    failed.value = true
    message.value = 'Copy this link manually:'
    snackbar.show('Could not copy the link. Use the manual copy field.')
  }
}
onMounted(() => {
  document.addEventListener('pointerdown', outside)
  document.addEventListener('pointerup', releasePointer)
  document.addEventListener('pointercancel', releasePointer)
  window.addEventListener('resize', scroll)
  window.addEventListener('scroll', scroll)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', outside)
  document.removeEventListener('pointerup', releasePointer)
  document.removeEventListener('pointercancel', releasePointer)
  window.removeEventListener('resize', scroll)
  window.removeEventListener('scroll', scroll)
})
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <div ref="root" class="shrink-0" @keydown.esc.stop.prevent="close(true)" @focusout="leaveFocus">
    <div v-if="inline" role="group" aria-label="Job actions" class="flex flex-wrap gap-2">
      <button
        v-for="action in actions"
        :key="action.key"
        type="button"
        class="btn-secondary h-11 w-11 !p-2"
        :class="
          flags[action.key]
            ? '!border-indigo-500 !bg-indigo-50 !text-indigo-800 dark:!bg-indigo-950 dark:!text-indigo-200'
            : ''
        "
        :aria-pressed="!!flags[action.key]"
        :aria-label="`${flags[action.key] ? action.active : action.label}: ${job.title} at ${job.company}`"
        :title="flags[action.key] ? action.active : action.label"
        @click="toggleAction(action.key)"
      >
        <component :is="action.icon" class="h-5 w-5" aria-hidden="true" />
      </button>
      <button
        type="button"
        class="btn-secondary h-11 w-11 !p-2"
        :disabled="!url"
        :aria-label="`Copy link for ${job.title}`"
        title="Copy link"
        @click="copyLink"
      >
        <LinkIcon class="h-5 w-5" aria-hidden="true" />
      </button>
    </div>
    <p v-if="inline && message" role="status" class="text-sm">{{ message }}</p>
    <input
      v-if="inline && failed"
      :value="url"
      readonly
      aria-label="Job link to copy manually"
      class="field"
      @focus="($event.target as HTMLInputElement).select()"
    />
    <button
      v-if="!inline"
      ref="trigger"
      type="button"
      class="btn-secondary h-11 w-11 !p-2"
      :aria-label="`Actions for ${job.title} at ${job.company}`"
      :aria-expanded="open"
      :aria-controls="id"
      @click="toggle"
    >
      <EllipsisHorizontalIcon class="h-6 w-6" aria-hidden="true" />
    </button>
    <div
      v-if="open"
      :id="id"
      data-actions
      :style="position"
      class="fixed z-50 w-60 rounded-xl border border-slate-200 bg-white p-2 shadow-xl dark:border-slate-600 dark:bg-slate-900"
      role="group"
      :aria-label="`Job actions for ${job.title}`"
    >
      <button
        type="button"
        class="action"
        :aria-pressed="!!flags.saved"
        :aria-label="`${flags.saved ? 'Saved' : 'Save'}: ${job.title} at ${job.company}`"
        @click="toggleAction('saved')"
      >
        <BookmarkIcon class="h-5 w-5" aria-hidden="true" />{{ flags.saved ? 'Saved' : 'Save' }}
      </button>
      <button
        type="button"
        class="action"
        :disabled="!url"
        :aria-label="`Copy link for ${job.title}`"
        @click="copyLink"
      >
        <LinkIcon class="h-5 w-5" aria-hidden="true" />Copy link
      </button>
      <button
        v-for="action in actions.slice(1)"
        :key="action.key"
        type="button"
        class="action"
        :aria-label="`${flags[action.key] ? action.active : action.label}: ${job.title} at ${job.company}`"
        :aria-pressed="!!flags[action.key]"
        @click="toggleAction(action.key)"
      >
        <component :is="action.icon" class="h-5 w-5" aria-hidden="true" />{{
          flags[action.key] ? action.active : action.label
        }}
      </button>
      <p v-if="message" role="status" class="px-3 py-2 text-xs text-slate-700 dark:text-slate-200">
        {{ message }}
      </p>
      <input
        v-if="failed"
        :value="url"
        readonly
        aria-label="Job link to copy manually"
        class="field"
        @focus="($event.target as HTMLInputElement).select()"
      />
    </div>
  </div>
</template>
<!-- Component presentation and interaction styling. -->
<style scoped>
.action {
  display: flex;
  width: 100%;
  min-height: 44px;
  align-items: center;
  gap: 0.75rem;
  border-radius: 0.5rem;
  padding: 0.625rem 0.75rem;
  font-size: 0.875rem;
  text-align: left;
}
.action:hover,
.action:focus-visible,
.action[aria-pressed='true'] {
  background: #eef2ff;
  color: #4338ca;
}
.dark .action:hover,
.dark .action:focus-visible,
.dark .action[aria-pressed='true'] {
  background: #312e81;
  color: #e0e7ff;
}
.action:disabled {
  opacity: 0.5;
}
</style>

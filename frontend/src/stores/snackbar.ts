import { defineStore } from 'pinia'
import { onScopeDispose, ref } from 'vue'

export const useSnackbarStore = defineStore('snackbar', () => {
  const message = ref('')
  const revision = ref(0)
  let timer: ReturnType<typeof setTimeout> | undefined

  function dismiss() {
    clearTimeout(timer)
    message.value = ''
  }

  function show(text: string) {
    dismiss()
    revision.value++
    message.value = text
    timer = setTimeout(dismiss, 5000)
  }

  onScopeDispose(dismiss)
  return { message, revision, show, dismiss }
})

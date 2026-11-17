<!-- Save provider API keys; each key is verified with its provider before it is stored. -->
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api } from '../stores/pipeline'
import type { components } from '../types/api'

type KeyStatus = components['schemas']['ApiKeyStatus']
const keys = ref<KeyStatus[]>([])
const drafts = reactive<Record<string, string>>({})
const busy = ref('')
const messages = reactive<Record<string, { text: string; ok: boolean }>>({})
const loadError = ref('')

onMounted(async () => {
  try {
    keys.value = await api<KeyStatus[]>('/api/settings/keys')
  } catch (cause) {
    loadError.value = (cause as Error).message
  }
})

async function send(provider: string, method: 'PUT' | 'DELETE') {
  busy.value = provider
  delete messages[provider]
  try {
    keys.value = await api<KeyStatus[]>(`/api/settings/keys/${provider}`, {
      method,
      ...(method === 'PUT' && {
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: drafts[provider] || '' }),
      }),
    })
    drafts[provider] = ''
    messages[provider] = {
      text: method === 'PUT' ? 'Key verified and saved.' : 'Saved key removed.',
      ok: true,
    }
  } catch (cause) {
    messages[provider] = { text: (cause as Error).message, ok: false }
  } finally {
    busy.value = ''
  }
}

function sourceText(item: KeyStatus) {
  if (item.source === 'settings') return `Saved here ${item.hint}`
  if (item.source === 'env') return `From .env ${item.hint}`
  return 'Not set'
}
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-6">
    <header class="space-y-2">
      <h1 class="text-3xl font-bold">Settings</h1>
      <p class="text-slate-600 dark:text-slate-300">
        API keys for the model providers. Each key is checked with its provider before it is saved,
        and saved keys take priority over <code>.env</code>. Keys stay on this computer.
      </p>
    </header>
    <p v-if="loadError" role="alert" class="panel text-rose-800 dark:text-rose-200">
      {{ loadError }}
    </p>
    <form
      v-for="item in keys"
      :key="item.provider"
      class="panel space-y-4"
      :aria-labelledby="`key-${item.provider}-title`"
      @submit.prevent="send(item.provider, 'PUT')"
    >
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h2 :id="`key-${item.provider}-title`" class="text-xl font-bold">{{ item.label }}</h2>
        <span
          class="chip"
          :class="{
            'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300': !item.source,
          }"
        >
          {{ sourceText(item) }}
        </span>
      </div>
      <label :for="`key-${item.provider}`" class="field-label">API key</label>
      <div class="flex flex-wrap gap-3">
        <input
          :id="`key-${item.provider}`"
          v-model="drafts[item.provider]"
          type="password"
          autocomplete="off"
          spellcheck="false"
          class="field min-w-0 flex-1"
          :placeholder="item.source ? 'Enter a new key to replace it' : 'Paste your key'"
        />
        <button
          class="btn-primary"
          :disabled="busy !== '' || !drafts[item.provider]?.trim()"
          :aria-busy="busy === item.provider"
        >
          {{ busy === item.provider ? 'Verifying…' : 'Verify & save' }}
        </button>
        <button
          v-if="item.source === 'settings'"
          type="button"
          class="btn-secondary"
          :disabled="busy !== ''"
          @click="send(item.provider, 'DELETE')"
        >
          Remove
        </button>
      </div>
      <p
        v-if="messages[item.provider]"
        role="status"
        class="text-sm"
        :class="
          messages[item.provider].ok
            ? 'text-emerald-700 dark:text-emerald-300'
            : 'text-rose-700 dark:text-rose-300'
        "
      >
        {{ messages[item.provider].text }}
      </p>
    </form>
  </div>
</template>

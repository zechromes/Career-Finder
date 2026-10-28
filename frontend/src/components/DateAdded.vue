<!-- Format a recorded timestamp in local time; missing historical dates remain unknown. -->
<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ value?: string | null }>()
// Historical jobs may have no timestamp; do not substitute the current date.
const date = computed(() => (props.value ? new Date(props.value) : null))
const valid = computed(() => date.value && !Number.isNaN(date.value.getTime()))
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <time v-if="valid" :datetime="value!">{{
    date!.toLocaleString('en-AU', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }}</time>
  <span v-else>Not recorded</span>
</template>

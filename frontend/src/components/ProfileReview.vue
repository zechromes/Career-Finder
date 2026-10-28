<!-- Validate the editable profile or search-only preferences before emitting confirmation. -->
<script setup lang="ts">
import { ref } from 'vue'
import { useProfileStore } from '../stores/profile'
import type { ModelOption } from '../types/domain'
import LocationInput from './LocationInput.vue'
import ChipInput from './ChipInput.vue'
import ProfileTimeline from './ProfileTimeline.vue'
const props = defineProps<{
  models: ModelOption[]
  disabled?: boolean
  saveOnly?: boolean
  searchOnly?: boolean
}>()
const emit = defineEmits<{ confirm: [] }>()
const store = useProfileStore()
const validation = ref('')
// Validate required search choices before emitting the confirmed draft.
function confirm() {
  validation.value = ''
  if (
    !props.saveOnly &&
    (!store.preferences.queries?.length || !store.preferences.platforms?.length)
  ) {
    validation.value = 'Add a target role and at least one job board.'
    return
  }
  emit('confirm')
}
</script>
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <form class="panel" @submit.prevent="confirm">
    <h2 class="text-2xl font-bold">{{ searchOnly ? 'Find more jobs' : 'Review your profile' }}</h2>
    <p v-if="searchOnly" class="mt-2 text-sm text-slate-600 dark:text-slate-300">
      Keep your target roles to search again, or add different roles. Existing jobs and saved
      actions stay in your results; duplicate postings are skipped. Starting a search makes new
      job-board and evaluation requests.
    </p>
    <p v-else class="mt-2 text-sm text-slate-600 dark:text-slate-300">
      Correct anything the extractor missed. Amber fields have no extracted value; leave unknown
      details empty.
    </p>
    <fieldset :disabled="disabled" class="mt-6 space-y-5">
      <template v-if="!searchOnly">
        <div class="grid gap-5 md:grid-cols-3">
          <label
            ><span class="field-label">Name</span
            ><input
              v-model="store.draft.name"
              class="field"
              :class="{ 'border-amber-500': !store.draft.name }"
              placeholder="Not found in resume"
          /></label>
          <label
            ><span class="field-label">Years of professional experience</span
            ><input
              :value="store.draft.years_of_experience ?? ''"
              @input="
                store.draft.years_of_experience =
                  ($event.target as HTMLInputElement).value === ''
                    ? null
                    : Number(($event.target as HTMLInputElement).value)
              "
              type="number"
              min="0"
              max="80"
              step="0.1"
              class="field"
              :class="{ 'border-amber-500': store.draft.years_of_experience == null }"
              placeholder="Unknown"
          /></label>
          <label
            ><span class="field-label">Career level</span
            ><select v-model="store.draft.career_level" class="field">
              <option
                v-for="value in ['unknown', 'graduate', 'entry', 'junior', 'mid', 'senior']"
                :key="value"
              >
                {{ value }}
              </option>
            </select></label
          >
        </div>
        <label class="block"
          ><span class="field-label">Profile summary</span
          ><textarea
            v-model="store.draft.profile"
            rows="3"
            class="field"
            :class="{ 'border-amber-500': !store.draft.profile }"
          />
        </label>
        <div class="grid gap-5 sm:grid-cols-2">
          <div
            :class="{ 'rounded-xl ring-1 ring-amber-500 p-2': !store.draft.tech_skills?.length }"
          >
            <ChipInput v-model="store.draft.tech_skills" label="Technical skills" />
          </div>
          <ChipInput v-model="store.draft.soft_skills" label="Soft skills" />
        </div>
        <div class="grid items-start gap-6 lg:grid-cols-2">
          <ProfileTimeline
            v-model="store.draft.work_history"
            label="Work history"
            entry-label="Role"
            placeholder="Role, company, dates and responsibilities"
          />
          <ProfileTimeline
            v-model="store.draft.education"
            label="Education"
            entry-label="Education entry"
            placeholder="Qualification, institution and dates"
          />
        </div>
      </template>
      <h2 class="border-t pt-5 text-lg font-semibold">Search preferences</h2>
      <div class="grid gap-5 sm:grid-cols-2">
        <ChipInput
          v-model="store.preferences.queries"
          label="Target roles"
          placeholder="Add a role"
        />
        <div><LocationInput v-model="store.preferences.locations" /></div>
        <label
          ><span class="field-label">Work arrangement</span
          ><select v-model="store.preferences.work_type" class="field">
            <option value="any">Any arrangement</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="on-site">On-site</option>
          </select></label
        >
        <label
          ><span class="field-label">Seniority filter</span
          ><select v-model="store.preferences.seniority" class="field">
            <option value="auto">Prioritize my experience (automatic)</option>
            <option value="any">All levels</option>
            <option v-for="value in ['graduate', 'entry', 'junior', 'mid', 'senior']" :key="value">
              {{ value }}
            </option></select
          ><span class="mt-1 block text-xs text-slate-600 dark:text-slate-300"
            >Automatic prioritizes suitable-level titles for early-career profiles without excluding
            other levels. All levels keeps relevance order; a specific level searches titles
            containing that level.</span
          ></label
        >
        <label
          ><span class="field-label">Posted within</span
          ><select v-model="store.preferences.posted_days_old" class="field">
            <option :value="1">Today</option>
            <option :value="7">Last week</option>
            <option :value="30">Last month</option>
            <option :value="0">Any time</option>
          </select></label
        >
        <label
          ><span class="field-label">Semantic shortlist size</span
          ><select v-model="store.preferences.top_k" class="field">
            <option :value="15">Top 15 matches</option>
            <option :value="50">Top 50 matches</option>
            <option :value="100">Top 100 matches</option>
            <option :value="0">All retrieved jobs</option>
          </select></label
        >
        <ChipInput v-model="store.preferences.exclusions" label="Exclude title or company terms" />
        <fieldset>
          <legend class="field-label">Job boards</legend>
          <label
            v-for="board in ['linkedin', 'indeed', 'glassdoor', 'seek']"
            :key="board"
            class="mr-4 inline-flex gap-2 text-sm capitalize"
            ><input v-model="store.preferences.platforms" type="checkbox" :value="board" />{{
              board
            }}</label
          >
        </fieldset>
        <div class="sm:col-span-2 rounded-xl bg-indigo-50 p-4 dark:bg-indigo-950">
          <p class="field-label">Automatic model comparison</p>
          <p class="text-sm">Every shortlisted job is evaluated by Claude, GPT and Gemini.</p>
          <p
            v-for="model in props.models"
            :key="model.value"
            class="mt-1 text-xs text-slate-600 dark:text-slate-300"
          >
            {{ model.label }}
          </p>
        </div>
      </div>
      <p class="text-xs text-slate-600 dark:text-slate-300">
        Specific work arrangements require evidence in the posting; unknown arrangements are
        omitted. All three evaluation providers run automatically, independently of the profile
        model.
      </p>
      <p v-if="validation" role="alert" class="text-sm text-rose-700 dark:text-rose-300">
        {{ validation }}
      </p>
      <div class="flex flex-wrap gap-3">
        <button class="btn-primary" :disabled="disabled">
          {{
            saveOnly
              ? 'Save changes'
              : searchOnly
                ? 'Search for more jobs'
                : 'Confirm and find jobs'
          }}
        </button>
      </div>
    </fieldset>
  </form>
</template>

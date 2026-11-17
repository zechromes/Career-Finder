// Keep editable candidate and preference drafts separate from server snapshots.
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Profile, Preferences, Run } from '../types/domain'
export const useProfileStore = defineStore('profile', () => {
  const draft = ref<Profile>({
    name: '',
    headline: '',
    profile: '',
    tech_skills: [],
    soft_skills: [],
    years_of_experience: null,
    preferred_domains: [],
    work_history: [],
    education: [],
    section_headings: [],
    sections: [],
    target_roles_reason: '',
    source_text: '',
    career_level: 'unknown',
    experience_evidence: [],
  })
  const preferences = ref<Preferences>({
    queries: [],
    locations: [],
    platforms: ['linkedin', 'indeed'],
    work_type: 'any',
    seniority: 'auto',
    exclusions: [],
    posted_days_old: 7,
    evaluation_model: 'claude',
    top_k: -1,
  })
  // Initialize editable drafts from saved preferences or legacy search inputs.
  function load(
    run: { profile?: Profile | null; preferences?: unknown; search_inputs?: unknown },
    defaultModel = 'claude',
  ) {
    if (run.profile) draft.value = { ...draft.value, ...JSON.parse(JSON.stringify(run.profile)) }
    const saved = (run.preferences || run.search_inputs || {}) as Partial<Preferences>
    preferences.value = {
      queries: [...(draft.value.preferred_domains || [])],
      locations: [],
      platforms: ['linkedin', 'indeed'],
      work_type: 'any',
      seniority: 'auto',
      exclusions: [],
      posted_days_old: 7,
      top_k: -1,
      evaluation_model: defaultModel as Preferences['evaluation_model'],
      ...saved,
      ...(saved.platforms
        ? {
            platforms: saved.platforms.filter((site) =>
              ['linkedin', 'indeed', 'seek', 'google', 'adzuna'].includes(site),
            ),
          }
        : {}),
    }
  }
  return { draft, preferences, load }
})

// Check the Find more note: new search parts are named; a recent repeat is flagged.
import { beforeEach, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ProfileReview from '../src/components/ProfileReview.vue'
import { useProfileStore } from '../src/stores/profile'
beforeEach(() => setActivePinia(createPinia()))
const search = (minutesAgo: number) => ({
  at: new Date(Date.now() - minutesAgo * 60000).toISOString(),
  platforms: ['linkedin'],
  queries: ['Data Engineer'],
  locations: ['Sydney'],
})
function render(previousSearches: ReturnType<typeof search>[]) {
  return mount(ProfileReview, {
    props: { models: [], searchOnly: true, previousSearches },
    global: { stubs: { LocationInput: true, ChipInput: true, ProfileTimeline: true } },
  })
}
it('names boards, roles and locations not searched before', () => {
  Object.assign(useProfileStore().preferences, {
    platforms: ['linkedin', 'seek'],
    queries: ['data engineer'],
    locations: ['Sydney', 'Melbourne'],
  })
  expect(render([search(2)]).text()).toContain('New this time: Seek, Melbourne.')
})
it('flags a repeat of a search made within the hour, but not an older one', () => {
  Object.assign(useProfileStore().preferences, {
    platforms: ['linkedin'],
    queries: ['Data Engineer'],
    locations: ['Sydney'],
  })
  expect(render([search(2)]).text()).toContain('2 minutes ago; results may mostly repeat')
  expect(render([search(90)]).text()).not.toContain('may mostly repeat')
})

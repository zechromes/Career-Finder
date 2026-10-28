import { beforeEach, expect, test } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useProfileStore } from '../src/stores/profile'

beforeEach(() => setActivePinia(createPinia()))

test('older profiles keep supported sources and remove retired feeds', () => {
  const store = useProfileStore()
  store.load({ preferences: { platforms: ['greenhouse', 'indeed', 'lever'] } })
  expect(store.preferences.platforms).toEqual(['indeed'])
})

test('feed-only saved preferences require the user to choose a board', () => {
  const store = useProfileStore()
  store.load({ preferences: { platforms: ['greenhouse', 'lever'] } })
  expect(store.preferences.platforms).toEqual([])
})

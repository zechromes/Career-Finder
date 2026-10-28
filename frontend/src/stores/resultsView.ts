// Keep each workspace's results position while navigating to details and back.
import { defineStore } from 'pinia'
import { reactive } from 'vue'

export function newResultsView() {
  return {
    search: '',
    sort: 'match',
    location: '',
    source: '',
    workType: '',
    minScore: 0,
    actionFilter: 'all',
    page: 1,
  }
}
export type ResultsView = ReturnType<typeof newResultsView>
export const useResultsViewStore = defineStore('results-view', () => {
  const workspaces = reactive<Record<string, ResultsView>>({})
  function forRun(id: string) {
    if (!workspaces[id]) workspaces[id] = newResultsView()
    return workspaces[id]
  }
  return { workspaces, forRun }
})

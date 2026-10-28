// Initialize the application and its shared plugins before mounting the interface.
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import './style.css'
// Enable optional mocks before mounting the Vue application.
async function start() {
  if (import.meta.env.VITE_MOCK_API === 'true') {
    const { worker } = await import('./mocks/browser')
    await worker.start({ onUnhandledRequest: 'bypass' })
  }
  // Fresh opens start at home; browser refreshes preserve the current route.
  const app = createApp(App).use(createPinia()).use(router)
  await router.isReady()
  const navigation = performance.getEntriesByType('navigation')[0] as
    | PerformanceNavigationTiming
    | undefined
  if (
    navigation?.type !== 'reload' &&
    !['/', '/eval'].includes(router.currentRoute.value.path) &&
    !router.currentRoute.value.path.startsWith('/eval/datasets/')
  ) {
    await router.replace('/')
  }
  app.mount('#app')
}
void start()

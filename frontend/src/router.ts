// Define routes for navigation within the application; fresh opens start at home and refreshes retain their route.
import { createRouter, createWebHistory } from 'vue-router'
import UploadView from './views/UploadView.vue'
import RunView from './views/RunView.vue'
import JobDetailView from './views/JobDetailView.vue'
import ProfilesView from './views/ProfilesView.vue'
import EvalView from './views/EvalView.vue'
import PrivacyView from './views/PrivacyView.vue'
import SettingsView from './views/SettingsView.vue'
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: UploadView },
    { path: '/profiles', component: ProfilesView },
    { path: '/run/:runId', component: RunView },
    { path: '/run/:runId/results', component: RunView },
    { path: '/run/:runId/job', component: JobDetailView },
    { path: '/privacy', component: PrivacyView },
    { path: '/eval', component: EvalView },
    { path: '/settings', component: SettingsView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

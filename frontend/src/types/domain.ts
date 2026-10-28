// Alias generated API schemas so application types stay aligned with the backend.
import type { components } from './api'
export type Profile = components['schemas']['ResumeProfile']
export type Preferences = components['schemas']['Preferences']
export type Job = components['schemas']['JobResult']
export type Run = components['schemas']['RunSnapshot']
export type ModelOption = components['schemas']['ModelOption']

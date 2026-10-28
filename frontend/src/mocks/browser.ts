// Register mock request handlers for the explicitly enabled browser demo.
import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'
export const worker = setupWorker(...handlers)

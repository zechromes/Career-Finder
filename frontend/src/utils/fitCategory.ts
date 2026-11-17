// One label and chip color per verdict, shared by the results table, job cards and job details.
type Fit = 'strong_match' | 'review' | 'not_suitable'

const LABELS: Record<Fit, string> = {
  strong_match: 'Strong match',
  review: 'For review',
  not_suitable: 'Not recommended',
}
const COLORS: Record<Fit, string> = {
  strong_match: 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  review: 'bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-300',
  not_suitable: 'bg-rose-50 text-rose-800 dark:bg-rose-950 dark:text-rose-300',
}

// A missing verdict reads as For review, as it always has.
const fit = (category?: string | null): Fit =>
  category && category in LABELS ? (category as Fit) : 'review'

export const fitLabel = (category?: string | null) => LABELS[fit(category)]
export const fitChipClass = (category?: string | null) => COLORS[fit(category)]

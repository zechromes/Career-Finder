// Convert stored timeline entries to editable display fields and back.
const months = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]
const month =
  '(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
const year = '(?:19|20)\\d{2}'
const date = `(?:${month}\\.?[ ,]+${year}|(?:0?[1-9]|1[0-2])[/.-]${year}|${year}-(?:0[1-9]|1[0-2])|${year})`
const range = new RegExp(`\\b(${date})\\s*(?:[–—-]|to)\\s*(${date}|present|current|now)\\b`, 'i')
// Format supported timeline dates without inventing missing date information.
function formatDate(value: string) {
  if (/^(present|current|now)$/i.test(value)) return 'Present'
  const named = value.match(new RegExp(`^(${month})\\.?[ ,]+(${year})$`, 'i'))
  if (named)
    return `${months.find((m) => m.slice(0, 3).toLowerCase() === named[1].slice(0, 3).toLowerCase())} ${named[2]}`
  const numeric = value.match(/^(\d{1,2})[/.-](\d{4})$/)
  if (numeric) return `${months[Number(numeric[1]) - 1]} ${numeric[2]}`
  const iso = value.match(/^(\d{4})-(\d{2})$/)
  if (iso) return `${months[Number(iso[2]) - 1]} ${iso[1]}`
  return value // Retain year-only evidence rather than inventing a month.
}
// Parse a stored history entry into labeled display fields.
export function displayTimelineEntry(entry: string) {
  if (entry.includes('|')) {
    const [title = '', company = '', dates = '', ...details] = entry
      .split('|')
      .map((part) => part.trim())
    const parsedDate = dates.match(range)
    return {
      title: title || 'New entry',
      company,
      date: parsedDate ? `${formatDate(parsedDate[1])} – ${formatDate(parsedDate[2])}` : dates,
      detail: details.join(' | ').trim(),
    }
  }
  const match = entry.match(range) || entry.match(new RegExp(`\\b(${date})\\b`, 'i'))
  const dates = match
    ? match[2]
      ? `${formatDate(match[1])} – ${formatDate(match[2])}`
      : formatDate(match[1])
    : ''
  const text = (match ? entry.replace(match[0], '').replace(/\(\s*\)/g, '') : entry)
    .trim()
    .replace(/^[,|;\s]+|[,|;\s]+$/g, '')
  // New extractions use pipes; accept older comma/newline and "Role at Company" entries too.
  const parts = text
    .split(text.includes('|') ? /\s*\|\s*/ : /\n|,\s+/)
    .map((p) => p.trim())
    .filter(Boolean)
  const heading = (parts.shift() || '').replace(/^(?:role|title|qualification|degree):\s*/i, '')
  const at = heading.split(/\s+at\s+/i)
  const title = at[0] || 'New entry'
  const company = (at.length > 1 ? at.slice(1).join(' at ') : parts.shift() || '').replace(
    /^(?:company|employer|institution|university):\s*/i,
    '',
  )
  return { date: dates, title, company, detail: parts.join(' · ') }
}

// Replace one timeline field without losing the other stored details.
export function updateTimelineField(
  entry: string,
  field: 'title' | 'company' | 'date' | 'detail',
  value: string,
) {
  const parsed = displayTimelineEntry(entry)
  if (!entry.trim()) parsed.title = ''
  parsed[field] = value
  return [parsed.title, parsed.company, parsed.date, parsed.detail].join(' | ')
}

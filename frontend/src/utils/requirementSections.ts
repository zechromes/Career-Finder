// Use source headings, never inferred candidate fit, to label requirement groups.
export function requirementSection(description: string, quote: string): string {
  const normalize = (text: string) =>
    text.toLowerCase().replace(/[*_#]/g, '').replace(/\s+/g, ' ').trim()
  const sections: { title: string; text: string }[] = []
  let current = { title: 'Other requirements', text: '' }
  for (const raw of description.split(/\r?\n/)) {
    const heading = normalize(raw).replace(/:$/, '').trim()
    let title = ''
    if (
      /^(qualifications|required qualifications|minimum qualifications|requirements|essential requirements|what you bring|what we.re looking for|about you)$/.test(
        heading,
      )
    )
      title = 'Qualifications'
    else if (
      /^(nice[- ]to[- ]haves?|preferred qualifications|preferred requirements|desirable|bonus points|bonus skills)$/.test(
        heading,
      )
    )
      title = 'Nice to have'
    else if (
      /^(responsibilities|key responsibilities|what you.ll do|what you will do|your role|the role|duties)$/.test(
        heading,
      )
    )
      title = 'Responsibilities'
    // Unrecognized explicit headings end the previous section instead of borrowing its label.
    if (title || /^\s*(?:#{1,6}\s+|\*\*.+\*\*\s*:?$)/.test(raw)) {
      sections.push(current)
      current = { title: title || 'Other requirements', text: '' }
    } else current.text += ` ${raw}`
  }
  sections.push(current)
  const needle = normalize(quote)
  if (!needle) return 'Other requirements'
  const matches = sections.filter((section) => normalize(section.text).includes(needle))
  return matches.length === 1 ? matches[0].title : 'Other requirements'
}

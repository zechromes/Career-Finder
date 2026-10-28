// Organize posting requirements into readable groups for the result views.
// Group related requirements while retaining their original text.
export function groupRequirements(requirements: string[]) {
  const groups = [
    { title: 'Must-haves', items: [] as string[] },
    { title: 'Responsibilities', items: [] as string[] },
    { title: 'Nice-to-haves', items: [] as string[] },
    { title: 'Other requirements', items: [] as string[] },
  ]
  for (const requirement of requirements) {
    const match = requirement.match(
      /^\s*(?:[-*•]\s*)?(?:\*\*)?(must[- ]haves?|required(?: qualifications| skills)?|mandatory|responsibilit(?:y|ies)|duties|nice[- ]to[- ]haves?|preferred(?: qualifications| skills)?|optional)(?:\*\*)?\s*[:–—-]\s*(?:\*\*)?\s*(.*)$/i,
    )
    const label = match?.[1].toLowerCase() || ''
    const index = /^(must|required|mandatory)/.test(label)
      ? 0
      : /^(responsibilit|duties)/.test(label)
        ? 1
        : /^(nice|preferred|optional)/.test(label)
          ? 2
          : 3
    const text = (match?.[2] || requirement).trim()
    if (text && !groups[index].items.includes(text)) groups[index].items.push(text)
  }
  return groups.filter((group) => group.items.length)
}

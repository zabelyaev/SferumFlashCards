export type FormulaSnippet = 'inline' | 'fraction' | 'root' | 'power' | 'display'

export function insertFormulaSnippet(
  value: string,
  selectionStart: number,
  selectionEnd: number,
  snippet: FormulaSnippet,
): { value: string; cursor: number } {
  const start = Math.max(0, Math.min(selectionStart, value.length))
  const end = Math.max(start, Math.min(selectionEnd, value.length))
  const selected = value.slice(start, end)

  let inserted: string
  let cursor: number
  switch (snippet) {
    case 'inline':
      inserted = `$${selected}$`
      cursor = start + (selected ? inserted.length : 1)
      break
    case 'fraction':
      inserted = `$\\frac{${selected}}{}$`
      cursor = start + 1 + '\\frac{'.length + selected.length
      break
    case 'root':
      inserted = `$\\sqrt{${selected}}$`
      cursor = start + 1 + '\\sqrt{'.length + selected.length
      break
    case 'power':
      inserted = `$${selected || 'x'}^{}$`
      cursor = start + 1 + (selected || 'x').length + 2
      break
    case 'display':
      inserted = `$$\n${selected}\n$$`
      cursor = start + 3 + selected.length
      break
  }

  return {
    value: value.slice(0, start) + inserted + value.slice(end),
    cursor,
  }
}

import katex from 'katex'

const ESC: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
const escapeHtml = (s: string) => s.replace(/[&<>"']/g, (c) => ESC[c])

// $$display$$ или $inline$ (inline — в одной строке)
const MATH_RE = /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g

function textToHtml(t: string): string {
  return escapeHtml(t).replace(/\n/g, '<br>')
}

function renderTex(tex: string, display: boolean): string {
  try {
    return katex.renderToString(tex, {
      displayMode: display,
      throwOnError: false, // ТЗ 4.2: ошибка в формуле не должна ронять интерфейс
      errorColor: '#d6322e',
      strict: 'ignore',
      trust: false,
    })
  } catch {
    return `<code class="tex-error">${escapeHtml(tex)}</code>`
  }
}

/**
 * Текст карточки → безопасный HTML.
 * Весь обычный текст экранируется, поэтому произвольный HTML от автора колоды не пройдёт (ТЗ 10.3);
 * формулы отдаёт KaTeX с trust:false.
 */
export function renderRich(src: string): string {
  let out = ''
  let last = 0
  for (const m of src.matchAll(MATH_RE)) {
    const idx = m.index ?? 0
    out += textToHtml(src.slice(last, idx))
    const display = m[1] !== undefined
    out += renderTex((display ? m[1] : m[2]).trim(), display)
    last = idx + m[0].length
  }
  return out + textToHtml(src.slice(last))
}

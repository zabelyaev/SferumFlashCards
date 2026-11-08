import { describe, expect, it } from 'vitest'
import { renderRich } from './katex'

describe('renderRich', () => {
  it('экранирует HTML в обычном тексте', () => {
    const html = renderRich('<img src=x onerror=alert(1)> привет')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img')
  })

  it('рендерит inline-формулу через KaTeX', () => {
    expect(renderRich('Сила $F = ma$')).toContain('class="katex"')
  })

  it('рендерит выключную формулу', () => {
    expect(renderRich('$$\\frac{a}{b}$$')).toContain('katex-display')
  })

  it('битая формула не бросает исключение', () => {
    expect(() => renderRich('$\\frac{1$')).not.toThrow()
  })
})

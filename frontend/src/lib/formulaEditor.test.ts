import { describe, expect, it } from 'vitest'
import { insertFormulaSnippet } from './formulaEditor'

describe('formula editor snippets', () => {
  it('wraps selected text as an inline formula', () => {
    expect(insertFormulaSnippet('Find x now', 5, 6, 'inline')).toEqual({
      value: 'Find $x$ now',
      cursor: 8,
    })
  })

  it('puts the cursor inside an empty inline formula', () => {
    expect(insertFormulaSnippet('', 0, 0, 'inline')).toEqual({ value: '$$', cursor: 1 })
  })

  it('inserts a fraction with the cursor in the numerator', () => {
    expect(insertFormulaSnippet('answer', 0, 0, 'fraction')).toEqual({
      value: '$\\frac{}{}$answer',
      cursor: 7,
    })
  })

  it('inserts root and exponent snippets as renderable formulas', () => {
    expect(insertFormulaSnippet('x', 0, 1, 'root')).toEqual({
      value: '$\\sqrt{x}$',
      cursor: 8,
    })
    expect(insertFormulaSnippet('', 0, 0, 'power')).toEqual({
      value: '$x^{}$',
      cursor: 4,
    })
  })

  it('wraps selected text as a display formula', () => {
    expect(insertFormulaSnippet('x + y', 0, 5, 'display')).toEqual({
      value: '$$\nx + y\n$$',
      cursor: 8,
    })
  })
})

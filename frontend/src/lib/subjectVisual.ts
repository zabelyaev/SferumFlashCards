import type { Subject } from '../types'

export const SUBJECT_VISUAL: Record<Subject, { glyph: string; background: string; color: string }> = {
  physics: { glyph: 'Ф', background: '#EBF3FF', color: '#0077FF' },
  algebra: { glyph: '∑', background: '#FEF3C7', color: '#FF9E00' },
  geometry: { glyph: '△', background: '#DCFCE7', color: '#27AE60' },
  chemistry: { glyph: 'Х₂', background: '#FEE2E2', color: '#FF334B' },
  biology: { glyph: 'Б', background: '#DCFCE7', color: '#27AE60' },
  history: { glyph: 'И', background: '#CCFBF1', color: '#0D9488' },
  russian: { glyph: 'Я', background: '#FEE2E2', color: '#FF334B' },
  informatics: { glyph: 'ИТ', background: '#EBF3FF', color: '#0077FF' },
  english: { glyph: 'EN', background: '#FEF3C7', color: '#FF9E00' },
  other: { glyph: '…', background: '#F2F3F5', color: '#818C99' },
}

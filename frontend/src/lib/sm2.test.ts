import { describe, expect, it } from 'vitest'
import { DEFAULT_EASE, MIN_EASE, calculateSM2, previewInterval } from './sm2'

const NOW = new Date('2026-10-28T12:00:00')
const fresh = { repetitions: 0, intervalDays: 0, easeFactor: DEFAULT_EASE, now: NOW }

describe('calculateSM2', () => {
  it('«Снова» сбрасывает серию, ставит интервал 1 день и сильно снижает EF', () => {
    const r = calculateSM2({ ...fresh, rating: 1, repetitions: 5, intervalDays: 30 })
    expect(r.repetitions).toBe(0)
    expect(r.intervalDays).toBe(1)
    expect(r.easeFactor).toBe(1.96)
    expect(r.state).toBe('relearning')
    expect(r.lapsed).toBe(true)
  })

  it('первое «Хорошо» → 1 день, EF не меняется', () => {
    const r = calculateSM2({ ...fresh, rating: 3 })
    expect(r.repetitions).toBe(1)
    expect(r.intervalDays).toBe(1)
    expect(r.easeFactor).toBe(2.5)
    expect(r.state).toBe('learning')
  })

  it('второе «Хорошо» → 3 дня', () => {
    const r = calculateSM2({ ...fresh, rating: 3, repetitions: 1, intervalDays: 1 })
    expect(r.repetitions).toBe(2)
    expect(r.intervalDays).toBe(3)
  })

  it('третье «Хорошо» → round(3 × 2.5) = 8 дней и состояние review', () => {
    const r = calculateSM2({ ...fresh, rating: 3, repetitions: 2, intervalDays: 3 })
    expect(r.intervalDays).toBe(8)
    expect(r.state).toBe('review')
  })

  it('«Легко» повышает EF, «Трудно» понижает, но остаётся успешным ответом', () => {
    const easy = calculateSM2({ ...fresh, rating: 4 })
    const hard = calculateSM2({ ...fresh, rating: 2 })
    expect(easy.easeFactor).toBe(2.6)
    expect(hard.easeFactor).toBe(2.36)
    expect(hard.repetitions).toBe(1)
    expect(hard.lapsed).toBe(false)
  })

  it('EF не опускается ниже 1.30', () => {
    const r = calculateSM2({ ...fresh, rating: 1, easeFactor: 1.35 })
    expect(r.easeFactor).toBe(MIN_EASE)
  })

  it('dueAt = now + интервал в днях', () => {
    const r = calculateSM2({ ...fresh, rating: 3, repetitions: 1, intervalDays: 1 })
    expect(r.dueAt.getDate()).toBe(31) // 28 окт + 3 дня
  })

  it('previewInterval совпадает с calculateSM2', () => {
    const input = { ...fresh, rating: 4 as const, repetitions: 2, intervalDays: 3 }
    expect(previewInterval(input)).toBe(calculateSM2(input).intervalDays)
  })
})

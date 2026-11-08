/**
 * SM-2 под 4 кнопки (раздел 9 ТЗ) — чистая функция без зависимостей от UI.
 * По ТЗ расчёт должен жить на сервере: этот же файл переиспользуется в бэкенде.
 *
 * Отличие от ТЗ: в формуле EF стоит (5 − q), поэтому кнопки 1..4 нельзя подставлять
 * в q напрямую — «Легко» (q=4) давало бы дельту 0 и EF никогда бы не рос.
 * Кнопки мапятся на q классического SM-2 через QUALITY.
 */

export type Rating = 1 | 2 | 3 | 4 // 1 Снова, 2 Трудно, 3 Хорошо, 4 Легко
export type ReviewState = 'learning' | 'review' | 'relearning'

export const QUALITY: Record<Rating, number> = { 1: 1, 2: 3, 3: 4, 4: 5 }
export const MIN_EASE = 1.3
export const DEFAULT_EASE = 2.5

export interface SM2Input {
  rating: Rating
  repetitions: number
  intervalDays: number
  easeFactor: number
  now?: Date
}

export interface SM2Output {
  repetitions: number
  intervalDays: number
  easeFactor: number
  state: ReviewState
  dueAt: Date
  lapsed: boolean
}

export function calculateSM2(input: SM2Input): SM2Output {
  const { rating, repetitions, intervalDays, easeFactor, now = new Date() } = input
  const q = QUALITY[rating]
  const lapsed = q < 3

  const delta = 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
  const nextEase = Math.max(MIN_EASE, Math.round((easeFactor + delta) * 100) / 100)

  let nextReps: number
  let nextInterval: number
  if (lapsed) {
    nextReps = 0
    nextInterval = 1
  } else {
    nextReps = repetitions + 1
    if (nextReps === 1) nextInterval = 1
    else if (nextReps === 2) nextInterval = 3
    else nextInterval = Math.max(1, Math.round(intervalDays * nextEase))
  }

  const state: ReviewState = lapsed ? 'relearning' : nextReps <= 2 ? 'learning' : 'review'

  const dueAt = new Date(now)
  dueAt.setDate(dueAt.getDate() + nextInterval)

  return {
    repetitions: nextReps,
    intervalDays: nextInterval,
    easeFactor: nextEase,
    state,
    dueAt,
    lapsed,
  }
}

/** Через сколько дней карточка вернётся, если нажать эту кнопку (подпись под кнопкой). */
export function previewInterval(input: SM2Input): number {
  return calculateSM2(input).intervalDays
}

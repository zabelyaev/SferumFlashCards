export type Subject =
  | 'physics'
  | 'algebra'
  | 'geometry'
  | 'chemistry'
  | 'biology'
  | 'history'
  | 'russian'
  | 'informatics'
  | 'english'
  | 'other'

export const SUBJECT_LABEL: Record<Subject, string> = {
  physics: 'Физика',
  algebra: 'Алгебра',
  geometry: 'Геометрия',
  chemistry: 'Химия',
  biology: 'Биология',
  history: 'История',
  russian: 'Русский язык',
  informatics: 'Информатика',
  english: 'Английский язык',
  other: 'Другое',
}

export interface Card {
  id: string
  deckId: string
  front: string // текст + $inline$ / $$display$$ формулы
  back: string
  tag?: string // плашка типа карточки: «Формула», «Дата»…
  hint?: string
  explanation?: string
  imageUrl?: string | null
}

export interface Deck {
  id: string
  title: string
  subject: Subject | null
  grade: number | null
  cards: Card[]
  description?: string
  coverColor?: string | null
  isPublic?: boolean
  isUserCreated?: boolean
  cardsCount?: number
  shareCode?: string
}

export type CardState = 'new' | 'learning' | 'review' | 'relearning'

/** Прогресс пользователя по карточке. Нет записи = карточка новая. */
export interface CardProgress {
  cardId: string
  deckId: string
  state: Exclude<CardState, 'new'>
  repetitions: number
  easeFactor: number
  intervalDays: number
  lapses: number
  dueAt: string // ISO
  lastReviewedAt: string // ISO
}

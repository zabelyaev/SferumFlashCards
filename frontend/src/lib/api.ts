import type { Card, Deck, Subject } from '../types'

const API_ROOT = __API_ROOT__

export interface ApiDeck {
  id: number
  author_id: number | null
  title: string
  description: string | null
  subject: Subject | null
  grade: number | null
  exam_type: 'oge' | 'ege' | null
  cover_color: string | null
  is_public: boolean
  is_official: boolean
  share_code: string
  cards_count: number
  created_at: string
  updated_at: string
}

export interface ApiCard {
  id: number
  deck_id: number
  front: string
  back: string
  hint: string | null
  explanation: string | null
  image_url: string | null
  order_index: number
  created_at: string
  updated_at: string
}

export interface ApiProfile {
  id: number
  vk_user_id: number
  first_name: string
  last_name: string
  avatar_url: string | null
  role: 'student' | 'teacher' | 'admin'
  is_active: boolean
  timezone: string
  streak_days: number
  max_streak_days: number
  last_streak_date: string | null
  daily_total_cards_limit: number
  daily_new_cards_limit: number
  settings?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ApiStudySession {
  id: number
  deck_id: number | null
  study_date: string
  status: 'active' | 'completed' | 'abandoned'
  started_at: string
  last_activity_at: string
  expires_at: string
  finished_at: string | null
  finish_reason: string | null
  limits: {
    daily_total_cards_limit: number
    daily_new_cards_limit: number
  }
  progress: {
    total_cards: number
    completed_cards: number
    remaining_cards: number
  }
}

export interface ApiDailyQuota {
  total_used: number
  new_used: number
  total_remaining: number
  new_remaining: number
}

export interface ApiStreak {
  streak_days: number
  max_streak_days: number
  last_streak_date: string | null
}

export interface ApiStudySessionView {
  session: ApiStudySession
  current_card_id: number | null
  answer_token: string | null
  quota: ApiDailyQuota
  streak: ApiStreak
  cards: ApiCard[]
}

export interface ApiNoWork {
  session: null
  current_card_id: null
  answer_token: null
  deck_id: number
  study_date: string
  limits: ApiStudySession['limits']
  quota: ApiDailyQuota
  streak: ApiStreak
  cards: []
  reason: 'empty_deck' | 'limits_reached' | 'nothing_due'
}

export interface ApiReviewResult extends Omit<ApiStudySessionView, 'cards'> {}

interface ApiList<T> {
  items: T[]
  total: number
}

export interface DeckFilters {
  search?: string
  subject?: Subject
  grade?: number
  exam_type?: 'oge' | 'ege'
  page?: number
  limit?: number
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (__API_ENABLED__) {
    const userId = __DEV_VK_USER_ID__ ||
      String(window.WebApp?.initDataUnsafe?.user?.id ?? __FALLBACK_VK_USER_ID__)
    if (!userId) throw new ApiError('Откройте приложение через MAX, чтобы войти в API.')
    headers.set('X-App-Key', __API_APP_KEY__)
    headers.set('X-VK-User-ID', userId)
  }
  if (init.body !== undefined) headers.set('Content-Type', 'application/json')

  let response: Response
  try {
    response = await fetch(`${API_ROOT}${path}`, { ...init, headers })
  } catch (error) {
    throw new ApiError(
      error instanceof Error ? `Не удалось связаться с API: ${error.message}` : 'Не удалось связаться с API.',
    )
  }

  if (response.status === 204) return undefined as T

  const responseText = await response.text()
  let body: unknown
  if (responseText) {
    try {
      body = JSON.parse(responseText)
    } catch {
      if (response.ok) {
        throw new ApiError('API вернул некорректный JSON.', response.status)
      }
      const detail = responseText.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 240)
      body = { detail: detail || 'Сервер вернул ответ в неизвестном формате.' }
    }
  }
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : undefined
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((item) => {
            if (item && typeof item === 'object' && 'msg' in item && typeof item.msg === 'string') {
              return item.msg
            }
            return 'Ошибка проверки данных'
          }).join('. ')
        : `Сервер API или прокси вернул ошибку (${response.status}). Проверьте консоль Vite.`
    throw new ApiError(message, response.status)
  }

  return body as T
}

function toQuery(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value))
  }
  const value = query.toString()
  return value ? `?${value}` : ''
}

export function mapApiCard(card: ApiCard): Card {
  return {
    id: String(card.id),
    deckId: String(card.deck_id),
    front: card.front,
    back: card.back,
    hint: card.hint ?? undefined,
    explanation: card.explanation ?? undefined,
    imageUrl: card.image_url,
  }
}

export function mapApiDeck(deck: ApiDeck, cards: Card[] = []): Deck {
  return {
    id: String(deck.id),
    title: deck.title,
    description: deck.description ?? undefined,
    subject: deck.subject,
    grade: deck.grade,
    coverColor: deck.cover_color,
    isPublic: deck.is_public,
    isUserCreated: false,
    cardsCount: deck.cards_count,
    shareCode: deck.share_code,
    cards,
  }
}

async function getAllPages<T>(loadPage: (page: number) => Promise<ApiList<T>>): Promise<T[]> {
  const result: T[] = []
  let page = 1
  let total = 0
  do {
    const response = await loadPage(page)
    result.push(...response.items)
    total = response.total
    if (!response.items.length && result.length < total) {
      throw new ApiError('API вернул неполную страницу без элементов.')
    }
    page++
  } while (result.length < total)
  return result
}

export const api = {
  syncUser: (input: { vk_user_id: number; first_name: string; timezone: string }) =>
    request<ApiProfile>('/users/sync', {
      method: 'POST',
      body: JSON.stringify(input),
    }),

  getProfile: () => request<ApiProfile>('/users/me/profile'),

  updateProfile: (input: Partial<Pick<ApiProfile,
    'first_name' | 'last_name' | 'avatar_url' | 'timezone' | 'daily_total_cards_limit' | 'daily_new_cards_limit'
  >>) =>
    request<ApiProfile>('/users/me/profile', {
      method: 'PATCH',
      body: JSON.stringify(input),
    }),

  replaceSettings: (settings: Record<string, unknown>) =>
    request<ApiProfile>('/users/me/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),

  openStudySession: (deckId: string) => {
    const numericDeckId = Number(deckId)
    if (!Number.isSafeInteger(numericDeckId) || numericDeckId <= 0) {
      throw new ApiError('Для серверного занятия выберите одну колоду.')
    }
    return request<ApiStudySessionView | ApiNoWork>('/study/sessions', {
      method: 'POST',
      body: JSON.stringify({ deck_id: numericDeckId }),
    })
  },

  getStudySession: (sessionId: string) =>
    request<ApiStudySessionView>(`/study/sessions/${encodeURIComponent(sessionId)}`),

  submitStudyReview: (sessionId: string, input: {
    card_id: number
    rating: number
    answer_token: string
  }) => request<ApiReviewResult>(`/study/sessions/${encodeURIComponent(sessionId)}/reviews`, {
    method: 'POST',
    body: JSON.stringify(input),
  }),

  getCatalog: (filters: DeckFilters = {}) =>
    request<ApiList<ApiDeck>>(`/decks${toQuery({
      search: filters.search,
      subject: filters.subject,
      grade: filters.grade,
      exam_type: filters.exam_type,
      page: filters.page,
      limit: filters.limit,
    })}`),

  getLibrary: (filters: Pick<DeckFilters, 'search' | 'subject' | 'page' | 'limit'> = {}) =>
    request<ApiList<ApiDeck>>(`/library/decks${toQuery(filters)}`),

  getAllLibraryDecks: () =>
    getAllPages((page) => api.getLibrary({ page, limit: 100 })),

  getAllCatalogDecks: (filters: Omit<DeckFilters, 'page' | 'limit'> = {}) =>
    getAllPages((page) => api.getCatalog({ ...filters, page, limit: 100 })),

  getDeckCards: (deckId: string) =>
    getAllPages((page) =>
      request<ApiList<ApiCard>>(`/decks/${encodeURIComponent(deckId)}/cards${toQuery({ page, limit: 100 })}`),
    ).then((cards) => cards.map(mapApiCard)),

  getSharePreview: (shareCode: string) =>
    request<{ deck: ApiDeck; cards: ApiCard[] }>(`/decks/share/${encodeURIComponent(shareCode)}`),

  createDeck: (input: {
    title: string
    description?: string
    subject: Subject | null
    grade: number | null
    coverColor?: string
  }) => request<ApiDeck>('/decks', {
    method: 'POST',
    body: JSON.stringify({
      title: input.title,
      description: input.description || null,
      ...(input.subject ? { subject: input.subject } : {}),
      ...(input.grade ? { grade: input.grade } : {}),
      cover_color: input.coverColor || 'gradient-blue',
      is_public: false,
    }),
  }),

  updateDeck: (deckId: string, input: {
    title: string
    description?: string
    subject: Subject | null
    grade: number | null
    coverColor?: string
  }) => request<ApiDeck>(`/decks/${encodeURIComponent(deckId)}`, {
    method: 'PATCH',
    body: JSON.stringify({
      title: input.title,
      description: input.description || null,
      subject: input.subject,
      grade: input.grade,
      cover_color: input.coverColor,
    }),
  }),

  deleteDeck: (deckId: string) =>
    request<void>(`/decks/${encodeURIComponent(deckId)}`, { method: 'DELETE' }),

  addToLibrary: (deckId: string) =>
    request<{ id: number; user_id: number; deck_id: number; is_favorite: boolean; created_at: string }>(
      `/library/decks/${encodeURIComponent(deckId)}`,
      { method: 'PUT' },
    ),

  addSharedDeck: (shareCode: string) =>
    request<{ id: number; user_id: number; deck_id: number; is_favorite: boolean; created_at: string }>(
      `/library/decks/share/${encodeURIComponent(shareCode)}`,
      { method: 'PUT' },
    ),

  removeFromLibrary: (deckId: string) =>
    request<void>(`/library/decks/${encodeURIComponent(deckId)}`, { method: 'DELETE' }),

  createCard: (deckId: string, input: {
    front: string
    back: string
    hint?: string
    explanation?: string
    imageUrl?: string
  }) => request<ApiCard>(`/decks/${encodeURIComponent(deckId)}/cards`, {
    method: 'POST',
    body: JSON.stringify({
      front: input.front,
      back: input.back,
      hint: input.hint || null,
      explanation: input.explanation || null,
      image_url: input.imageUrl || null,
    }),
  }),

  updateCard: (deckId: string, cardId: string, input: {
    front: string
    back: string
    hint?: string
    explanation?: string
    imageUrl?: string
  }) => request<ApiCard>(
    `/decks/${encodeURIComponent(deckId)}/cards/${encodeURIComponent(cardId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify({
        front: input.front,
        back: input.back,
        hint: input.hint || null,
        explanation: input.explanation || null,
        image_url: input.imageUrl || null,
      }),
    },
  ),

  deleteCard: (deckId: string, cardId: string) =>
    request<void>(
      `/decks/${encodeURIComponent(deckId)}/cards/${encodeURIComponent(cardId)}`,
      { method: 'DELETE' },
    ),
}

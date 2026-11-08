import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'
import { MOCK_CATALOG_DECKS, MOCK_DECKS } from '../data/mock'
import { api, mapApiCard, mapApiDeck, type ApiDeck, type ApiProfile } from '../lib/api'
import { DEFAULT_EASE, calculateSM2, previewInterval, type Rating } from '../lib/sm2'
import type { Card, CardProgress, Deck, Subject } from '../types'

const STORAGE_KEY = 'zapominalka:v1'

interface Saved {
  decks?: Deck[]
  progress: Record<string, CardProgress>
  streak: { days: number; max: number; lastDate: string | null }
  newToday: { date: string; count: number }
  dailyTotalLimit?: number
  dailyNewLimit?: number
  userSettings?: Record<string, unknown>
}

type DeckInput = Pick<Deck, 'title' | 'subject' | 'grade'> & Pick<Deck, 'description'> & { coverColor?: string }
type CardInput = Pick<Card, 'front' | 'back'> & Pick<Card, 'hint' | 'explanation'> & { imageUrl?: string }

const dayKey = (d = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

function createId(prefix: string): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return `${prefix}-${Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')}`
}

function load(): Saved | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Saved) : null
  } catch (error) {
    console.warn('Не удалось загрузить локальные данные обучения.', error)
    return null
  }
}

/** Local learning state used by mock mode; API mode delegates study scheduling to the server. */
export const useStudyStore = defineStore('study', () => {
  const saved = load()

  const apiMode = __API_ENABLED__
  const decks = ref<Deck[]>(saved?.decks ?? MOCK_DECKS)
  const progress = reactive<Record<string, CardProgress>>(saved?.progress ?? {})
  const newToday = reactive(saved?.newToday ?? { date: dayKey(), count: 0 })
  const settings = reactive({
    dailyTotalLimit: saved?.dailyTotalLimit ?? 125,
    dailyNewLimit: saved?.dailyNewLimit ?? 20,
  })
  const user = reactive({ firstName: 'Ученик' }) // TODO: имя из MAX initData
  const profile = ref<ApiProfile | null>(null)
  const userSettings = ref<Record<string, unknown>>(saved?.userSettings ?? {})
  const streak = reactive({
    days: saved?.streak.days ?? 0,
    max: saved?.streak.max ?? 0,
    lastDate: saved?.streak.lastDate ?? (null as string | null),
  })
  const apiLoading = ref(false)
  const apiError = ref('')
  let devUserSynced = false

  function persist() {
    try {
      const data: Saved = {
        decks: decks.value,
        progress: { ...progress },
        streak: { days: streak.days, max: streak.max, lastDate: streak.lastDate },
        newToday: { date: newToday.date, count: newToday.count },
        dailyTotalLimit: settings.dailyTotalLimit,
        dailyNewLimit: settings.dailyNewLimit,
        userSettings: userSettings.value,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch (error) {
      console.error('Не удалось сохранить локальные данные обучения.', error)
    }
  }

  function rollNewToday() {
    const today = dayKey()
    if (newToday.date !== today) {
      newToday.date = today
      newToday.count = 0
    }
  }

  async function loadLibrary(): Promise<void> {
    if (!apiMode) return
    apiLoading.value = true
    apiError.value = ''
    try {
      if (!devUserSynced) {
        const maxUser = window.WebApp?.initDataUnsafe?.user
        const fallbackUserId = __DEV_VK_USER_ID__ || __FALLBACK_VK_USER_ID__
        const vkUserId = maxUser?.id ?? Number(fallbackUserId)
        if (!Number.isSafeInteger(vkUserId) || !vkUserId || vkUserId <= 0) {
          throw new Error('Не удалось получить пользователя. Откройте приложение через MAX.')
        }
        await api.syncUser({
          vk_user_id: vkUserId,
          first_name: fallbackUserId && !maxUser?.id
            ? 'Тестовый пользователь'
            : maxUser?.first_name || 'Ученик',
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
        })
        devUserSynced = true
      }

      const [apiProfile, apiDecks] = await Promise.all([
        api.getProfile(),
        api.getAllLibraryDecks(),
      ])
      const currentDecks = new Map(decks.value.map((deck) => [deck.id, deck]))
      decks.value = apiDecks.map((apiDeck) => {
        const previous = currentDecks.get(String(apiDeck.id))
        const deck = mapApiDeck(apiDeck, previous?.cards ?? [])
        deck.isUserCreated = apiDeck.author_id === apiProfile.id
        return deck
      })
      user.firstName = apiProfile.first_name || 'Ученик'
      profile.value = apiProfile
      userSettings.value = apiProfile.settings ?? {}
      streak.days = apiProfile.streak_days
      streak.max = apiProfile.max_streak_days
      streak.lastDate = apiProfile.last_streak_date
      settings.dailyTotalLimit = apiProfile.daily_total_cards_limit
      settings.dailyNewLimit = apiProfile.daily_new_cards_limit
      persist()
    } catch (error) {
      apiError.value = error instanceof Error ? error.message : 'Не удалось загрузить библиотеку из API.'
      throw error
    } finally {
      apiLoading.value = false
    }
  }

  async function loadDeckCards(deckId: string): Promise<void> {
    if (!apiMode) return
    apiError.value = ''
    try {
      const deck = deckById(deckId)
      if (!deck) throw new Error('Колода не найдена в библиотеке.')
      deck.cards = await api.getDeckCards(deckId)
      deck.cardsCount = deck.cards.length
      persist()
    } catch (error) {
      apiError.value = error instanceof Error ? error.message : 'Не удалось загрузить карточки колоды.'
      throw error
    }
  }

  async function loadCatalog(filters: {
    search?: string
    subject?: Subject
    grade?: number
    exam_type?: 'oge' | 'ege'
    page?: number
    limit?: number
  } = {}): Promise<{ items: Deck[]; total: number }> {
    if (apiMode) {
      const result = await api.getCatalog(filters)
      return { items: result.items.map((deck) => mapApiDeck(deck)), total: result.total }
    }
    const term = filters.search?.trim().toLocaleLowerCase()
    const items = MOCK_CATALOG_DECKS.filter((deck) =>
      (!term || deck.title.toLocaleLowerCase().includes(term)) &&
      (!filters.subject || deck.subject === filters.subject) &&
      (!filters.grade || deck.grade === filters.grade),
    )
    return { items, total: items.length }
  }

  async function addToLibrary(deck: Deck): Promise<void> {
    if (decks.value.some((item) => item.id === deck.id)) return
    if (apiMode) {
      await api.addToLibrary(deck.id)
      await loadLibrary()
      return
    }
    const copy: Deck = {
      ...deck,
      cards: deck.cards.map((card) => ({ ...card })),
      isUserCreated: false,
    }
    decks.value.push(copy)
    persist()
  }

  async function addSharedDeck(shareCode: string): Promise<void> {
    if (!apiMode) throw new Error('Добавление по коду доступно после подключения API.')
    await api.addSharedDeck(shareCode)
    await loadLibrary()
  }

  async function saveDailyLimits(totalLimit: number, newLimit: number): Promise<void> {
    if (!Number.isInteger(totalLimit) || totalLimit < 20 || totalLimit > 1000) {
      throw new Error('Общий дневной лимит должен быть от 20 до 1000 карточек.')
    }
    if (!Number.isInteger(newLimit) || newLimit < 1 || newLimit > 250) {
      throw new Error('Лимит новых карточек должен быть от 1 до 250.')
    }
    if (apiMode) {
      const updatedProfile = await api.updateProfile({
        daily_total_cards_limit: totalLimit,
        daily_new_cards_limit: newLimit,
      })
      profile.value = updatedProfile
      settings.dailyTotalLimit = updatedProfile.daily_total_cards_limit
      settings.dailyNewLimit = updatedProfile.daily_new_cards_limit
      streak.days = updatedProfile.streak_days
      streak.max = updatedProfile.max_streak_days
      streak.lastDate = updatedProfile.last_streak_date
      user.firstName = updatedProfile.first_name || 'Ученик'
    } else {
      settings.dailyTotalLimit = totalLimit
      settings.dailyNewLimit = newLimit
      persist()
    }
  }

  async function saveDailyNewLimit(limit: number): Promise<void> {
    await saveDailyLimits(settings.dailyTotalLimit, limit)
  }

  async function saveUserSettings(value: Record<string, unknown>): Promise<void> {
    if (apiMode) {
      const updatedProfile = await api.replaceSettings(value)
      profile.value = updatedProfile
      userSettings.value = updatedProfile.settings ?? value
    } else {
      userSettings.value = value
      persist()
    }
  }

  async function removeFromLibrary(deckId: string): Promise<void> {
    const deck = deckById(deckId)
    if (!deck || deck.isUserCreated) return
    if (apiMode) await api.removeFromLibrary(deckId)
    decks.value = decks.value.filter((item) => item.id !== deckId)
    for (const card of deck.cards) delete progress[card.id]
    persist()
  }

  const cardById = (id: string): Card | undefined => {
    for (const d of decks.value) {
      const c = d.cards.find((x) => x.id === id)
      if (c) return c
    }
    return undefined
  }

  const deckById = (id: string) => decks.value.find((d) => d.id === id)

  const isDue = (p: CardProgress) => new Date(p.dueAt).getTime() <= Date.now()

  function dueIds(deckId: string | 'all'): string[] {
    return decks.value
      .filter((d) => deckId === 'all' || d.id === deckId)
      .flatMap((d) => d.cards)
      .filter((c) => progress[c.id] && isDue(progress[c.id]))
      .sort((a, b) => progress[a.id].dueAt.localeCompare(progress[b.id].dueAt))
      .map((c) => c.id)
  }

  function newIds(deckId: string | 'all'): string[] {
    return decks.value
      .filter((d) => deckId === 'all' || d.id === deckId)
      .flatMap((d) => d.cards)
      .filter((c) => !progress[c.id])
      .map((c) => c.id)
  }

  const dueCount = (deckId: string | 'all') => dueIds(deckId).length
  const newCount = (deckId: string | 'all') => newIds(deckId).length

  /** Сначала карточки с наступившим сроком, затем новые в рамках дневного лимита (ТЗ 8.5). */
  function buildQueue(deckId: string | 'all'): string[] {
    rollNewToday()
    const totalRemaining = Math.max(0, settings.dailyTotalLimit - reviewedToday())
    const due = dueIds(deckId).slice(0, totalRemaining)
    const newRemaining = Math.max(0, Math.min(
      settings.dailyNewLimit - newToday.count,
      totalRemaining - due.length,
    ))
    return [...due, ...newIds(deckId).slice(0, newRemaining)]
  }

  function progressInput(cardId: string) {
    const p = progress[cardId]
    return {
      repetitions: p?.repetitions ?? 0,
      intervalDays: p?.intervalDays ?? 0,
      easeFactor: p?.easeFactor ?? DEFAULT_EASE,
    }
  }

  /** Доля выученных (дошедших до состояния review) карточек колоды, 0–100. */
  function learnedPercent(deckId: string): number {
    const deck = deckById(deckId)
    if (!deck || !deck.cards.length) return 0
    const learned = deck.cards.filter((c) => progress[c.id]?.state === 'review').length
    return Math.round((learned / deck.cards.length) * 100)
  }

  /** Сколько карточек уже повторено сегодня. */
  function reviewedToday(): number {
    const today = dayKey()
    return Object.values(progress).filter((p) => dayKey(new Date(p.lastReviewedAt)) === today).length
  }

  function applyServerStreak(value: { streak_days: number; max_streak_days: number; last_streak_date: string | null }) {
    streak.days = value.streak_days
    streak.max = value.max_streak_days
    streak.lastDate = value.last_streak_date
    persist()
  }

  const stateOf = (cardId: string) => progress[cardId]?.state ?? 'new'

  const previewDays = (cardId: string, rating: Rating) =>
    previewInterval({ rating, ...progressInput(cardId) })

  function review(cardId: string, rating: Rating) {
    const card = cardById(cardId)
    if (!card) return
    rollNewToday()
    const prev = progress[cardId]
    if (!prev) newToday.count++

    const now = new Date()
    const r = calculateSM2({ rating, ...progressInput(cardId), now })
    progress[cardId] = {
      cardId,
      deckId: card.deckId,
      state: r.state,
      repetitions: r.repetitions,
      easeFactor: r.easeFactor,
      intervalDays: r.intervalDays,
      lapses: (prev?.lapses ?? 0) + (r.lapsed ? 1 : 0),
      dueAt: r.dueAt.toISOString(),
      lastReviewedAt: now.toISOString(),
    }
    persist()
  }

  async function createDeck(input: DeckInput): Promise<Deck> {
    if (apiMode) {
      const created = mapApiDeck(await api.createDeck(input))
      created.isUserCreated = true
      decks.value.push(created)
      persist()
      return created
    }
    const deck: Deck = {
      id: createId('deck'),
      title: input.title.trim(),
      description: input.description?.trim() || undefined,
      subject: input.subject,
      grade: input.grade,
      coverColor: input.coverColor || 'gradient-blue',
      isPublic: false,
      isUserCreated: true,
      cards: [],
    }
    decks.value.push(deck)
    persist()
    return deck
  }

  async function updateDeck(deckId: string, input: DeckInput): Promise<boolean> {
    const deck = deckById(deckId)
    if (!deck || !deck.isUserCreated) return false
    if (apiMode) {
      const updated = mapApiDeck(await api.updateDeck(deckId, input), deck.cards)
      updated.isUserCreated = true
      Object.assign(deck, updated)
      persist()
      return true
    }
    Object.assign(deck, {
      title: input.title.trim(),
      description: input.description?.trim() || undefined,
      subject: input.subject,
      grade: input.grade,
      coverColor: input.coverColor,
    })
    persist()
    return true
  }

  async function deleteDeck(deckId: string): Promise<boolean> {
    const deck = deckById(deckId)
    if (!deck || !deck.isUserCreated) return false
    if (apiMode) await api.deleteDeck(deckId)
    decks.value = decks.value.filter((item) => item.id !== deckId)
    for (const card of deck.cards) delete progress[card.id]
    persist()
    return true
  }

  async function createCard(deckId: string, input: CardInput): Promise<Card | undefined> {
    const deck = deckById(deckId)
    if (!deck || !deck.isUserCreated) return undefined
    if (apiMode) {
      const card = mapApiCard(await api.createCard(deckId, input))
      deck.cards.push(card)
      deck.cardsCount = deck.cards.length
      persist()
      return card
    }
    const card: Card = {
      id: createId('card'),
      deckId,
      front: input.front.trim(),
      back: input.back.trim(),
      hint: input.hint?.trim() || undefined,
      explanation: input.explanation?.trim() || undefined,
      imageUrl: input.imageUrl?.trim() || undefined,
    }
    deck.cards.push(card)
    persist()
    return card
  }

  async function updateCard(deckId: string, cardId: string, input: CardInput): Promise<boolean> {
    const deck = deckById(deckId)
    const card = deck?.cards.find((item) => item.id === cardId)
    if (!deck?.isUserCreated || !card) return false
    if (apiMode) {
      Object.assign(card, mapApiCard(await api.updateCard(deckId, cardId, input)))
      persist()
      return true
    }
    Object.assign(card, {
      front: input.front.trim(),
      back: input.back.trim(),
      hint: input.hint?.trim() || undefined,
      explanation: input.explanation?.trim() || undefined,
      imageUrl: input.imageUrl?.trim() || undefined,
    })
    persist()
    return true
  }

  async function deleteCard(deckId: string, cardId: string): Promise<boolean> {
    const deck = deckById(deckId)
    if (!deck?.isUserCreated || !deck.cards.some((item) => item.id === cardId)) return false
    if (apiMode) await api.deleteCard(deckId, cardId)
    deck.cards = deck.cards.filter((item) => item.id !== cardId)
    deck.cardsCount = deck.cards.length
    delete progress[cardId]
    persist()
    return true
  }

  /** Стрик (ТЗ 4.5): день засчитывается за сессию от 5 карточек, один раз в календарный день. */
  function completeSession(cardsCount: number) {
    if (cardsCount >= 5) {
      const today = dayKey()
      if (streak.lastDate !== today) {
        const y = new Date()
        y.setDate(y.getDate() - 1)
        streak.days = streak.lastDate === dayKey(y) ? streak.days + 1 : 1
        streak.max = Math.max(streak.max, streak.days)
        streak.lastDate = today
      }
    }
    persist()
  }

  function resetAll() {
    for (const k of Object.keys(progress)) delete progress[k]
    streak.days = 0
    streak.max = 0
    streak.lastDate = null
    newToday.count = 0
    persist()
  }

  return {
    decks, progress, streak, settings, user, profile, userSettings, apiMode, apiLoading, apiError,
    cardById, deckById, dueCount, newCount, buildQueue,
    stateOf, learnedPercent, reviewedToday, previewDays, review, completeSession, applyServerStreak, resetAll,
    loadLibrary, loadDeckCards, loadCatalog, addToLibrary, removeFromLibrary, addSharedDeck,
    saveDailyLimits, saveDailyNewLimit, saveUserSettings,
    createDeck, updateDeck, deleteDeck, createCard, updateCard, deleteCard,
  }
})

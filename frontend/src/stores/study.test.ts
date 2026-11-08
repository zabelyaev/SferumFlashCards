import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useStudyStore } from './study'

const values = new Map<string, string>()

beforeEach(() => {
  values.clear()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  })
  setActivePinia(createPinia())
})

describe('study store deck management', () => {
  it('creates and persists decks and cards', async () => {
    const store = useStudyStore()
    const deck = await store.createDeck({
      title: '  Моя колода  ',
      subject: null,
      grade: null,
      description: '  Описание  ',
    })
    const card = await store.createCard(deck.id, {
      front: '  Вопрос  ',
      back: '  Ответ  ',
      hint: '',
      explanation: undefined,
    })

    expect(deck.title).toBe('Моя колода')
    expect(deck.description).toBe('Описание')
    expect(card?.front).toBe('Вопрос')
    expect(JSON.parse(values.get('zapominalka:v1') ?? '{}').decks).toHaveLength(store.decks.length)

    setActivePinia(createPinia())
    expect(useStudyStore().deckById(deck.id)?.cards[0].back).toBe('Ответ')
  })

  it('allows editing and deleting only user-created deck content', async () => {
    const store = useStudyStore()
    const mockDeck = store.decks[0]
    const customDeck = await store.createDeck({
      title: 'Пользовательская',
      subject: 'physics',
      grade: 9,
      description: '',
    })
    const card = await store.createCard(customDeck.id, {
      front: 'Вопрос',
      back: 'Ответ',
      hint: undefined,
      explanation: undefined,
    })

    expect(await store.updateDeck(mockDeck.id, {
      title: 'Изменено',
      subject: null,
      grade: null,
      description: '',
    })).toBe(false)
    expect(await store.deleteDeck(mockDeck.id)).toBe(false)
    expect(await store.deleteCard(customDeck.id, card!.id)).toBe(true)
    expect(await store.deleteDeck(customDeck.id)).toBe(true)
    expect(store.deckById(customDeck.id)).toBeUndefined()
  })

  it('persists daily limit and user preferences locally', async () => {
    const store = useStudyStore()
    await store.saveDailyNewLimit(35)
    await store.saveUserSettings({ soundEnabled: false, hintsEnabled: true })

    setActivePinia(createPinia())
    const restored = useStudyStore()
    expect(restored.settings.dailyNewLimit).toBe(35)
    expect(restored.settings.dailyTotalLimit).toBe(125)
    expect(restored.userSettings).toEqual({ soundEnabled: false, hintsEnabled: true })
  })

  it('enforces both local daily card limits', async () => {
    const store = useStudyStore()
    await store.saveDailyLimits(20, 1)

    expect(store.buildQueue('phys-kinematics')).toHaveLength(1)
  })
})

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Confetti from '../components/Confetti.vue'
import Icon from '../components/Icon.vue'
import StudyCard from '../components/StudyCard.vue'
import { api, mapApiCard, type ApiStudySessionView } from '../lib/api'
import { plural } from '../lib/plural'
import type { Rating } from '../lib/sm2'
import { useStudyStore } from '../stores/study'
import { SUBJECT_LABEL, type Card } from '../types'

const props = defineProps<{ deckId: string }>()
const store = useStudyStore()
const router = useRouter()

const queue = ref<string[]>([])
const practiceRepeat = ref(false)
const total = ref(0)
const completed = ref(0)
const answers = ref({ good: 0, all: 0 })
const hardIds = new Set<string>()
const revealed = ref(false)
const finished = ref(false)
const confirmExit = ref(false)
const startedAt = ref(Date.now())
const streakAfter = ref(0)
const elapsedSec = ref(0)
const loadingSession = ref(store.apiMode)
const sessionLoadError = ref('')
const noWorkReason = ref('')
const remoteSession = ref<ApiStudySessionView | null>(null)
const remoteCards = ref<ReturnType<typeof mapApiCard>[]>([])
const reviewBusy = ref(false)
const reviewError = ref('')

const currentId = computed(() => practiceRepeat.value || !store.apiMode
  ? queue.value[0]
  : String(remoteSession.value?.current_card_id ?? ''))
const card = computed<Card | undefined>(() => {
  if (!currentId.value) return undefined
  if (practiceRepeat.value || !store.apiMode) return store.cardById(currentId.value)
  return remoteCards.value.find((item) => item.id === currentId.value)
})
const position = computed(() => Math.min(completed.value + 1, total.value))
const remaining = computed(() => Math.max(0, total.value - position.value))
const percent = computed(() => (total.value ? Math.round((completed.value / total.value) * 100) : 0))
const accuracy = computed(() =>
  answers.value.all ? Math.round((answers.value.good / answers.value.all) * 100) : 0,
)
const title = computed(() =>
  props.deckId === 'all' ? 'Повторение' : (store.deckById(props.deckId)?.title ?? 'Тренировка'),
)
const subjectSubtitle = computed(() => {
  const subject = props.deckId === 'all' ? null : store.deckById(props.deckId)?.subject
  return subject ? SUBJECT_LABEL[subject] : 'Интервальное повторение'
})

const RATINGS: { value: Rating; label: string; tone: string }[] = [
  { value: 1, label: 'Снова', tone: 'red' },
  { value: 2, label: 'Трудно', tone: 'yellow' },
  { value: 3, label: 'Хорошо', tone: 'blue' },
  { value: 4, label: 'Легко', tone: 'green' },
]

function intervalLabel(rating: Rating): string {
  if (rating === 1) return '< 1 мин' // «Снова» возвращается в эту же сессию
  const d = store.previewDays(currentId.value, rating)
  return `${d} ${plural(d, ['день', 'дня', 'дней'])}`
}

function start(ids: string[]) {
  practiceRepeat.value = false
  queue.value = [...ids]
  total.value = ids.length
  completed.value = 0
  answers.value = { good: 0, all: 0 }
  hardIds.clear()
  revealed.value = false
  finished.value = false
  startedAt.value = Date.now()
}

function reveal() {
  if (!finished.value && card.value) revealed.value = true
}

async function rate(rating: Rating) {
  const id = currentId.value
  if (!revealed.value || !id) return
  if (practiceRepeat.value) {
    answers.value.all++
    if (rating >= 3) answers.value.good++
    if (rating <= 2) hardIds.add(id)
    queue.value.shift()
    if (rating === 1) queue.value.push(id)
    else completed.value++
    revealed.value = false
    if (!queue.value.length) finish()
    return
  }
  if (store.apiMode) {
    const activeSession = remoteSession.value
    if (!activeSession?.answer_token || reviewBusy.value) return
    reviewBusy.value = true
    reviewError.value = ''
    try {
      const result = await api.submitStudyReview(String(activeSession.session.id), {
        card_id: Number(id),
        rating,
        answer_token: activeSession.answer_token,
      })
      remoteSession.value = { ...activeSession, ...result, cards: activeSession.cards }
      completed.value = result.session.progress.completed_cards
      total.value = result.session.progress.total_cards
      streakAfter.value = result.streak.streak_days
      store.applyServerStreak(result.streak)
      answers.value.all++
      if (rating >= 3) answers.value.good++
      revealed.value = false
      if (result.session.status === 'completed') finish()
    } catch (error) {
      reviewError.value = error instanceof Error ? error.message : 'Не удалось сохранить ответ.'
    } finally {
      reviewBusy.value = false
    }
    return
  }

  store.review(id, rating)
  answers.value.all++
  if (rating >= 3) answers.value.good++
  if (rating <= 2) hardIds.add(id)
  queue.value.shift()
  if (rating === 1) {
    queue.value.push(id) // «Снова» — в конец очереди (на макете для неё «< 1 мин»)
  } else {
    completed.value++
  }
  revealed.value = false
  if (!queue.value.length) finish()
}

function finish() {
  elapsedSec.value = Math.round((Date.now() - startedAt.value) / 1000)
  if (!store.apiMode && !practiceRepeat.value) {
    store.completeSession(total.value)
    streakAfter.value = store.streak.days
  }
  finished.value = true
}

const retryHard = () => start([...hardIds])
const goHome = () => router.push({ name: 'home' })
const goToLibrary = () => router.push({ name: 'library' })

async function repeatForPractice() {
  loadingSession.value = true
  sessionLoadError.value = ''
  try {
    if (store.apiMode && props.deckId !== 'all') {
      await store.loadDeckCards(props.deckId)
    }
    const cards = props.deckId === 'all'
      ? store.decks.flatMap((deck) => deck.cards)
      : store.deckById(props.deckId)?.cards ?? []
    if (!cards.length) {
      noWorkReason.value = 'empty_deck'
      return
    }
    practiceRepeat.value = true
    queue.value = cards.map((item) => item.id)
    total.value = cards.length
    completed.value = 0
    answers.value = { good: 0, all: 0 }
    hardIds.clear()
    revealed.value = false
    finished.value = false
    noWorkReason.value = ''
    startedAt.value = Date.now()
  } catch (error) {
    sessionLoadError.value = error instanceof Error ? error.message : 'Не удалось загрузить карточки для повтора.'
  } finally {
    loadingSession.value = false
  }
}

function onKey(e: KeyboardEvent) {
  if (e.repeat || finished.value || confirmExit.value) return
  if (e.key === ' ' || e.key === 'Enter') {
    if (!revealed.value) {
      e.preventDefault()
      reveal()
    }
  } else if (['1', '2', '3', '4'].includes(e.key)) {
    rate(Number(e.key) as Rating)
  }
}

async function initializeSession() {
  loadingSession.value = store.apiMode
  sessionLoadError.value = ''
  noWorkReason.value = ''
  practiceRepeat.value = false
  queue.value = []
  remoteSession.value = null
  remoteCards.value = []
  total.value = 0
  completed.value = 0
  try {
    if (store.apiMode) {
      await store.loadLibrary()
      const result = await api.openStudySession(props.deckId)
      if (result.session === null) {
        noWorkReason.value = result.reason
        streakAfter.value = result.streak.streak_days
        store.applyServerStreak(result.streak)
        return
      }
      remoteSession.value = result
      remoteCards.value = result.cards.map(mapApiCard)
      store.applyServerStreak(result.streak)
      total.value = result.session.progress.total_cards
      completed.value = result.session.progress.completed_cards
      if (result.session.status !== 'active' || result.current_card_id === null) {
        noWorkReason.value = result.session.status === 'abandoned' ? 'session_expired' : 'nothing_due'
        total.value = 0
        return
      }
      if (!remoteCards.value.some((item) => item.id === String(result.current_card_id))) {
        throw new Error('В ответе API нет текущей карточки сессии.')
      }
      answers.value = { good: 0, all: 0 }
      startedAt.value = Date.now()
      return
    }
    start(store.buildQueue(props.deckId))
  } catch (error) {
    sessionLoadError.value = error instanceof Error ? error.message : 'Не удалось подготовить занятие.'
  } finally {
    loadingSession.value = false
  }
}

void initializeSession()
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="session-screen">
  <section v-if="loadingSession" class="center-note" role="status">
    <h1>Готовим занятие…</h1>
    <p class="muted">Загружаем колоду и карточки.</p>
  </section>

  <section v-else-if="sessionLoadError" class="center-note">
    <h1>Не удалось открыть занятие</h1>
    <p class="form-error" role="alert">{{ sessionLoadError }}</p>
    <div class="actions">
      <button class="btn" type="button" @click="router.push({ name: 'library' })">К библиотеке</button>
      <button class="btn btn--primary" type="button" @click="initializeSession">Повторить</button>
    </div>
  </section>

  <section v-else-if="!total" class="center-note">
    <h1>{{ noWorkReason === 'empty_deck' ? 'В этой колоде пока нет карточек' : noWorkReason === 'limits_reached' ? 'Дневной лимит достигнут' : noWorkReason === 'session_expired' ? 'Занятие завершилось' : 'На сегодня повторений больше нет' }}</h1>
    <p class="muted">
      {{ noWorkReason === 'limits_reached' ? 'Можно изменить дневные лимиты или потренироваться на карточках без изменения расписания.' : noWorkReason === 'nothing_due' ? 'Карточки вернутся по расписанию. Можно пройти их ещё раз для тренировки — повтор не изменит FSRS и прогресс.' : noWorkReason === 'session_expired' ? 'Откройте колоду и начните новое занятие.' : 'Добавьте карточки в библиотеку, чтобы начать занятие.' }}
    </p>
    <div class="actions">
      <button
        v-if="noWorkReason === 'nothing_due' || noWorkReason === 'limits_reached'"
        class="btn btn--primary"
        type="button"
        @click="repeatForPractice"
      >
        Повторить для тренировки
      </button>
      <button class="btn" type="button" @click="goToLibrary">Мои колоды</button>
      <button class="btn" type="button" @click="goHome">На главную</button>
    </div>
  </section>

  <section v-else-if="finished" class="summary">
    <Confetti />
    <h1>{{ practiceRepeat ? 'Тренировка завершена' : 'Отличная работа!' }}</h1>
    <dl class="stats">
      <div><dt>Карточек пройдено</dt><dd>{{ store.apiMode && !practiceRepeat ? completed : total }}</dd></div>
      <div v-if="!store.apiMode || practiceRepeat"><dt>Время</dt><dd>{{ Math.floor(elapsedSec / 60) }} мин {{ elapsedSec % 60 }} сек</dd></div>
      <div v-if="!store.apiMode || practiceRepeat"><dt>Точность</dt><dd>{{ accuracy }}%</dd></div>
      <div v-if="!practiceRepeat"><dt>Серия</dt><dd>{{ streakAfter }} {{ plural(streakAfter, ['день', 'дня', 'дней']) }}</dd></div>
    </dl>
    <p v-if="practiceRepeat" class="muted">Тренировочный повтор не меняет прогресс и интервалы FSRS.</p>
    <p v-else-if="total < 5" class="muted">Чтобы день засчитался в серию, пройдите сессию из 5 карточек.</p>
    <div class="actions">
      <button v-if="practiceRepeat" class="btn" type="button" @click="repeatForPractice">Повторить ещё раз</button>
      <button v-else-if="store.apiMode" class="btn" type="button" @click="repeatForPractice">Повторить для тренировки</button>
      <button v-if="hardIds.size && !store.apiMode" class="btn" type="button" @click="retryHard">Повторить сложные карточки</button>
      <button class="btn btn--primary" type="button" @click="goToLibrary">Мои колоды</button>
      <button class="btn" type="button" @click="goHome">На главную</button>
    </div>
  </section>

  <template v-else-if="card">
    <header class="session-top">
      <div class="session-head">
        <button class="icon-circle" type="button" aria-label="Закрыть сессию" @click="confirmExit = true">
          <Icon name="x" />
        </button>
        <div class="session-title">
          <strong>{{ title }}</strong>
          <span>{{ practiceRepeat ? 'Тренировочный повтор · без записи в FSRS' : subjectSubtitle }}</span>
        </div>
        <span class="left-badge">{{ position }}/{{ total }}</span>
      </div>
      <div
        class="session-progress"
        role="progressbar"
        aria-valuemin="0"
        :aria-valuemax="total"
        :aria-valuenow="completed"
      >
        <span :style="{ width: percent + '%' }" />
      </div>
    </header>
    <StudyCard
      :key="card.id"
      :card="card"
      :revealed="revealed"
      :hints-enabled="store.userSettings.hintsEnabled !== false"
      @reveal="reveal"
    />

    <footer class="session-foot">
      <button v-if="!revealed" class="btn btn--primary btn--big btn--wide" type="button" @click="reveal">
        <Icon name="eye" /> Показать ответ
      </button>
      <template v-else>
        <p class="rate-label">Насколько легко было вспомнить?</p>
        <p v-if="reviewError" class="form-error" role="alert">{{ reviewError }}</p>
        <div class="rate-row">
          <button
            v-for="r in RATINGS"
            :key="r.value"
            class="rate"
            :class="`rate--${r.tone}`"
            type="button"
            :disabled="reviewBusy"
            @click="rate(r.value)"
          >
            <b v-if="!store.apiMode && !practiceRepeat">{{ intervalLabel(r.value) }}</b>
            <span>{{ r.label }}</span>
          </button>
        </div>
      </template>
    </footer>

    <div v-if="confirmExit" class="dialog" role="alertdialog" aria-modal="true" aria-label="Выйти из сессии">
      <div class="dialog__box">
        <p>Выйти из сессии? Ответы, которые вы уже дали, сохранены.</p>
        <div class="actions">
          <button class="btn" type="button" @click="confirmExit = false">Продолжить</button>
          <button class="btn btn--primary" type="button" @click="goHome">Выйти</button>
        </div>
      </div>
    </div>
  </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '../components/Icon.vue'
import { plural } from '../lib/plural'
import { SUBJECT_VISUAL } from '../lib/subjectVisual'
import { useStudyStore } from '../stores/study'
import { SUBJECT_LABEL } from '../types'

const store = useStudyStore()
const router = useRouter()
const showAiNotice = ref(false)

const initials = computed(() => store.user.firstName.slice(0, 1).toUpperCase())
const due = computed(() => store.dueCount('all'))
const fresh = computed(() => store.apiMode
  ? 0
  : store.newCount('all'))
const ratio = computed(() => {
  const done = store.reviewedToday()
  return done + due.value ? Math.round((done / (done + due.value)) * 100) : 0
})
const minutes = computed(() => Math.max(1, Math.round(due.value * 0.4)))
const dueText = computed(() => {
  const count = due.value
  const verb = count % 10 === 1 && count % 100 !== 11 ? 'требует' : 'требуют'
  return `${count} ${plural(count, ['карточка', 'карточки', 'карточек'])} ${verb} закрепления`
})
const visibleDecks = computed(() => store.decks)
const deckCount = computed(() => store.decks.length)

onMounted(() => {
  if (store.apiMode) {
    store.loadLibrary().catch((error: unknown) => {
      console.error('Не удалось загрузить данные главного экрана.', error)
    })
  }
})

function start(deckId: string) {
  void router.push({ name: 'session', params: { deckId } })
}

function startAll() {
  if (store.apiMode) {
    void router.push({ name: 'library' })
    return
  }
  start('all')
}
</script>

<template>
  <div class="home-screen">
    <header class="home-head">
      <button class="who" type="button" aria-label="Открыть профиль" @click="router.push({ name: 'profile' })">
        <span class="avatar">{{ initials }}</span>
        <span class="who__titles">
          <strong>Привет, {{ store.user.firstName }}!</strong>
          <span class="muted">MAX · учись каждый день</span>
        </span>
      </button>
      <p class="streak" :class="{ 'streak--off': store.streak.days === 0 }">
        <Icon name="flame" :size="18" />
        {{ store.streak.days }} {{ plural(store.streak.days, ['день', 'дня', 'дней']) }}
      </p>
    </header>

    <div class="home-content">
      <section class="review-widget">
        <div class="review-widget__top">
          <div>
            <h2>Интервальное повторение</h2>
            <p v-if="store.apiMode" class="card__due">Выберите колоду — сервер подберёт карточки по расписанию.</p>
            <p v-else-if="due" class="card__due">{{ dueText }}</p>
            <p v-else-if="fresh" class="card__due">
              {{ fresh }} {{ plural(fresh, ['новая карточка', 'новые карточки', 'новых карточек']) }}
            </p>
            <p v-else class="card__done">На сегодня всё повторено</p>
          </div>
          <span v-if="!store.apiMode" class="review-widget__count">{{ due || fresh }}</span>
        </div>
        <div v-if="!store.apiMode" class="track" role="progressbar" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="ratio">
          <span :style="{ width: ratio + '%' }" />
        </div>
        <button
          v-if="store.apiMode"
          class="btn btn--primary btn--wide"
          type="button"
          @click="router.push({ name: 'library' })"
        >
          <Icon name="book" :size="16" />
          Выбрать колоду
        </button>
        <button
          v-else-if="due || fresh"
          class="btn btn--primary btn--wide"
          type="button"
          @click="startAll"
        >
          <Icon name="play" :size="16" />
          {{ due ? `Повторить сейчас (${minutes} мин)` : 'Учить новое' }}
        </button>
        <button v-else class="btn btn--primary btn--wide" type="button" @click="router.push({ name: 'catalog' })">
          Открыть каталог
        </button>
      </section>

      <section class="section" aria-labelledby="decks-title">
        <div class="section__head">
          <h2 id="decks-title">Мои колоды</h2>
          <button class="link-btn" type="button" @click="router.push({ name: 'library' })">
            Все {{ deckCount }}
          </button>
        </div>
        <p v-if="store.apiLoading" class="muted" role="status">Загружаем библиотеку…</p>
        <p v-else-if="store.apiError" class="form-error" role="alert">{{ store.apiError }}</p>
        <ul v-else-if="visibleDecks.length" class="deck-list">
          <li v-for="deck in visibleDecks" :key="deck.id">
            <button class="deck" type="button" @click="start(deck.id)">
              <span class="deck__left">
                <span
                  class="deck__icon"
                  :style="{
                    background: deck.coverColor?.startsWith('#') ? deck.coverColor : SUBJECT_VISUAL[deck.subject ?? 'other'].background,
                    color: SUBJECT_VISUAL[deck.subject ?? 'other'].color,
                  }"
                  aria-hidden="true"
                >{{ SUBJECT_VISUAL[deck.subject ?? 'other'].glyph }}</span>
                <span class="deck__info">
                  <span class="deck__title">{{ deck.title }}</span>
                  <span class="deck__meta">
                    {{ deck.cardsCount ?? deck.cards.length }}
                    {{ plural(deck.cardsCount ?? deck.cards.length, ['карточка', 'карточки', 'карточек']) }}
                    · {{ deck.grade ? `${deck.grade} класс` : SUBJECT_LABEL[deck.subject ?? 'other'] }}
                  </span>
                  <span v-if="!store.apiMode" class="deck__track" aria-hidden="true">
                    <span :style="{ width: `${store.learnedPercent(deck.id)}%` }" />
                  </span>
                </span>
              </span>
              <span v-if="!store.apiMode" class="deck__right">
                <span class="deck__pct">{{ store.learnedPercent(deck.id) }}%</span>
                <span class="deck__status">
                  {{ store.learnedPercent(deck.id) === 100 ? 'Выучено' : store.learnedPercent(deck.id) ? 'В процессе' : 'Новая' }}
                </span>
              </span>
              <span v-else class="deck__right">
                <span class="deck__status">В библиотеке</span>
              </span>
            </button>
          </li>
        </ul>
        <div v-else class="home-empty">
          <p>В библиотеке пока нет колод.</p>
          <button class="link-btn" type="button" @click="router.push({ name: 'catalog' })">Открыть каталог</button>
        </div>
      </section>
    </div>

    <div v-if="showAiNotice" class="dialog" role="dialog" aria-modal="true" aria-labelledby="ai-notice-title">
      <div class="dialog__box">
        <h2 id="ai-notice-title">ИИ-сканер пока не подключён</h2>
        <p class="muted">Сейчас можно создать колоду вручную — она сохранится в вашей библиотеке.</p>
        <div class="actions">
          <button class="btn" type="button" @click="showAiNotice = false">Закрыть</button>
          <button class="btn btn--primary" type="button" @click="router.push({ name: 'library', query: { create: '1' } })">
            Создать колоду
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

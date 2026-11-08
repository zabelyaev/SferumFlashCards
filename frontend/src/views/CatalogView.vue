<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import MathText from '../components/MathText.vue'
import { plural } from '../lib/plural'
import { SUBJECT_VISUAL } from '../lib/subjectVisual'
import { api, mapApiCard, mapApiDeck } from '../lib/api'
import { useStudyStore } from '../stores/study'
import { SUBJECT_LABEL, type Deck } from '../types'

const store = useStudyStore()
const router = useRouter()
const decks = ref<Deck[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const error = ref('')
const addingId = ref<string | null>(null)
const preview = ref<Deck | null>(null)
const previewLoading = ref(false)
const previewError = ref('')

const pageSize = 20
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

onMounted(() => {
  loadPage().catch((loadError: unknown) => console.error('Не удалось загрузить каталог.', loadError))
})

async function loadPage() {
  loading.value = true
  error.value = ''
  try {
    if (store.apiMode) await store.loadLibrary()
    const result = await store.loadCatalog({
      page: store.apiMode ? page.value : undefined,
      limit: store.apiMode ? pageSize : undefined,
    })
    decks.value = result.items
    total.value = result.total
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Не удалось загрузить каталог.'
    throw loadError
  } finally {
    loading.value = false
  }
}

async function changePage(nextPage: number) {
  page.value = nextPage
  try {
    await loadPage()
  } catch (loadError) {
    console.error('Не удалось загрузить страницу каталога.', loadError)
  }
}

const inLibrary = (deck: Deck) => store.decks.some((item) => item.id === deck.id)

async function add(deck: Deck) {
  addingId.value = deck.id
  error.value = ''
  try {
    await store.addToLibrary(deck)
  } catch (addError) {
    error.value = addError instanceof Error ? addError.message : 'Не удалось добавить колоду.'
  } finally {
    addingId.value = null
  }
}

async function openPreview(deck: Deck) {
  previewError.value = ''
  previewLoading.value = true
  try {
    if (store.apiMode && deck.shareCode) {
      const result = await api.getSharePreview(deck.shareCode)
      preview.value = mapApiDeck(result.deck, result.cards.map(mapApiCard))
    } else {
      preview.value = deck
    }
  } catch (previewLoadError) {
    previewError.value = previewLoadError instanceof Error
      ? previewLoadError.message
      : 'Не удалось загрузить предпросмотр.'
  } finally {
    previewLoading.value = false
  }
}
</script>

<template>
  <div class="catalog-screen">
  <header class="library-head">
    <button class="icon-circle" type="button" aria-label="На главную" @click="router.push({ name: 'home' })">
      ←
    </button>
    <h1>Каталог колод</h1>
    <button class="link-btn" type="button" @click="router.push({ name: 'library' })">Мои колоды</button>
  </header>

  <p v-if="loading" class="muted" role="status">Загружаем каталог…</p>
  <p v-else-if="error" class="form-error" role="alert">{{ error }}</p>
  <section v-else-if="!decks.length" class="center-note">
    <h2>Общих колод пока нет</h2>
    <p class="muted">Опубликованные колоды появятся здесь.</p>
  </section>

  <ul v-else class="deck-list">
    <li v-for="deck in decks" :key="deck.id" class="library-item catalog-item">
      <div class="catalog-item__heading">
        <span
          class="deck__icon"
          :style="{
            background: deck.coverColor?.startsWith('#')
              ? deck.coverColor
              : SUBJECT_VISUAL[deck.subject ?? 'other'].background,
            color: SUBJECT_VISUAL[deck.subject ?? 'other'].color,
          }"
          aria-hidden="true"
        >{{ SUBJECT_VISUAL[deck.subject ?? 'other'].glyph }}</span>
        <div class="catalog-item__text">
        <strong class="deck__title">{{ deck.title }}</strong>
        <p class="deck__meta">
          {{ SUBJECT_LABEL[deck.subject ?? 'other'] }}
          · {{ deck.grade ? `${deck.grade} класс` : 'без класса' }}
          · {{ deck.cardsCount ?? deck.cards.length }}
          {{ plural(deck.cardsCount ?? deck.cards.length, ['карточка', 'карточки', 'карточек']) }}
        </p>
        <p v-if="deck.description" class="muted">{{ deck.description }}</p>
        </div>
      </div>
      <div class="actions">
        <button class="btn" type="button" @click="openPreview(deck)">Предпросмотр</button>
        <button
          class="btn btn--primary"
          type="button"
          :disabled="inLibrary(deck) || addingId === deck.id"
          @click="add(deck)"
        >
          {{ inLibrary(deck) ? 'Уже в библиотеке' : addingId === deck.id ? 'Добавляем…' : 'Добавить себе' }}
        </button>
      </div>
    </li>
  </ul>

  <nav v-if="store.apiMode && pages > 1" class="pagination" aria-label="Страницы каталога">
    <button class="btn" type="button" :disabled="page <= 1 || loading" @click="changePage(page - 1)">Назад</button>
    <span>Страница {{ page }} из {{ pages }}</span>
    <button class="btn" type="button" :disabled="page >= pages || loading" @click="changePage(page + 1)">
      Далее
    </button>
  </nav>

  <div v-if="preview || previewLoading || previewError" class="dialog" role="dialog" aria-modal="true" aria-labelledby="preview-title">
    <div class="dialog__box preview-dialog">
      <button class="preview-close" type="button" aria-label="Закрыть" @click="preview = null; previewError = ''">×</button>
      <p v-if="previewLoading" class="muted" role="status">Загружаем предпросмотр…</p>
      <p v-else-if="previewError" class="form-error" role="alert">{{ previewError }}</p>
      <template v-else-if="preview">
        <h2 id="preview-title">{{ preview.title }}</h2>
        <p class="muted">
          {{ SUBJECT_LABEL[preview.subject ?? 'other'] }}
          · {{ preview.cardsCount ?? preview.cards.length }}
          {{ plural(preview.cardsCount ?? preview.cards.length, ['карточка', 'карточки', 'карточек']) }}
        </p>
        <p v-if="preview.description">{{ preview.description }}</p>
        <ul class="card-list preview-cards">
          <li v-for="card in preview.cards.slice(0, 5)" :key="card.id" class="card-item">
            <div class="card-item__text">
              <strong>{{ card.front }}</strong>
              <MathText :text="card.back" class="muted" />
            </div>
          </li>
        </ul>
        <p v-if="preview.cards.length > 5" class="muted">Показаны первые 5 карточек.</p>
        <div class="actions">
          <button class="btn" type="button" @click="preview = null">Закрыть</button>
          <button
            class="btn btn--primary"
            type="button"
            :disabled="inLibrary(preview) || addingId === preview.id"
            @click="add(preview)"
          >
            {{ inLibrary(preview) ? 'Уже в библиотеке' : 'Добавить себе' }}
          </button>
        </div>
      </template>
    </div>
  </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import MathText from '../components/MathText.vue'
import { api, mapApiCard, mapApiDeck } from '../lib/api'
import { plural } from '../lib/plural'
import { useStudyStore } from '../stores/study'
import { SUBJECT_LABEL, type Deck } from '../types'

const props = defineProps<{ shareCode: string }>()
const store = useStudyStore()
const router = useRouter()
const deck = ref<Deck | null>(null)
const loading = ref(true)
const adding = ref(false)
const error = ref('')
const message = ref('')

async function loadPreview() {
  loading.value = true
  error.value = ''
  try {
    if (!store.apiMode) throw new Error('Предпросмотр по коду доступен после подключения API.')
    await store.loadLibrary()
    const result = await api.getSharePreview(props.shareCode)
    deck.value = mapApiDeck(result.deck, result.cards.map(mapApiCard))
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Не удалось загрузить колоду.'
  } finally {
    loading.value = false
  }
}

async function addToLibrary() {
  adding.value = true
  message.value = ''
  try {
    await store.addSharedDeck(props.shareCode)
    message.value = 'Колода добавлена в вашу библиотеку.'
  } catch (addError) {
    message.value = addError instanceof Error ? addError.message : 'Не удалось добавить колоду.'
  } finally {
    adding.value = false
  }
}

onMounted(loadPreview)
</script>

<template>
  <header class="library-head">
    <button class="icon-circle" type="button" aria-label="Назад" @click="router.back()">←</button>
    <h1>Колода по ссылке</h1>
    <button class="link-btn" type="button" @click="router.push({ name: 'library' })">Библиотека</button>
  </header>

  <section v-if="loading" class="center-note" role="status">
    <h2>Загружаем колоду…</h2>
  </section>
  <section v-else-if="error" class="center-note">
    <h2>Не удалось открыть колоду</h2>
    <p class="form-error" role="alert">{{ error }}</p>
    <button class="btn btn--primary" type="button" @click="loadPreview">Попробовать ещё раз</button>
  </section>
  <section v-else-if="deck" class="share-preview card">
    <h2>{{ deck.title }}</h2>
    <p class="muted">
      {{ SUBJECT_LABEL[deck.subject ?? 'other'] }}
      · {{ deck.cards.length }} {{ plural(deck.cards.length, ['карточка', 'карточки', 'карточек']) }}
    </p>
    <p v-if="deck.description">{{ deck.description }}</p>
    <ul class="card-list">
      <li v-for="card in deck.cards.slice(0, 10)" :key="card.id" class="card-item">
        <div class="card-item__text">
          <strong>{{ card.front }}</strong>
          <MathText :text="card.back" class="muted" />
        </div>
      </li>
    </ul>
    <p v-if="deck.cards.length > 10" class="muted">Показаны первые 10 карточек.</p>
    <p v-if="message" class="muted" role="status">{{ message }}</p>
    <div class="actions">
      <button class="btn btn--primary" type="button" :disabled="adding" @click="addToLibrary">
        {{ adding ? 'Добавляем…' : 'Добавить в мою библиотеку' }}
      </button>
      <button class="btn" type="button" @click="router.push({ name: 'catalog' })">К каталогу</button>
    </div>
  </section>
</template>

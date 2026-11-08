<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyStore } from '../stores/study'

const store = useStudyStore()
const router = useRouter()
const loading = ref(false)
const error = ref('')

onMounted(async () => {
  if (!store.apiMode) return
  loading.value = true
  try {
    await store.loadLibrary()
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Не удалось загрузить профиль.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <header class="library-head">
    <button class="icon-circle" type="button" aria-label="На главную" @click="router.push({ name: 'home' })">←</button>
    <h1>Профиль</h1>
    <button class="link-btn" type="button" @click="router.push({ name: 'settings' })">Настройки</button>
  </header>

  <section v-if="loading" class="card" role="status">Загружаем профиль…</section>
  <p v-else-if="error" class="form-error" role="alert">{{ error }}</p>
  <section v-else class="card profile-card">
    <div class="avatar">{{ store.user.firstName.slice(0, 1).toUpperCase() }}</div>
    <div>
      <h2>{{ store.profile ? `${store.profile.first_name} ${store.profile.last_name}`.trim() : store.user.firstName }}</h2>
      <p class="muted">{{ store.profile?.role ?? 'Локальный профиль' }}</p>
    </div>
    <dl class="profile-stats">
      <div><dt>Текущая серия</dt><dd>{{ store.streak.days }} дней</dd></div>
      <div><dt>Рекорд</dt><dd>{{ store.streak.max }} дней</dd></div>
      <div><dt>Всего карточек в день</dt><dd>{{ store.settings.dailyTotalLimit }}</dd></div>
      <div><dt>Новых карточек в день</dt><dd>{{ store.settings.dailyNewLimit }}</dd></div>
      <div><dt>Колоды в библиотеке</dt><dd>{{ store.decks.length }}</dd></div>
    </dl>
    <p v-if="!store.apiMode" class="api-study-notice">
      Локальный профиль — имя и статистика пока не синхронизируются с сервером.
    </p>
  </section>
</template>

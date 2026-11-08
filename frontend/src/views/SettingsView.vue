<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyStore } from '../stores/study'

const store = useStudyStore()
const router = useRouter()
const totalLimit = ref(store.settings.dailyTotalLimit)
const newLimit = ref(store.settings.dailyNewLimit)
const hintsEnabled = ref(store.userSettings.hintsEnabled !== false)
const saving = ref(false)
const loading = ref(false)
const message = ref('')
const error = ref('')

onMounted(async () => {
  if (!store.apiMode) return
  loading.value = true
  try {
    await store.loadLibrary()
    totalLimit.value = store.settings.dailyTotalLimit
    newLimit.value = store.settings.dailyNewLimit
    hintsEnabled.value = store.userSettings.hintsEnabled !== false
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Не удалось загрузить настройки.'
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  message.value = ''
  error.value = ''
  try {
    await store.saveDailyLimits(totalLimit.value, newLimit.value)
    await store.saveUserSettings({
      ...store.userSettings,
      hintsEnabled: hintsEnabled.value,
    })
    message.value = 'Настройки сохранены.'
  } catch (saveError) {
    error.value = saveError instanceof Error ? saveError.message : 'Не удалось сохранить настройки.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <header class="library-head">
    <button class="icon-circle" type="button" aria-label="На главную" @click="router.push({ name: 'home' })">←</button>
    <h1>Настройки</h1>
    <button class="link-btn" type="button" @click="router.push({ name: 'profile' })">Профиль</button>
  </header>

  <p v-if="loading" class="muted" role="status">Загружаем настройки…</p>
  <form v-else class="card settings-form" @submit.prevent="save">
    <label class="field">
      <span>Всего карточек в день: {{ totalLimit }}</span>
      <input v-model.number="totalLimit" type="range" min="20" max="1000" step="1" />
    </label>
    <label class="field">
      <span>Новых карточек в день: {{ newLimit }}</span>
      <input v-model.number="newLimit" type="range" min="1" max="250" step="1" />
      <span class="muted">Лимиты сохраняются в профиле пользователя на API.</span>
    </label>
    <label class="setting-toggle">
      <span>Подсказки включены</span>
      <input v-model="hintsEnabled" type="checkbox" />
    </label>
    <p class="muted">Звуковые эффекты пока не реализованы.</p>
    <p v-if="!store.apiMode" class="api-study-notice">
      Сейчас настройки сохраняются только в этом браузере; после подключения API — в профиле на сервере.
    </p>
    <p v-if="message" class="success-note" role="status">{{ message }}</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <button class="btn btn--primary" type="submit" :disabled="saving">
      {{ saving ? 'Сохраняем…' : 'Сохранить настройки' }}
    </button>
  </form>
</template>

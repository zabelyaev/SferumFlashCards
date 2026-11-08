<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icon from './Icon.vue'

const route = useRoute()
const router = useRouter()

const activeTab = computed(() => {
  switch (route.name) {
    case 'catalog':
      return 'catalog'
    case 'library':
    case 'share':
    case 'session':
      return 'library'
    case 'profile':
    case 'settings':
      return 'profile'
    default:
      return 'home'
  }
})

const tabs = [
  { key: 'home', label: 'Главная', icon: 'home', route: 'home' },
  { key: 'catalog', label: 'Каталог', icon: 'catalog', route: 'catalog' },
  { key: 'library', label: 'Мои колоды', icon: 'book', route: 'library' },
  { key: 'profile', label: 'Профиль', icon: 'user', route: 'profile' },
] as const
</script>

<template>
  <nav class="tab-bar" aria-label="Разделы приложения">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      class="tab-item"
      :class="{ 'tab-item--active': activeTab === tab.key }"
      type="button"
      :aria-current="activeTab === tab.key ? 'page' : undefined"
      @click="router.push({ name: tab.route })"
    >
      <Icon :name="tab.icon" :size="20" />
      <span>{{ tab.label }}</span>
    </button>
  </nav>
</template>

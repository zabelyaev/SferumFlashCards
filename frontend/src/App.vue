<script setup lang="ts">
import BottomNavigation from './components/BottomNavigation.vue'
</script>

<template>
  <main class="app">
    <div class="screen-content">
      <RouterView />
    </div>
    <BottomNavigation />
  </main>
</template>

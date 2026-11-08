<script setup lang="ts">
import { computed } from 'vue'
import { renderRich } from '../lib/katex'

const props = defineProps<{ text: string }>()
// renderRich экранирует весь текст вне формул, поэтому v-html здесь безопасен
const html = computed(() => renderRich(props.text))
</script>

<template>
  <div class="rich" v-html="html" />
</template>

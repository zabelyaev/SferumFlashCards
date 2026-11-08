<script setup lang="ts">
import { ref } from 'vue'
import type { Card } from '../types'
import MathText from './MathText.vue'

withDefaults(defineProps<{ card: Card; revealed: boolean; hintsEnabled?: boolean }>(), {
  hintsEnabled: true,
})
const emit = defineEmits<{ reveal: [] }>()

const hintOpen = ref(false)
</script>

<template>
  <article class="study-card" :class="{ 'is-revealed': revealed }" @click="emit('reveal')">
    <!-- Вопрос: до ответа крупно, после — компактно (экраны 2A и 2A-Answer) -->
    <header v-if="!revealed" class="study-card__tag-row">
      <span v-if="card.tag" class="tag">{{ card.tag }}</span>
      <span class="study-card__tap">Нажмите, чтобы открыть ответ</span>
    </header>
    <span v-else-if="card.tag" class="tag tag--small">{{ card.tag }} • Вопрос</span>

    <hr v-if="!revealed" class="divider" />

    <div v-if="!revealed" class="study-card__question">
      <MathText :text="card.front" class="q-big" />
      <img v-if="card.imageUrl" class="study-card__image" :src="card.imageUrl" alt="Изображение к карточке" />
      <template v-if="card.hint && hintsEnabled">
        <button v-if="!hintOpen" class="link-btn" type="button" @click.stop="hintOpen = true">
          Показать подсказку
        </button>
        <MathText v-else :text="card.hint" class="hint" />
      </template>
    </div>

    <template v-else>
      <MathText :text="card.front" class="q-small" />
      <hr class="divider" />
      <div class="answer-box">
        <span class="tag tag--green">✓ Ответ</span>
        <MathText :text="card.back" class="answer" />
        <MathText v-if="card.explanation" :text="card.explanation" class="detail" />
      </div>
    </template>
  </article>
</template>

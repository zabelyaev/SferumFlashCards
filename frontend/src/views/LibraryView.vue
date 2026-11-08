<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { insertFormulaSnippet, type FormulaSnippet } from '../lib/formulaEditor'
import MathText from '../components/MathText.vue'
import { plural } from '../lib/plural'
import { SUBJECT_VISUAL } from '../lib/subjectVisual'
import { useStudyStore } from '../stores/study'
import { SUBJECT_LABEL, type Card, type Deck, type Subject } from '../types'

const store = useStudyStore()
const route = useRoute()
const router = useRouter()

const expandedDeckId = ref<string | null>(null)
const deckDialogOpen = ref(false)
const cardDialogOpen = ref(false)
const deckError = ref('')
const cardError = ref('')
const operationError = ref('')
const shareMessage = ref('')
const saving = ref(false)
const loadingCards = ref(false)
const editingDeckId = ref<string | null>(null)
const editingCardId = ref<string | null>(null)
const activeDeckId = ref<string | null>(null)
const frontInput = ref<HTMLTextAreaElement | null>(null)
const backInput = ref<HTMLTextAreaElement | null>(null)
const deleteTarget = ref<{ deckId: string; cardId?: string; title: string } | null>(null)

const deckForm = reactive({
  title: '',
  description: '',
  subject: '' as Subject | '',
  grade: '',
  coverColor: '#EBF3FF',
})
const cardForm = reactive({ front: '', back: '', hint: '', explanation: '', imageUrl: '' })
const deckColors = ['#EBF3FF', '#FEF3C7', '#DCFCE7', '#FEE2E2', '#F3E8FF', '#CCFBF1']

const subjects = Object.entries(SUBJECT_LABEL) as [Subject, string][]
const filteredDecks = computed(() => store.decks)
const activeDeck = computed(() => activeDeckId.value ? store.deckById(activeDeckId.value) : undefined)
const cardPosition = computed(() =>
  (activeDeck.value?.cardsCount ?? activeDeck.value?.cards.length ?? 0) + (editingCardId.value ? 0 : 1),
)
onMounted(() => {
  if (store.apiMode) {
    store.loadLibrary().catch((error: unknown) => {
      console.error('Не удалось загрузить библиотеку.', error)
    })
  }
  if (route.query.create === '1') openDeckForm()
})

function openDeckForm(deck?: Deck) {
  editingDeckId.value = deck?.id ?? null
  deckForm.title = deck?.title ?? ''
  deckForm.description = deck?.description ?? ''
  deckForm.subject = deck?.subject ?? ''
  deckForm.grade = deck?.grade ? String(deck.grade) : ''
  deckForm.coverColor = deck?.coverColor?.startsWith('#') ? deck.coverColor : '#EBF3FF'
  deckError.value = ''
  deckDialogOpen.value = true
}

function openCardForm(deckId: string, card?: Card) {
  activeDeckId.value = deckId
  editingCardId.value = card?.id ?? null
  cardForm.front = card?.front ?? ''
  cardForm.back = card?.back ?? ''
  cardForm.hint = card?.hint ?? ''
  cardForm.explanation = card?.explanation ?? ''
  cardForm.imageUrl = card?.imageUrl ?? ''
  cardError.value = ''
  cardDialogOpen.value = true
}

async function insertFormula(target: 'front' | 'back', kind: FormulaSnippet) {
  const input = target === 'front' ? frontInput.value : backInput.value
  const value = cardForm[target]
  const result = insertFormulaSnippet(
    value,
    input?.selectionStart ?? value.length,
    input?.selectionEnd ?? value.length,
    kind,
  )
  cardForm[target] = result.value
  await nextTick()
  const updatedInput = target === 'front' ? frontInput.value : backInput.value
  updatedInput?.focus()
  updatedInput?.setSelectionRange(result.cursor, result.cursor)
}

async function saveDeck() {
  const title = deckForm.title.trim()
  if (!title || title.length > 100) {
    deckError.value = 'Введите название длиной от 1 до 100 символов.'
    return
  }
  if (deckForm.description.length > 300) {
    deckError.value = 'Описание должно быть не длиннее 300 символов.'
    return
  }
  const grade = deckForm.grade ? Number(deckForm.grade) : null
  if (grade !== null && (!Number.isInteger(grade) || grade < 7 || grade > 11)) {
    deckError.value = 'Выберите класс от 7 до 11.'
    return
  }

  const input = {
    title,
    description: deckForm.description,
    subject: deckForm.subject || null,
    grade,
    coverColor: deckForm.coverColor,
  }
  saving.value = true
  try {
    if (editingDeckId.value) {
      if (!await store.updateDeck(editingDeckId.value, input)) {
        deckError.value = 'Эту колоду нельзя редактировать.'
        return
      }
    } else {
      const created = await store.createDeck(input)
      deckDialogOpen.value = false
      openCardForm(created.id)
      return
    }
    deckDialogOpen.value = false
  } catch (error) {
    deckError.value = error instanceof Error ? error.message : 'Не удалось сохранить колоду.'
  } finally {
    saving.value = false
  }
}

async function saveCard(addAnother = false) {
  if (!activeDeckId.value) return
  const front = cardForm.front.trim()
  const back = cardForm.back.trim()
  const imageUrl = cardForm.imageUrl.trim()
  if (!front || !back) {
    cardError.value = 'Заполните вопрос и ответ.'
    return
  }
  if (imageUrl) {
    try {
      if (new URL(imageUrl).protocol !== 'https:') throw new Error('invalid protocol')
    } catch {
      cardError.value = 'Укажите корректную ссылку на изображение.'
      return
    }
  }
  const input = {
    front,
    back,
    hint: cardForm.hint || undefined,
    explanation: cardForm.explanation || undefined,
    imageUrl: imageUrl || undefined,
  }
  saving.value = true
  try {
    const wasEditing = Boolean(editingCardId.value)
    const result = editingCardId.value
      ? await store.updateCard(activeDeckId.value, editingCardId.value, input)
      : await store.createCard(activeDeckId.value, input)
    if (!result) {
      cardError.value = 'Не удалось сохранить карточку. Проверьте, что колода существует и доступна для редактирования.'
      return
    }
    if (addAnother && !wasEditing) {
      cardForm.front = ''
      cardForm.back = ''
      cardForm.hint = ''
      cardForm.explanation = ''
      cardForm.imageUrl = ''
      cardError.value = ''
    } else {
      cardDialogOpen.value = false
    }
  } catch (error) {
    cardError.value = error instanceof Error ? error.message : 'Не удалось сохранить карточку.'
  } finally {
    saving.value = false
  }
}

async function toggleDeck(deck: Deck) {
  if (expandedDeckId.value === deck.id) {
    expandedDeckId.value = null
    return
  }
  expandedDeckId.value = deck.id
  if (!store.apiMode || deck.cards.length >= (deck.cardsCount ?? 0)) return
  loadingCards.value = true
  try {
    await store.loadDeckCards(deck.id)
  } catch (error) {
    console.error('Не удалось загрузить карточки колоды.', error)
  } finally {
    loadingCards.value = false
  }
}

async function confirmDelete() {
  const target = deleteTarget.value
  if (!target) return
  saving.value = true
  try {
    if (target.cardId) await store.deleteCard(target.deckId, target.cardId)
    else if (store.deckById(target.deckId)?.isUserCreated) await store.deleteDeck(target.deckId)
    else await store.removeFromLibrary(target.deckId)
    deleteTarget.value = null
  } catch (error) {
    operationError.value = error instanceof Error ? error.message : 'Не удалось удалить объект.'
    deleteTarget.value = null
  } finally {
    saving.value = false
  }
}

async function copyShareLink(deck: Deck) {
  if (!deck.shareCode) return
  const link = new URL(router.resolve({ name: 'share', params: { shareCode: deck.shareCode } }).href, location.origin)
  try {
    await navigator.clipboard.writeText(link.toString())
    shareMessage.value = 'Ссылка скопирована.'
  } catch (error) {
    console.error('Не удалось скопировать ссылку шаринга.', error)
    shareMessage.value = `Не удалось скопировать. Код колоды: ${deck.shareCode}`
  }
}

function askDelete(deck: Deck, card?: Card) {
  deleteTarget.value = { deckId: deck.id, cardId: card?.id, title: card?.front ?? deck.title }
}

function start(deckId: string) {
  router.push({ name: 'session', params: { deckId } })
}
</script>

<template>
  <div class="library-screen">
    <header class="library-head">
      <button class="icon-circle" type="button" aria-label="На главную" @click="router.push({ name: 'home' })">
        ←
      </button>
      <div class="library-title">
        <h1>Мои колоды</h1>
        <span class="muted">{{ store.decks.length }} {{ plural(store.decks.length, ['колода', 'колоды', 'колод']) }}</span>
      </div>
    </header>
  <p v-if="operationError" class="form-error" role="alert">{{ operationError }}</p>
  <p v-if="shareMessage" class="muted" role="status">{{ shareMessage }}</p>

  <p v-if="store.apiLoading" class="muted" role="status">Загружаем библиотеку…</p>
  <p v-else-if="store.apiError" class="form-error" role="alert">{{ store.apiError }}</p>

  <section v-if="!filteredDecks.length" class="center-note">
    <h2>Пока нет колод</h2>
    <p class="muted">
      Создайте свою колоду и добавьте в неё карточки.
    </p>
    <button class="btn btn--primary" type="button" @click="openDeckForm()">
      Создать колоду
    </button>
  </section>

  <ul v-else class="deck-list library-decks">
    <li v-for="deck in filteredDecks" :key="deck.id" class="library-item">
      <div class="library-row">
        <button
          class="deck library-deck"
          type="button"
          :aria-expanded="expandedDeckId === deck.id"
          @click="toggleDeck(deck)"
        >
          <span
            class="library-deck__icon"
            :style="{
              background: deck.coverColor?.startsWith('#')
                ? deck.coverColor
                : SUBJECT_VISUAL[deck.subject ?? 'other'].background,
              color: SUBJECT_VISUAL[deck.subject ?? 'other'].color,
            }"
            aria-hidden="true"
          >{{ SUBJECT_VISUAL[deck.subject ?? 'other'].glyph }}</span>
          <span class="library-deck__main">
            <span class="deck__title">{{ deck.title }}</span>
            <span class="deck__meta">
              {{ SUBJECT_LABEL[deck.subject ?? 'other'] }}
              · {{ deck.grade ? `${deck.grade} класс` : 'без класса' }}
              · {{ deck.cardsCount ?? deck.cards.length }}
              {{ plural(deck.cardsCount ?? deck.cards.length, ['карточка', 'карточки', 'карточек']) }}
            </span>
            <span v-if="!store.apiMode" class="deck__track" aria-hidden="true">
              <span :style="{ width: `${store.learnedPercent(deck.id)}%` }" />
            </span>
          </span>
          <span class="library-deck__progress">
            <template v-if="!store.apiMode">
              <strong>{{ store.learnedPercent(deck.id) }}%</strong>
              <small>{{ store.learnedPercent(deck.id) === 100 ? 'Освоено' : store.learnedPercent(deck.id) ? 'В процессе' : 'Новая' }}</small>
            </template>
            <small v-else>В библиотеке</small>
          </span>
        </button>
      </div>

      <div v-if="expandedDeckId === deck.id" class="library-details">
        <p v-if="deck.description" class="muted">{{ deck.description }}</p>
        <div class="actions">
          <button class="btn btn--primary" type="button" :disabled="!deck.cards.length" @click="start(deck.id)">
            Учить
          </button>
          <button v-if="deck.isUserCreated" class="btn" type="button" @click="openDeckForm(deck)">
            Изменить колоду
          </button>
          <button v-if="deck.isUserCreated && deck.shareCode" class="btn" type="button" @click="copyShareLink(deck)">
            Поделиться · {{ deck.shareCode }}
          </button>
          <button v-if="deck.isUserCreated" class="btn" type="button" @click="openCardForm(deck.id)">
            + Карточка
          </button>
          <button v-if="deck.isUserCreated" class="btn btn--danger" type="button" @click="askDelete(deck)">
            Удалить колоду
          </button>
          <button v-else-if="store.apiMode" class="btn btn--danger" type="button" @click="askDelete(deck)">
            Убрать из библиотеки
          </button>
        </div>

        <p v-if="loadingCards && expandedDeckId === deck.id" class="muted" role="status">Загружаем карточки…</p>
        <p v-else-if="store.apiError" class="form-error" role="alert">{{ store.apiError }}</p>
        <p v-else-if="!deck.cards.length" class="muted">В колоде пока нет карточек.</p>
        <ul v-else class="card-list">
          <li v-for="card in deck.cards" :key="card.id" class="card-item">
            <div class="card-item__text">
              <strong>{{ card.front }}</strong>
              <MathText :text="card.back" class="muted" />
            </div>
            <div v-if="deck.isUserCreated" class="actions">
              <button class="btn" type="button" @click="openCardForm(deck.id, card)">Изменить</button>
              <button class="btn btn--danger" type="button" @click="askDelete(deck, card)">Удалить</button>
            </div>
          </li>
        </ul>
      </div>
    </li>
  </ul>

    <button v-if="!cardDialogOpen && !deckDialogOpen" class="library-create" type="button" @click="openDeckForm()">
      <span>＋</span> Создать новую колоду
    </button>
  </div>

  <div v-if="deckDialogOpen" class="dialog" role="dialog" aria-modal="true" aria-labelledby="deck-dialog-title">
    <form class="dialog__box editor-form editor-form--screen" @submit.prevent="saveDeck">
      <header class="editor-header">
        <button class="icon-circle" type="button" aria-label="Закрыть" @click="deckDialogOpen = false">×</button>
        <div class="editor-header__title">
          <h2 id="deck-dialog-title">{{ editingDeckId ? 'Изменить колоду' : 'Создание колоды' }}</h2>
          <span v-if="!editingDeckId">Шаг 1 из 2</span>
        </div>
        <span class="editor-header__spacer" />
      </header>
      <div class="deck-icon-picker">
        <span
          class="deck-icon-picker__preview"
          :style="{
            background: deckForm.coverColor,
            color: SUBJECT_VISUAL[deckForm.subject || 'other'].color,
          }"
        >
          {{ SUBJECT_VISUAL[deckForm.subject || 'other'].glyph }}
        </span>
        <div>
          <strong>Значок: {{ SUBJECT_LABEL[deckForm.subject || 'other'] }}</strong>
          <p class="muted">Определяется по выбранному предмету</p>
        </div>
      </div>
      <fieldset class="color-picker">
        <legend>Цвет колоды</legend>
        <button
          v-for="color in deckColors"
          :key="color"
          class="color-picker__swatch"
          :class="{ 'is-selected': deckForm.coverColor === color }"
          :style="{ background: color }"
          type="button"
          :aria-label="`Выбрать цвет ${color}`"
          :aria-pressed="deckForm.coverColor === color"
          @click="deckForm.coverColor = color"
        />
      </fieldset>
      <label class="field">
        <span>Название *</span>
        <input v-model="deckForm.title" maxlength="100" required autofocus />
      </label>
      <label class="field">
        <span>Описание</span>
        <textarea v-model="deckForm.description" maxlength="300" rows="3" />
      </label>
      <label class="field">
        <span>Предмет</span>
        <select v-model="deckForm.subject">
          <option value="">Без предмета</option>
          <option v-for="[value, label] in subjects" :key="value" :value="value">{{ label }}</option>
        </select>
      </label>
      <label class="field">
        <span>Класс</span>
        <select v-model="deckForm.grade">
          <option value="">Без класса</option>
          <option v-for="grade in [7, 8, 9, 10, 11]" :key="grade" :value="String(grade)">{{ grade }} класс</option>
        </select>
      </label>
      <p v-if="deckError" class="form-error" role="alert">{{ deckError }}</p>
      <div class="actions">
        <button class="btn" type="button" @click="deckDialogOpen = false">Отмена</button>
        <button class="btn btn--primary" type="submit" :disabled="saving">
          {{ saving ? 'Сохраняем…' : editingDeckId ? 'Сохранить' : 'Создать колоду и добавить карточки' }}
        </button>
      </div>
    </form>
  </div>

  <div v-if="cardDialogOpen" class="dialog" role="dialog" aria-modal="true" aria-labelledby="card-dialog-title">
    <form class="dialog__box editor-form editor-form--screen" @submit.prevent="saveCard()">
      <header class="editor-header">
        <button class="icon-circle editor-close" type="button" aria-label="Закрыть" @click="cardDialogOpen = false">×</button>
        <div class="editor-header__title">
          <h2 id="card-dialog-title">{{ editingCardId ? 'Изменить карточку' : 'Новая карточка' }}</h2>
          <span v-if="!editingCardId">№ {{ cardPosition }} в колоде</span>
        </div>
        <span class="editor-header__spacer" />
      </header>
      <p class="editor-deck-name">Колода: {{ activeDeck?.title }}</p>
      <label class="field">
        <span>Лицевая сторона · вопрос *</span>
        <textarea ref="frontInput" v-model="cardForm.front" rows="3" maxlength="2000" required placeholder="Введите вопрос или термин" />
      </label>
      <div class="formula-tools" aria-label="Формулы в вопросе">
        <button type="button" aria-label="Вставить формулу" @click="insertFormula('front', 'inline')">$…$</button>
        <button type="button" aria-label="Вставить дробь" @click="insertFormula('front', 'fraction')">a/b</button>
        <button type="button" aria-label="Вставить корень" @click="insertFormula('front', 'root')">√</button>
        <button type="button" aria-label="Вставить степень" @click="insertFormula('front', 'power')">xⁿ</button>
        <button type="button" aria-label="Вставить формулу отдельной строкой" @click="insertFormula('front', 'display')">∑</button>
      </div>
      <div class="preview">
        <strong>Предпросмотр вопроса</strong>
        <MathText v-if="cardForm.front.trim()" :text="cardForm.front" />
        <span v-else class="muted">Предпросмотр появится здесь</span>
      </div>
      <label class="field">
        <span>Изображение к вопросу</span>
        <input v-model="cardForm.imageUrl" type="url" placeholder="Вставьте ссылку на изображение" />
      </label>
      <img
        v-if="cardForm.imageUrl"
        class="editor-media__preview"
        :src="cardForm.imageUrl"
        alt="Предпросмотр изображения к вопросу"
      />
      <label class="field">
        <span>Ответ *</span>
        <textarea ref="backInput" v-model="cardForm.back" rows="3" maxlength="4000" required placeholder="Введите ответ" />
      </label>
      <div class="formula-tools" aria-label="Формулы в ответе">
        <button type="button" aria-label="Вставить формулу" @click="insertFormula('back', 'inline')">$…$</button>
        <button type="button" aria-label="Вставить дробь" @click="insertFormula('back', 'fraction')">a/b</button>
        <button type="button" aria-label="Вставить корень" @click="insertFormula('back', 'root')">√</button>
        <button type="button" aria-label="Вставить степень" @click="insertFormula('back', 'power')">xⁿ</button>
        <button type="button" aria-label="Вставить формулу отдельной строкой" @click="insertFormula('back', 'display')">∑</button>
      </div>
      <div class="preview">
        <strong>Предпросмотр ответа</strong>
        <MathText v-if="cardForm.back.trim()" :text="cardForm.back" />
        <span v-else class="muted">Предпросмотр появится здесь</span>
      </div>
      <label class="field">
        <span>Подсказка</span>
        <textarea v-model="cardForm.hint" rows="2" />
      </label>
      <label class="field">
        <span>Пояснение</span>
        <textarea v-model="cardForm.explanation" rows="2" />
      </label>
      <p v-if="cardError" class="form-error" role="alert">{{ cardError }}</p>
      <div class="editor-actions">
        <button v-if="!editingCardId" class="btn" type="button" :disabled="saving" @click="saveCard(true)">
          {{ saving ? 'Сохраняем…' : '+ Ещё' }}
        </button>
        <button class="btn btn--primary" type="submit" :disabled="saving">
          {{ saving ? 'Сохраняем…' : 'Сохранить' }}
        </button>
      </div>
    </form>
  </div>

  <div v-if="deleteTarget" class="dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-title">
    <div class="dialog__box">
      <h2 id="delete-title">Подтвердите удаление</h2>
      <p>Удалить «{{ deleteTarget.title }}»? Это действие нельзя отменить.</p>
      <div class="actions">
        <button class="btn" type="button" @click="deleteTarget = null">Отмена</button>
        <button class="btn btn--danger" type="button" :disabled="saving" @click="confirmDelete">
          {{ saving ? 'Удаляем…' : 'Удалить' }}
        </button>
      </div>
    </div>
  </div>
</template>

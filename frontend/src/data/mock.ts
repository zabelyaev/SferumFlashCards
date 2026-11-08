import type { Deck } from '../types'

// String.raw — чтобы не удваивать обратные слэши в LaTeX
const t = String.raw

export const MOCK_DECKS: Deck[] = [
  {
    id: 'phys-kinematics',
    title: 'Кинематика: формулы движения',
    subject: 'physics',
    grade: 9,
    cards: [
      {
        id: 'k1',
        deckId: 'phys-kinematics',
        tag: 'Формула',
        front: t`Скорость при равноускоренном движении`,
        back: t`$$v = v_0 + at$$`,
        hint: t`Начальная скорость плюс то, что набрали за время $t$`,
        explanation: t`$v_0$ — начальная скорость, $a$ — ускорение, $t$ — время`,
      },
      {
        id: 'k2',
        deckId: 'phys-kinematics',
        tag: 'Формула',
        front: t`Перемещение при равноускоренном движении`,
        back: t`$$s = v_0 t + \frac{at^2}{2}$$`,
        explanation: t`$s$ — перемещение, $v_0$ — начальная скорость, $a$ — ускорение, $t$ — время`,
      },
      {
        id: 'k3',
        deckId: 'phys-kinematics',
        tag: 'Формула',
        front: t`Связь скоростей и перемещения без времени`,
        back: t`$$v^2 = v_0^2 + 2as$$`,
        hint: t`В формуле нет $t$`,
      },
      {
        id: 'k4',
        deckId: 'phys-kinematics',
        tag: 'Формула',
        front: t`Центростремительное ускорение`,
        back: t`$$a_c = \frac{v^2}{R}$$`,
        explanation: t`$v$ — линейная скорость, $R$ — радиус окружности`,
      },
      {
        id: 'k5',
        deckId: 'phys-kinematics',
        tag: 'Формула',
        front: t`Связь периода и частоты вращения`,
        back: t`$$T = \frac{1}{\nu}$$`,
        explanation: t`$T$ — период (с), $\nu$ — частота (Гц)`,
      },
    ],
  },
  {
    id: 'alg-quadratic',
    title: 'Квадратные уравнения и сокращённое умножение',
    subject: 'algebra',
    grade: 8,
    cards: [
      {
        id: 'q1',
        deckId: 'alg-quadratic',
        tag: 'Формула',
        front: t`Дискриминант уравнения $ax^2 + bx + c = 0$`,
        back: t`$$D = b^2 - 4ac$$`,
      },
      {
        id: 'q2',
        deckId: 'alg-quadratic',
        tag: 'Формула',
        front: t`Корни квадратного уравнения через дискриминант`,
        back: t`$$x_{1,2} = \frac{-b \pm \sqrt{D}}{2a}$$`,
        hint: t`Если $D < 0$, действительных корней нет`,
      },
      {
        id: 'q3',
        deckId: 'alg-quadratic',
        tag: 'Формула',
        front: t`Теорема Виета для $x^2 + px + q = 0$`,
        back: t`$$x_1 + x_2 = -p, \qquad x_1 x_2 = q$$`,
      },
      {
        id: 'q4',
        deckId: 'alg-quadratic',
        tag: 'Формула',
        front: t`Разность квадратов`,
        back: t`$$a^2 - b^2 = (a - b)(a + b)$$`,
      },
      {
        id: 'q5',
        deckId: 'alg-quadratic',
        tag: 'Формула',
        front: t`Квадрат суммы`,
        back: t`$$(a + b)^2 = a^2 + 2ab + b^2$$`,
      },
    ],
  },
  {
    id: 'hist-dates',
    title: 'Ключевые даты истории России',
    subject: 'history',
    grade: 9,
    cards: [
      { id: 'h1', deckId: 'hist-dates', tag: 'Дата', front: 'Крещение Руси', back: '988 год', explanation: 'При князе Владимире Святославиче' },
      { id: 'h2', deckId: 'hist-dates', tag: 'Дата', front: 'Ледовое побоище', back: '1242 год' },
      { id: 'h3', deckId: 'hist-dates', tag: 'Дата', front: 'Куликовская битва', back: '1380 год', explanation: 'Дмитрий Донской против войск Мамая' },
      { id: 'h4', deckId: 'hist-dates', tag: 'Дата', front: 'Стояние на реке Угре', back: '1480 год', explanation: 'Конец ордынского владычества' },
      { id: 'h5', deckId: 'hist-dates', tag: 'Дата', front: 'Избрание на царство Михаила Романова', back: '1613 год', hint: 'Конец Смутного времени' },
    ],
  },
]

export const MOCK_CATALOG_DECKS: Deck[] = [
  {
    id: 'geo-area-volume',
    title: 'Площади и объёмы: основные формулы',
    subject: 'geometry',
    grade: 8,
    description: 'Формулы площадей основных фигур и объёмов тел.',
    cards: [
      {
        id: 'gv1',
        deckId: 'geo-area-volume',
        tag: 'Формула',
        front: 'Площадь треугольника через основание и высоту',
        back: String.raw`$$S = \frac{ah}{2}$$`,
      },
      {
        id: 'gv2',
        deckId: 'geo-area-volume',
        tag: 'Формула',
        front: 'Объём прямоугольного параллелепипеда',
        back: String.raw`$$V = abc$$`,
      },
    ],
  },
]

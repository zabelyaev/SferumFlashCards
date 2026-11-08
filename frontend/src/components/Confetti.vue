<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const canvas = ref<HTMLCanvasElement | null>(null)
let raf = 0

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const el = canvas.value
  const ctx = el?.getContext('2d')
  if (!el || !ctx) return

  const dpr = window.devicePixelRatio || 1
  const w = (el.width = el.clientWidth * dpr)
  const h = (el.height = el.clientHeight * dpr)
  const colors = ['#0077FF', '#FF9E00', '#27AE60', '#FF334B', '#19191A']
  const pieces = Array.from({ length: 90 }, () => ({
    x: Math.random() * w,
    y: -Math.random() * h * 0.6,
    s: (4 + Math.random() * 6) * dpr,
    vy: (2 + Math.random() * 3) * dpr,
    vx: (Math.random() - 0.5) * 2 * dpr,
    r: Math.random() * Math.PI,
    vr: (Math.random() - 0.5) * 0.3,
    c: colors[Math.floor(Math.random() * colors.length)],
  }))

  const t0 = performance.now()
  const tick = (now: number) => {
    ctx.clearRect(0, 0, w, h)
    for (const p of pieces) {
      p.x += p.vx
      p.y += p.vy
      p.r += p.vr
      ctx.save()
      ctx.translate(p.x, p.y)
      ctx.rotate(p.r)
      ctx.fillStyle = p.c
      ctx.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2)
      ctx.restore()
    }
    if (now - t0 < 2800) raf = requestAnimationFrame(tick)
    else ctx.clearRect(0, 0, w, h)
  }
  raf = requestAnimationFrame(tick)
})

onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <canvas ref="canvas" class="confetti" aria-hidden="true" />
</template>

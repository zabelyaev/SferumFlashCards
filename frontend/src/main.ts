import { createApp } from 'vue'
import { createPinia } from 'pinia'
import '@fontsource-variable/inter/wght.css'
import 'katex/dist/katex.min.css'
import './styles.css'
import App from './App.vue'
import { router } from './router'

createApp(App).use(createPinia()).use(router).mount('#app')

import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import CatalogView from './views/CatalogView.vue'
import LibraryView from './views/LibraryView.vue'
import ProfileView from './views/ProfileView.vue'
import SettingsView from './views/SettingsView.vue'
import ShareView from './views/ShareView.vue'
import SessionView from './views/SessionView.vue'
import { isMaxLaunchHash } from './lib/maxLaunch'

// Hash-режим: внутри WebView мини-приложения нет серверной маршрутизации (ТЗ 5.1)
if (isMaxLaunchHash(window.location.hash)) {
  window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}#/`)
}

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/catalog', name: 'catalog', component: CatalogView },
    { path: '/library', name: 'library', component: LibraryView },
    { path: '/profile', name: 'profile', component: ProfileView },
    { path: '/settings', name: 'settings', component: SettingsView },
    { path: '/share/:shareCode', name: 'share', component: ShareView, props: true },
    { path: '/session/:deckId', name: 'session', component: SessionView, props: true },
  ],
})

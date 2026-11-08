/// <reference types="vite/client" />

declare const __API_ENABLED__: boolean
declare const __API_ROOT__: string
declare const __API_APP_KEY__: string
declare const __DEV_VK_USER_ID__: string
declare const __FALLBACK_VK_USER_ID__: string

interface MaxWebApp {
  initData: string
  initDataUnsafe?: {
    user?: {
      id?: number
      first_name?: string
    }
  }
}

interface Window {
  WebApp?: MaxWebApp
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

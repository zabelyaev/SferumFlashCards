import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, '.', '')
  const apiConfigured = Boolean(env.API_TARGET && env.API_APP_KEY)
  const devApiConfigured = apiConfigured && Boolean(env.API_DEV_USER_ID)
  const apiEnabled = mode !== 'test' && env.VITE_USE_API === 'true' &&
    (command === 'build' ? apiConfigured : devApiConfigured)

  if (mode !== 'test' && env.VITE_USE_API === 'true' && !apiEnabled) {
    const required = command === 'build'
      ? 'API_TARGET and API_APP_KEY'
      : 'API_TARGET, API_APP_KEY, and API_DEV_USER_ID'
    throw new Error(`API mode requires ${required} in .env.local.`)
  }

  const apiRoot = apiEnabled && command === 'build'
    ? `${env.API_TARGET.replace(/\/+$/, '')}/api/v1`
    : '/backend-api/api/v1'

  return {
    plugins: [vue()],
    base: './',
    define: {
      __API_ENABLED__: JSON.stringify(apiEnabled),
      __API_ROOT__: JSON.stringify(apiRoot),
      __API_APP_KEY__: JSON.stringify(apiEnabled ? env.API_APP_KEY : ''),
      __DEV_VK_USER_ID__: JSON.stringify(command === 'serve' && apiEnabled ? env.API_DEV_USER_ID : ''),
      __FALLBACK_VK_USER_ID__: JSON.stringify(command === 'build' && apiEnabled ? env.API_DEV_USER_ID : ''),
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: apiEnabled
        ? {
            '/backend-api': {
              target: env.API_TARGET,
              changeOrigin: true,
              rewrite: (path) => path.replace(/^\/backend-api/, ''),
              configure: (proxy) => {
                proxy.on('proxyReq', (request) => {
                  request.setHeader('X-App-Key', env.API_APP_KEY)
                })
              },
            },
          }
        : undefined,
    },
    test: {
      environment: 'node',
      include: ['src/**/*.test.ts'],
    },
  }
})

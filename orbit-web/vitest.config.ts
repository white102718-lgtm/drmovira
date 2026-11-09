import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  test: {
    environment: 'jsdom',
    include: ['tests/orbit/**/*.test.ts'],
    setupFiles: ['tests/orbit/setup.ts'],
    reporters: ['default'],
    // 大表格组件占用较多DOM资源，限制工作进程避免并发争用触及原5秒用例上限。
    maxWorkers: 4,
  },
})

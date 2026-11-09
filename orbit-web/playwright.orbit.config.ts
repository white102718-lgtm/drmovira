import { defineConfig } from '@playwright/test'
import path from 'node:path'

if (!process.env.ORBIT_E2E_BACKEND_URL || !process.env.ORBIT_E2E_FIXTURE_PASSWORD) {
  throw new Error('请通过后端独立浏览器fixture运行，不能连接未知服务或使用真实账号')
}
const output = path.resolve(process.env.ORBIT_E2E_OUTPUT || '')
if (output !== path.resolve(process.cwd(), '../.runtime/browser-it')) {
  throw new Error('浏览器产物只能写入本项目独立测试目录')
}
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: ['orbit-configuration.spec.ts', 'orbit-scopes.spec.ts', 'orbit-audit.spec.ts'],
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [['list'], ['json', { outputFile: path.join(output, 'playwright-result.json') }]],
  outputDir: path.join(output, 'artifacts'),
  use: {
    baseURL: 'http://127.0.0.1:18082',
    headless: true,
    trace: 'off',
    video: 'off',
    screenshot: 'off',
  },
  projects: [
    { name: 'desktop-1440', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'wide-1920', use: { viewport: { width: 1920, height: 1080 } } },
    { name: 'mobile-390', use: { viewport: { width: 390, height: 844 } } },
  ],
  webServer: {
    command: 'pnpm dev --port 18082',
    url: 'http://127.0.0.1:18082/login',
    reuseExistingServer: false,
    timeout: 60_000,
  },
})

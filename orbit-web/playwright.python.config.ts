import { defineConfig } from '@playwright/test'
import path from 'node:path'

/** Python真实后端专用夹具；与现有用户预览及旧Java浏览器测试端口隔离。 */
if (
  process.env.ORBIT_E2E_BACKEND_URL !== 'http://127.0.0.1:18083' ||
  !process.env.ORBIT_E2E_FIXTURE_PASSWORD
) {
  throw new Error('请通过Python独立浏览器夹具运行')
}
const output = path.resolve(process.env.ORBIT_E2E_OUTPUT || '')
if (output !== path.resolve(process.cwd(), '../.runtime/python-browser-it')) {
  throw new Error('Python浏览器证据目录不在独立工作区')
}
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: [
    'orbit-python-configuration.spec.ts',
    ...(process.env.ORBIT_E2E_METRICS_FIXTURE ? ['orbit-metrics.spec.ts'] : []),
    ...(process.env.ORBIT_E2E_IDENTITY_PUBLICATION_FIXTURE
      ? ['orbit-python-identity-publication.spec.ts']
      : []),
    ...(process.env.ORBIT_E2E_IDENTITY_SUMMARY_FIXTURE
      ? ['orbit-python-identity-summary.spec.ts']
      : []),
    ...(process.env.ORBIT_E2E_MATERIAL_SCANNER_CONFIGURATION === '1'
      ? ['orbit-python-scanner-configuration.spec.ts']
      : []),
    ...(process.env.ORBIT_E2E_TASK_CORE === '1' ? ['orbit-python-tasks.spec.ts'] : []),
    ...(process.env.ORBIT_E2E_TASK_EVENTS === '1' ? ['orbit-python-task-events.spec.ts'] : []),
    'orbit-python-teams.spec.ts',
    'orbit-python-roles.spec.ts',
    'orbit-python-users.spec.ts',
    'orbit-python-native-directory.spec.ts',
    'orbit-python-authentication.spec.ts',
    ...(process.env.ORBIT_E2E_CHANNELS === '1' ? ['orbit-python-channels.spec.ts'] : []),
    ...(process.env.ORBIT_E2E_OWNERS500 === '1' ? ['orbit-python-channel-owners500.spec.ts'] : []),
    ...(process.env.ORBIT_E2E_ACCOUNTS === '1' ? ['orbit-python-accounts.spec.ts'] : []),
    ...(process.env.ORBIT_E2E_ACCOUNT_COMMAND === '1'
      ? ['orbit-python-account-command.spec.ts']
      : []),
    ...(process.env.ORBIT_E2E_SCOPES === '1' ? ['orbit-python-scopes.spec.ts'] : []),
    ...(process.env.ORBIT_E2E_LAUNCH === '1' ? ['orbit-python-launch.spec.ts'] : []),
    ...(process.env.ORBIT_E2E_METRIC_PROFILES === '1'
      ? ['orbit-python-metric-profiles.spec.ts']
      : []),
    ...(process.env.ORBIT_E2E_LAUNCH_METRIC_PROFILES === '1'
      ? ['orbit-python-launch-metric-profiles.spec.ts']
      : []),
    ...(process.env.ORBIT_E2E_VENDOR_ALIAS === '1' ? ['orbit-python-vendor-alias.spec.ts'] : []),
    ...(process.env.ORBIT_E2E_MATERIALS === '1' ? ['orbit-python-materials.spec.ts'] : []),
    ...(process.env.ORBIT_E2E_MATERIAL_SECURITY === '1'
      ? ['orbit-python-material-security.spec.ts']
      : []),
  ],
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [['list'], ['json', { outputFile: path.join(output, 'playwright-result.json') }]],
  outputDir: path.join(output, 'artifacts'),
  use: {
    baseURL: 'http://127.0.0.1:18084',
    headless: true,
    trace: 'off',
    video: 'off',
    screenshot: 'off',
    launchOptions: {
      args: [
        '--host-resolver-rules=MAP app.fixture.example 127.0.0.1, MAP orbit-idp.fixture.example 127.0.0.1',
        '--no-proxy-server',
      ],
    },
  },
  projects: [
    { name: 'desktop-1440', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'wide-1920', use: { viewport: { width: 1920, height: 1080 } } },
    { name: 'mobile-390', use: { viewport: { width: 390, height: 844 } } },
  ],
  webServer: {
    command: 'pnpm dev --port 18084 --config vite.python.config.js',
    url: 'http://127.0.0.1:18084/login',
    reuseExistingServer: false,
    timeout: 60_000,
  },
})

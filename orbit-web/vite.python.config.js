import { defineConfig, mergeConfig } from 'vite'
import path from 'node:path'
import baseConfig from './vite.config.js'

/** Python验收与现有Java预览隔离预构建缓存，不改变原预览配置或进程。 */
export default defineConfig((environment) => {
  if (process.env.ORBIT_E2E_BACKEND_URL !== 'http://127.0.0.1:18083') {
    throw new Error('Python验收配置只能由独立夹具启动')
  }
  return mergeConfig(baseConfig(environment), {
    cacheDir: path.resolve(__dirname, 'node_modules/.vite-orbit-python-it'),
    // 一次性登录凭据在内存消费；隔离验收不需要热更新重载页面或连接虚拟域名的HMR。
    server: { hmr: false },
  })
})

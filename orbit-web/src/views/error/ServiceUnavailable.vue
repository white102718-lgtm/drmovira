<template>
  <main class="service-recovery">
    <el-result icon="warning" title="暂时无法加载页面" sub-title="服务暂时不可用或网络连接中断，你的登录信息已保留。请稍后重试。">
      <template #extra><el-button type="primary" @click="retry">重新加载</el-button></template>
    </el-result>
  </main>
</template>
<script setup>
import { useRoute, useRouter } from 'vue-router'
const route = useRoute()
const router = useRouter()
function retry() {
  const value = route.query.redirect
  const safe = typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') && !/[\\\x00-\x20]/.test(value) && !value.startsWith('/service-unavailable')
  router.replace(safe ? value : '/')
}
</script>
<style scoped>
.service-recovery { min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #f5f7fa; }
</style>

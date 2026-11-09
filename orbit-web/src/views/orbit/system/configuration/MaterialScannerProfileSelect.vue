<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { listMaterialScannerProfiles, type MaterialScannerProfile } from '@/api/orbit/configuration'

const props = defineProps<{ modelValue: string | number }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const options = ref<MaterialScannerProfile[]>([])
const loading = ref(false)
const error = ref('')
let epoch = 0
const unknown = computed(
  () => String(props.modelValue) && !options.value.some((item) => item.id === props.modelValue),
)

/** 失败保留已有选择；响应序号防关闭/刷新后的迟到结果覆盖当前界面。 */
async function refresh() {
  const current = ++epoch
  loading.value = true
  error.value = ''
  try {
    const result = await listMaterialScannerProfiles()
    if (current === epoch) options.value = result
  } catch {
    if (current === epoch) error.value = '扫描候选读取失败，请刷新重试'
  } finally {
    if (current === epoch) loading.value = false
  }
}
onMounted(refresh)
onBeforeUnmount(() => {
  epoch += 1
})
</script>

<template>
  <div class="scanner-profile-control">
    <el-select
      :model-value="modelValue"
      :loading="loading"
      aria-label="服务端扫描候选"
      placeholder="选择服务端已启动的扫描候选"
      @update:model-value="emit('update:modelValue', String($event))"
    >
      <el-option v-if="unknown" :value="modelValue" label="已保存的候选当前不可用" disabled />
      <el-option
        v-for="item in options"
        :key="item.id"
        :value="item.id"
        :label="item.availability === 'READY' ? item.label : `${item.label}（不可用）`"
        :disabled="item.availability !== 'READY'"
      />
    </el-select>
    <el-button :loading="loading" :disabled="loading" @click="refresh">刷新候选</el-button>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-else-if="!loading && !options.length">暂无可用扫描候选，请联系系统管理员配置。</p>
  </div>
</template>

<style scoped>
.scanner-profile-control {
  width: 100%;
}
.scanner-profile-control .el-select {
  width: calc(100% - 112px);
  margin-right: 12px;
}
.scanner-profile-control p {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
}
</style>

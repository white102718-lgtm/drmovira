<template>
  <el-dialog
    v-model="visible"
    title="上传素材"
    :style="{ maxWidth: 'calc(100vw - 24px)' }"
    width="760px"
    :close-on-click-modal="false"
    :close-on-press-escape="!busy"
    :before-close="close"
  >
    <el-alert
      title="每批最多50个文件；JPEG/PNG不超过20MiB，MP4不超过500MiB。上传后须扫描和处理，达到READY才可使用。"
      type="info"
      :closable="false"
    />
    <el-form label-position="top" class="upload-form">
      <el-form-item label="分类（必填）"
        ><el-select v-model="category" :disabled="busy || started" filterable
          ><el-option
            v-for="item in categories.filter((x) => x.state === 'ENABLED')"
            :key="item.id"
            :value="item.id"
            :label="item.name" /></el-select
      ></el-form-item>
      <el-form-item label="标签（最多20个）"
        ><el-select
          v-model="selectedTags"
          multiple
          filterable
          :multiple-limit="20"
          :disabled="busy || started"
          ><el-option
            v-for="item in tags.filter((x) => x.state === 'ENABLED')"
            :key="item.id"
            :value="item.id"
            :label="item.group ? `${item.group} / ${item.name}` : item.name" /></el-select
      ></el-form-item>
      <el-form-item label="文件"
        ><input
          aria-label="选择素材文件"
          type="file"
          multiple
          accept="image/jpeg,image/png,video/mp4"
          :disabled="busy || started"
          @change="selectFiles"
      /></el-form-item>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table :data="jobs" max-height="380" empty-text="请先选择文件">
      <el-table-column label="素材名称" min-width="180"
        ><template #default="{ row }"
          ><el-input
            v-model="row.name"
            maxlength="200"
            :disabled="busy || started"
            aria-label="素材名称" /></template
      ></el-table-column>
      <el-table-column label="大小" width="100"
        ><template #default="{ row }"
          >{{ (row.file.size / 1024 / 1024).toFixed(2) }}MiB</template
        ></el-table-column
      >
      <el-table-column label="进度和结果" min-width="180"
        ><template #default="{ row }"
          ><el-progress :percentage="row.progress" /><span>{{ row.message }}</span></template
        ></el-table-column
      >
    </el-table>
    <template #footer
      ><el-button :disabled="busy" @click="close()">关闭</el-button
      ><el-button v-if="busy" @click="abort?.abort()">停止剩余上传</el-button
      ><el-button
        type="primary"
        :loading="busy"
        :disabled="!jobs.length || !category"
        @click="submit"
        >{{ started ? '重试未完成项' : '开始上传' }}</el-button
      ></template
    >
  </el-dialog>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { materialApi, type MaterialTaxonomy, type MaterialUploadState } from '@/api/orbit/materials'
const props = defineProps<{
  modelValue: boolean
  csrf: string
  categories: MaterialTaxonomy[]
  tags: MaterialTaxonomy[]
  defaultCategory: string
}>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; completed: [] }>()
const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
const category = ref(props.defaultCategory),
  selectedTags = ref<string[]>([]),
  error = ref(''),
  busy = ref(false),
  started = ref(false)
interface Job {
  file: File
  name: string
  progress: number
  message: string
  done: boolean
  state: MaterialUploadState
}
const jobs = ref<Job[]>([])
let abort: AbortController | undefined
function selectFiles(event: Event) {
  error.value = ''
  const files = Array.from((event.target as HTMLInputElement).files ?? [])
  if (files.length > 50) {
    error.value = '每批不能超过50个文件'
    jobs.value = []
    return
  }
  jobs.value = files.map((file) => ({
    file,
    name: Array.from(file.name.replace(/\.[^.]+$/, '').normalize('NFC'))
      .slice(0, 100)
      .join(''),
    progress: 0,
    message: '等待上传',
    done: false,
    state: {},
  }))
}
async function submit() {
  if (busy.value) return
  if (jobs.value.some((job) => !job.name.trim() || [...job.name.trim()].length > 100)) {
    error.value = '每个素材名称必须为1至100字符'
    return
  }
  busy.value = true
  started.value = true
  error.value = ''
  abort = new AbortController()
  try {
    for (const job of jobs.value) {
      if (job.done || abort.signal.aborted) continue
      try {
        job.message = '计算摘要并上传'
        const asset = await materialApi.upload(
          job.file,
          { name: job.name.trim(), category_id: category.value, tag_ids: selectedTags.value },
          props.csrf,
          (n) => {
            job.progress = n
          },
          job.state,
          abort.signal,
        )
        job.done = true
        job.message = asset.state === 'READY' ? '已复用可用素材' : '上传完成，等待处理'
      } catch (failure) {
        job.message = abort.signal.aborted
          ? '已停止，可重试'
          : failure instanceof Error
            ? failure.message
            : '上传失败，可重试'
      }
    }
    emit('completed')
  } finally {
    busy.value = false
  }
}
function close(done?: () => void) {
  if (busy.value) return
  emit('update:modelValue', false)
  done?.()
}
onBeforeUnmount(() => abort?.abort())
</script>
<style scoped>
.upload-form {
  margin-top: 16px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
}
.upload-form :deep(.el-select) {
  width: 100%;
}
@media (max-width: 600px) {
  .upload-form {
    grid-template-columns: 1fr;
  }
}
</style>

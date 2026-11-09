<template>
  <el-dialog
    :title="title"
    v-model="visible"
    :width="width"
    :class="dialogClass"
    append-to-body
    @close="handleClose"
  >
    <el-upload
      ref="uploadRef"
      :limit="1"
      accept=".xlsx, .xls"
      :headers="headers"
      :action="uploadUrl"
      :disabled="isUploading"
      :on-progress="handleProgress"
      :on-change="handleFileChange"
      :on-remove="handleFileRemove"
      :on-success="handleSuccess"
      :on-error="handleError"
      :auto-upload="false"
      drag
    >
      <el-icon class="el-icon--upload"><upload-filled /></el-icon>
      <div class="el-upload__text">将文件拖到此处，或<em>点击上传</em></div>
      <template #tip>
        <div class="el-upload__tip text-center">
          <div class="el-upload__tip">
            <el-checkbox v-model="updateSupport"> {{ updateSupportLabel }} </el-checkbox>
          </div>
          <span>仅允许导入xls、xlsx格式文件。</span>
          <el-link
            v-if="templateUrl"
            type="primary"
            underline="never"
            style="font-size: 12px; vertical-align: baseline"
            @click="handleDownloadTemplate"
            >下载模板</el-link
          >
        </div>
      </template>
    </el-upload>
    <template #footer>
      <div class="dialog-footer">
        <el-button type="primary" :loading="isUploading" @click="handleSubmit">确 定</el-button>
        <el-button @click="visible = false">取 消</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { h } from 'vue'
import { getToken } from '@/utils/auth'

const { proxy } = getCurrentInstance()

const props = defineProps({
  // 业务入口可单独约束弹窗尺寸，不影响其他原导入窗口。
  dialogClass: { type: String, default: '' },
  // 对话框标题
  title: {
    type: String,
    default: '数据导入',
  },
  // 对话框宽度
  width: {
    type: String,
    default: '400px',
  },
  // 上传接口地址（必传）
  action: {
    type: String,
    required: true,
  },
  // 模板下载接口地址，不传则不显示下载模板链接
  templateAction: {
    type: String,
    default: '',
  },
  // 模板文件名前缀
  templateFileName: {
    type: String,
    default: 'template',
  },
  // 覆盖更新勾选框的说明文字
  updateSupportLabel: {
    type: String,
    default: '是否更新已经存在的数据',
  },
})

const emit = defineEmits(['success'])

const uploadRef = ref(null)
const visible = ref(false)
const selectedFile = ref(null)
const isUploading = ref(false)
const updateSupport = ref(false)
const headers = ref({})

const uploadUrl = computed(() => {
  return (
    import.meta.env.VITE_APP_BASE_API +
    props.action +
    '?updateSupport=' +
    (updateSupport.value ? 1 : 0)
  )
})

const templateUrl = computed(() => !!props.templateAction)

// 打开对话框（供父组件通过 ref 调用）
function open() {
  // 原页面可能被缓存；再次打开时使用当前会话，不能沿用组件初次加载的旧令牌。
  headers.value = { Authorization: 'Bearer ' + getToken() }
  updateSupport.value = false
  isUploading.value = false
  visible.value = true
  nextTick(() => {
    selectedFile.value = null
    uploadRef.value?.clearFiles()
  })
}

// 关闭时清理
function handleClose() {
  isUploading.value = false
  selectedFile.value = null
  uploadRef.value?.clearFiles()
}

// 下载模板
function handleDownloadTemplate() {
  proxy.download(props.templateAction, {}, `${props.templateFileName}_${new Date().getTime()}.xlsx`)
}

// 上传进度
function handleProgress() {
  isUploading.value = true
}

/** 文件选择处理 */
const handleFileChange = (file, fileList) => {
  selectedFile.value = file
}

/** 文件删除处理 */
const handleFileRemove = (file, fileList) => {
  selectedFile.value = null
}

// 上传成功
function handleSuccess(response) {
  isUploading.value = false
  if (response?.code !== 200) {
    // HTTP200也可能是业务拒绝；保留窗口和文件，不发出成功刷新事件。
    proxy.$modal.msgError(response?.msg || '导入失败，请检查后重试')
    nextTick(restoreSelectedFileForRetry)
    return
  }
  visible.value = false
  selectedFile.value = null
  uploadRef.value?.clearFiles()
  // 结果可能包含导入的登录名，必须按纯文本展示，不能解释为HTML。
  proxy.$alert(
    h(
      'div',
      {
        style: {
          overflow: 'auto',
          maxHeight: '70vh',
          whiteSpace: 'pre-wrap',
          overflowWrap: 'anywhere',
        },
      },
      response.msg || '导入已完成',
    ),
    '导入结果',
  )
  emit('success')
}

function handleError() {
  isUploading.value = false
  proxy.$modal.msgError('导入请求失败，请检查网络后重试')
  nextTick(restoreSelectedFileForRetry)
}

/** ElUpload将HTTP成功/网络失败文件移出ready状态，保留原文件并恢复显式重试能力。 */
function restoreSelectedFileForRetry() {
  const raw = selectedFile.value?.raw
  if (!visible.value || !raw) return
  uploadRef.value?.clearFiles()
  uploadRef.value?.handleStart(raw)
}

// 提交上传
async function handleSubmit() {
  if (isUploading.value) return
  const file = selectedFile.value
  if (
    !file ||
    file.length === 0 ||
    (!file.name.toLowerCase().endsWith('.xls') && !file.name.toLowerCase().endsWith('.xlsx'))
  ) {
    proxy.$modal.msgError('请选择后缀为 “xls”或“xlsx”的文件。')
    return
  }
  headers.value = { Authorization: 'Bearer ' + getToken() }
  isUploading.value = true
  await nextTick()
  uploadRef.value.submit()
}

defineExpose({ open })
</script>

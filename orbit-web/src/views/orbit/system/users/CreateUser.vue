<template>
  <el-dialog
    class="user-create-dialog"
    destroy-on-close
    v-model="visible"
    :title="editing ? '编辑人员' : '新增人员'"
    width="min(640px, calc(100vw - 24px))"
    :close-on-click-modal="false"
    :close-on-press-escape="!saving && !opening"
    :show-close="!saving && !opening"
  >
    <el-alert
      v-if="!editing || editing.identity_status === 'UNVERIFIED'"
      title="该人员尚未验证身份，不能直接启用；此操作不会发送邀请。"
      type="info"
      :closable="false"
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-button v-if="editing && error" :disabled="saving" @click="reloadPerson"
      >重新读取人员</el-button
    >
    <el-form
      ref="form"
      :model="draft"
      :rules="rules"
      label-position="top"
      :disabled="saving || opening"
      @submit.prevent="save"
    >
      <el-form-item label="姓名" prop="display_name"
        ><el-input v-model="draft.display_name"
      /></el-form-item>
      <el-form-item label="昵称" prop="nickname"
        ><el-input v-model="draft.nickname"
      /></el-form-item>
      <el-form-item label="邮箱" prop="email"><el-input v-model="draft.email" /></el-form-item>
      <el-form-item label="联系方式" prop="phone"><el-input v-model="draft.phone" /></el-form-item>
      <el-form-item label="所属团队" prop="team_id">
        <ReferenceSelect
          :model-value="draft.team_id"
          kind="TEAM"
          label="所属团队"
          :disabled="ownOrProtected"
          @update:model-value="(value) => (draft.team_id = String(value))"
        />
      </el-form-item>
      <el-form-item label="功能角色" prop="role_ids">
        <ReferenceSelect
          :model-value="draft.role_ids"
          kind="ROLE"
          label="功能角色"
          :disabled="ownOrProtected"
          multiple
          :limit="20"
          @update:model-value="(value) => (draft.role_ids = Array.isArray(value) ? value : [])"
        />
      </el-form-item>
      <el-form-item label="数据角色" prop="data_role">
        <el-select
          v-model="draft.data_role"
          aria-label="数据角色"
          :disabled="ownOrProtected"
          @change="draft.managed_team_ids = []"
        >
          <el-option label="普通用户" value="USER" /><el-option
            label="团队管理员"
            value="TEAM_ADMIN"
          />
          <el-option label="超级管理员" value="SUPER_ADMIN" />
        </el-select>
      </el-form-item>
      <el-form-item
        v-if="draft.data_role === 'TEAM_ADMIN'"
        label="管理团队"
        prop="managed_team_ids"
      >
        <ReferenceSelect
          :model-value="draft.managed_team_ids"
          kind="TEAM"
          label="管理团队"
          :disabled="ownOrProtected"
          multiple
          :limit="500"
          @update:model-value="
            (value) => (draft.managed_team_ids = Array.isArray(value) ? value : [])
          "
        />
      </el-form-item>
      <el-form-item label="账号状态" prop="status">
        <el-select v-model="draft.status" aria-label="账号状态" :disabled="protectedUser">
          <el-option
            v-if="!editing || editing.identity_status === 'UNVERIFIED'"
            label="待邀请验证"
            value="INVITED"
          />
          <el-option
            v-if="editing && editing.identity_status !== 'UNVERIFIED'"
            label="启用"
            value="ENABLED"
          /><el-option label="停用" value="DISABLED" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button :disabled="saving || opening" @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving || opening" @click="save">{{
        editing ? '保存修改' : '保存人员'
      }}</el-button>
    </template>
  </el-dialog>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { useRouter } from 'vue-router'
import { removeToken } from '@/utils/auth'
import { userApi, type OrbitUser, type UserWrite } from '@/api/orbit/users'
import ReferenceSelect from './ReferenceSelect.vue'
const emit = defineEmits<{ created: [value: OrbitUser] }>()
const router = useRouter()
const editing = ref<OrbitUser | null>(null),
  actorId = ref(''),
  protectedIds = ref<string[]>([])
const protectedUser = computed(
  () => !!editing.value && protectedIds.value.includes(editing.value.id),
)
const ownOrProtected = computed(() => protectedUser.value || editing.value?.id === actorId.value)
const visible = ref(false),
  opening = ref(false),
  saving = ref(false),
  error = ref(''),
  csrf = ref('')
const form = ref<FormInstance>()
const blank = (): UserWrite => ({
  display_name: '',
  nickname: '',
  email: '',
  phone: '',
  team_id: '',
  role_ids: [],
  data_role: 'USER',
  managed_team_ids: [],
  status: 'INVITED',
})
const draft = ref<UserWrite>(blank())
let retry: { payload: string; key: string } | null = null
const textRule = (limit: number, required = false) => ({
  required,
  validator: (_rule: unknown, value: string, done: (e?: Error) => void) => {
    const text = value.normalize('NFC').trim()
    done(
      (required && !text) || [...text].length > limit || /[\p{Cc}\p{Cf}\p{Cs}]/u.test(text)
        ? new Error(`${required ? '必填，' : ''}最多${limit}个字符，不能包含控制字符`)
        : undefined,
    )
  },
  trigger: 'blur',
})
const rules: FormRules = {
  display_name: [textRule(50, true)],
  nickname: [textRule(50)],
  phone: [textRule(32)],
  email: [textRule(254, true), { type: 'email', message: '请输入有效邮箱', trigger: 'blur' }],
  team_id: [{ required: true, message: '请选择所属团队', trigger: 'change' }],
  role_ids: [
    {
      type: 'array',
      required: true,
      min: 1,
      max: 20,
      message: '请选择1至20个功能角色',
      trigger: 'change',
    },
  ],
  managed_team_ids: [
    {
      type: 'array',
      max: 500,
      message: '最多选择500个管理团队',
      trigger: 'change',
    },
  ],
}
let openGeneration = 0
async function open(person?: OrbitUser) {
  const sequence = ++openGeneration
  opening.value = true
  draft.value = blank()
  retry = null
  error.value = ''
  csrf.value = ''
  try {
    const caps = await userApi.capabilities()
    if (!caps.can_create) throw new Error('当前身份没有人员维护权限')
    const current = person ? await userApi.get(person.id) : null
    if (sequence !== openGeneration) return
    actorId.value = caps.actor_user_id
    protectedIds.value = caps.protected_user_ids
    editing.value = current
    if (editing.value) {
      const { id: _id, revision: _revision, identity_status: _identity, ...fields } = editing.value
      draft.value = {
        ...fields,
        role_ids: [...fields.role_ids],
        managed_team_ids: [...fields.managed_team_ids],
      }
    }
    csrf.value = caps.csrf_token
    visible.value = true
    form.value?.clearValidate()
  } catch (cause) {
    if (sequence === openGeneration)
      ElMessage.error(cause instanceof Error ? cause.message : '能力读取失败')
  } finally {
    if (sequence === openGeneration) opening.value = false
  }
}
async function save() {
  if (saving.value || opening.value || !(await form.value?.validate().catch(() => false))) return
  error.value = ''
  const value: UserWrite = {
    ...draft.value,
    display_name: draft.value.display_name.normalize('NFC').trim(),
    nickname: draft.value.nickname.normalize('NFC').trim(),
    email: draft.value.email.normalize('NFC').trim(),
    phone: draft.value.phone.normalize('NFC').trim(),
    role_ids: [...draft.value.role_ids].sort(),
    managed_team_ids: [...draft.value.managed_team_ids].sort(),
  }
  const payload = JSON.stringify(value)
  const securityFields = ['team_id', 'role_ids', 'data_role', 'managed_team_ids', 'status'] as const
  if (
    editing.value &&
    securityFields.some(
      (field) => JSON.stringify(editing.value![field]) !== JSON.stringify(value[field]),
    )
  ) {
    try {
      await ElMessageBox.confirm(
        '本次修改将变更人员状态或授权范围，并使其已有会话失效。确认保存？',
        '确认变更人员授权',
        { type: 'warning', confirmButtonText: '确认保存', cancelButtonText: '返回修改' },
      )
    } catch {
      return
    }
  }
  saving.value = true
  if (retry?.payload !== payload)
    retry = { payload, key: `user-${editing.value ? 'update' : 'create'}-${crypto.randomUUID()}` }
  try {
    const result = editing.value
      ? await userApi.update(
          editing.value.id,
          value,
          editing.value.revision,
          csrf.value,
          retry!.key,
        )
      : await userApi.create(value, csrf.value, retry!.key)
    visible.value = false
    ElMessage.success(editing.value ? '人员修改已保存' : '人员已创建，尚未验证身份')
    if (editing.value?.id === actorId.value && value.status === 'DISABLED') {
      removeToken()
      await router.replace('/login')
    } else emit('created', result)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '保存失败，请重试'
  } finally {
    saving.value = false
  }
}
async function reloadPerson() {
  if (!editing.value) return
  try {
    await ElMessageBox.confirm('重新读取会丢弃当前未保存的修改，确认重新读取？', '重新读取人员', {
      type: 'warning',
      confirmButtonText: '确认重读',
      cancelButtonText: '保留修改',
    })
    await open(editing.value)
  } catch {
    /* 用户选择保留修改时不发送写请求。 */
  }
}
defineExpose({ open })
</script>

<style>
/* 长表单在弹窗内部滚动，手机上始终保留标题、关闭与保存操作。 */
.user-create-dialog {
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 24px);
  margin: 12px auto;
}
.el-dialog.user-create-dialog:not(.is-fullscreen) {
  /* 若依原样式带6vh !important，仅覆盖本长表单，避免手机底部操作被挤出屏幕。 */
  margin-top: 12px !important;
}
.user-create-dialog .el-dialog__body {
  min-height: 0;
  overflow-y: auto;
}
.user-create-dialog .el-dialog__header,
.user-create-dialog .el-dialog__footer {
  flex-shrink: 0;
}
</style>

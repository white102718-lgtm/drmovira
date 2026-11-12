<template>
  <div class="app-container users-page">
    <h2>人员管理</h2>
    <el-button v-if="canCreate" type="primary" @click="creator?.open()">新增人员</el-button>
    <CreateUser ref="creator" @created="created" />
    <ResetPassword ref="passwordEditor" @changed="reload" />
    <el-form :inline="true" @submit.prevent="reload">
      <el-form-item label="人员信息">
        <el-input
          v-model="query"
          clearable
          placeholder="姓名、账号、昵称、邮箱或联系方式"
          @keyup.enter="reload"
        />
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="status" clearable placeholder="全部状态" style="width: 140px">
          <el-option v-for="(label, code) in states" :key="code" :label="label" :value="code" />
        </el-select>
      </el-form-item>
      <el-form-item label="登记日期（UTC）">
        <el-date-picker
          v-model="dates"
          type="daterange"
          value-format="YYYY-MM-DD"
          popper-class="orbit-directory-date-popper"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :disabled="loading" @click="reload">查询</el-button>
        <el-button :disabled="loading" @click="reset">重置</el-button>
      </el-form-item>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-table v-loading="loading" :data="rows" empty-text="暂无符合条件的人员">
      <el-table-column
        prop="login_account"
        label="登录账号"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column prop="display_name" label="姓名" min-width="140" show-overflow-tooltip />
      <el-table-column prop="nickname" label="昵称" min-width="140" show-overflow-tooltip />
      <el-table-column prop="email" label="邮箱" min-width="200" show-overflow-tooltip />
      <el-table-column prop="phone" label="联系方式" min-width="160" show-overflow-tooltip />
      <el-table-column prop="team_name" label="所属团队" min-width="140" />
      <el-table-column label="功能角色" min-width="180"
        ><template #default="{ row }">{{
          row.role_names?.join('、') || '—'
        }}</template></el-table-column
      >
      <el-table-column label="密码状态" min-width="140"
        ><template #default="{ row }">{{
          identities[row.identity_status as keyof typeof identities]
        }}</template></el-table-column
      >
      <el-table-column label="数据角色" min-width="120">
        <template #default="{ row }">{{ roles[row.data_role as keyof typeof roles] }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">{{ states[row.status as keyof typeof states] }}</template>
      </el-table-column>
      <el-table-column label="操作" fixed="right" :width="canCreate ? 300 : 90">
        <template #default="{ row }"
          ><el-button link type="primary" @click="showDetail(row)">详情</el-button>
          <el-button v-if="canCreate" link type="primary" @click="creator?.open(row)"
            >编辑</el-button
          >
          <el-button
            v-if="canCreate"
            link
            :type="row.status === 'ENABLED' ? 'danger' : 'primary'"
            :disabled="row.id === actorId || protectedIds.includes(row.id) || changing"
            @click="toggleStatus(row)"
            >{{ row.status === 'ENABLED' ? '停用' : '开启' }}</el-button
          >
          <el-button
            v-if="canCreate"
            link
            type="primary"
            :disabled="row.id === actorId || protectedIds.includes(row.id)"
            @click="passwordEditor?.open(row)"
            >重置密码</el-button
          >
        </template>
      </el-table-column>
    </el-table>
    <div class="users-pagination">
      <el-select
        v-model="pageSize"
        aria-label="每页数量"
        style="width: 120px"
        :disabled="loading"
        @change="reload"
      >
        <el-option
          v-for="size in [20, 50, 100, 200]"
          :key="size"
          :value="size"
          :label="`${size}条/页`"
        />
      </el-select>
      <span>第{{ page + 1 }}页</span>
      <el-button :disabled="loading || page === 0" @click="previous">上一页</el-button>
      <el-button :disabled="loading || !nextCursor" @click="next">下一页</el-button>
    </div>
    <el-drawer v-model="detailVisible" title="人员详情" size="min(640px, calc(100vw - 24px))">
      <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" />
      <el-skeleton v-if="detailLoading" :rows="8" animated />
      <el-descriptions v-else-if="detail" :column="1" border>
        <el-descriptions-item label="登录账号">{{ detail.login_account }}</el-descriptions-item>
        <el-descriptions-item label="姓名">{{ detail.display_name }}</el-descriptions-item>
        <el-descriptions-item label="昵称">{{ detail.nickname || '未填写' }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ detail.email }}</el-descriptions-item>
        <el-descriptions-item label="联系方式">{{ detail.phone || '未填写' }}</el-descriptions-item>
        <el-descriptions-item label="团队UUID">{{ detail.team_id }}</el-descriptions-item>
        <el-descriptions-item label="功能角色UUID">
          <div v-for="id in detail.role_ids" :key="id">{{ id }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="数据角色">{{ roles[detail.data_role] }}</el-descriptions-item>
        <el-descriptions-item label="管理团队UUID">{{
          detail.managed_team_ids.join('、') || '无'
        }}</el-descriptions-item>
        <el-descriptions-item label="账号状态">{{ states[detail.status] }}</el-descriptions-item>
        <el-descriptions-item label="登录方式">{{
          identities[detail.identity_status]
        }}</el-descriptions-item>
        <el-descriptions-item label="业务UUID">{{ detail.id }}</el-descriptions-item>
        <el-descriptions-item label="版本">{{ detail.revision }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { userApi, type OrbitUser } from '@/api/orbit/users'
import '../directory-date.scss'
import CreateUser from './CreateUser.vue'
import ResetPassword from './ResetPassword.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
const creator = ref<InstanceType<typeof CreateUser>>()
const passwordEditor = ref<InstanceType<typeof ResetPassword>>()
const actorId = ref(''),
  protectedIds = ref<string[]>([]),
  changing = ref(false)
const canCreate = ref(false)
async function created(value: OrbitUser) {
  await reload()
  await showDetail(value)
}

const states = { ENABLED: '开启', DISABLED: '停用' }
const roles = { USER: '普通用户', TEAM_ADMIN: '团队管理员', SUPER_ADMIN: '超级管理员' }
const identities = {
  LOCAL_ACCOUNT: '已设置登录密码',
  UNVERIFIED: '未设置登录密码',
  OIDC_VERIFIED: '企业身份登录',
}
const route = useRoute()
const query = ref(typeof route.query.q === 'string' ? route.query.q : ''),
  status = ref(''),
  dates = ref<string[] | null>(null)
const rows = ref<OrbitUser[]>([]),
  loading = ref(false),
  error = ref('')
const pageSize = ref(50),
  page = ref(0),
  nextCursor = ref<string | null>(null)
const cursors = ref<(string | null)[]>([null])
let generation = 0
async function load() {
  const sequence = ++generation
  loading.value = true
  error.value = ''
  const params = new URLSearchParams({ page_size: String(pageSize.value) })
  if (query.value) params.set('q', query.value)
  if (status.value) params.set('status', status.value)
  if (dates.value?.length === 2) {
    params.set('date_from', dates.value[0])
    params.set('date_to', dates.value[1])
  }
  if (cursors.value[page.value]) params.set('cursor', cursors.value[page.value]!)
  try {
    const result = await userApi.list(params)
    if (sequence !== generation) return
    rows.value = result.items
    nextCursor.value = result.next_cursor
  } catch (cause) {
    if (sequence !== generation) return
    rows.value = []
    nextCursor.value = null
    error.value = cause instanceof Error ? cause.message : '人员读取失败，请重试'
  } finally {
    if (sequence === generation) loading.value = false
  }
}
function reload() {
  page.value = 0
  cursors.value = [null]
  return load()
}
function reset() {
  query.value = ''
  status.value = ''
  dates.value = null
  return reload()
}
function next() {
  if (!nextCursor.value) return
  cursors.value[page.value + 1] = nextCursor.value
  page.value++
  return load()
}
function previous() {
  if (!page.value) return
  page.value--
  return load()
}
const detailVisible = ref(false),
  detailLoading = ref(false),
  detailError = ref('')
const detail = ref<OrbitUser | null>(null)
let detailGeneration = 0
async function showDetail(row: OrbitUser) {
  const sequence = ++detailGeneration
  detailVisible.value = true
  detailLoading.value = true
  detailError.value = ''
  detail.value = null
  try {
    const result = await userApi.get(row.id)
    if (sequence === detailGeneration) detail.value = result
  } catch (cause) {
    if (sequence === detailGeneration)
      detailError.value = cause instanceof Error ? cause.message : '详情读取失败'
  } finally {
    if (sequence === detailGeneration) detailLoading.value = false
  }
}
onMounted(async () => {
  await load()
  try {
    const caps = await userApi.capabilities()
    canCreate.value = caps.can_create
    actorId.value = caps.actor_user_id
    protectedIds.value = caps.protected_user_ids
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '人员能力读取失败'
  }
})
async function toggleStatus(row: OrbitUser) {
  if (changing.value) return
  try {
    await ElMessageBox.confirm(
      `${row.status === 'ENABLED' ? '停用后该人员将不能登录，已有会话会失效。' : '开启后该人员可使用已设置的账号密码登录。'}确认${row.status === 'ENABLED' ? '停用' : '开启'}“${row.display_name}”？`,
      '变更人员状态',
      { type: 'warning' },
    )
  } catch {
    return
  }
  changing.value = true
  try {
    const caps = await userApi.capabilities()
    const current = await userApi.get(row.id)
    if (current.revision !== row.revision) throw new Error('人员已被修改，请刷新后重试')
    const { id, revision, identity_status, login_account, team_name, role_names, ...fields } =
      current
    await userApi.update(
      id,
      { ...fields, status: row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED' },
      revision,
      caps.csrf_token,
      `user-state-${crypto.randomUUID()}`,
    )
    ElMessage.success('人员状态已更新')
    await reload()
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : '状态更新失败')
    await reload()
  } finally {
    changing.value = false
  }
}
</script>

<style scoped>
.users-pagination {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 16px;
}
.users-page :deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  .users-page :deep(.el-form-item),
  .users-page :deep(.el-date-editor) {
    max-width: 100%;
  }
}
</style>

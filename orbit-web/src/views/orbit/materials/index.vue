<template>
  <div class="app-container material-page">
    <div class="toolbar">
      <h2>素材库</h2>
      <div>
        <el-button v-if="can('tags.read')" @click="taxonomyVisible = true">标签与分类</el-button
        ><el-button v-if="can('assets.upload')" type="primary" :disabled="!caps" @click="openUpload"
          >上传素材</el-button
        ><el-button
          v-if="can('assets.delete')"
          type="danger"
          plain
          :disabled="!selected.length || busy"
          @click="archiveSelected"
          >批量归档（{{ selected.length }}）</el-button
        >
      </div>
    </div>
    <el-alert
      title="当前按名称浏览。广告指标汇总尚未接入，花费、点击、展示、ROAS、转化和使用次数为未知；不以0代替。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-form :inline="true" class="filters" @submit.prevent="reload">
      <el-form-item label="名称"
        ><el-input
          v-model="q"
          clearable
          maxlength="200"
          placeholder="按名称搜索"
          @keyup.enter="reload"
      /></el-form-item>
      <el-form-item label="分类"
        ><el-select v-model="category" clearable filterable style="width: 160px"
          ><el-option
            v-for="item in categories"
            :key="item.id"
            :value="item.id"
            :label="item.name" /></el-select
      ></el-form-item>
      <el-form-item label="类型"
        ><el-select v-model="kind" clearable style="width: 110px"
          ><el-option label="图片" value="IMAGE" /><el-option
            label="视频"
            value="VIDEO" /></el-select
      ></el-form-item>
      <el-form-item label="状态"
        ><el-select v-model="status" clearable style="width: 170px"
          ><el-option
            v-for="(label, value) in states"
            :key="value"
            :value="value"
            :label="label" /></el-select
      ></el-form-item>
      <el-form-item label="标签"
        ><el-select
          v-model="tagIds"
          multiple
          filterable
          :multiple-limit="20"
          style="min-width: 180px"
          ><el-option
            v-for="item in tags"
            :key="item.id"
            :value="item.id"
            :label="item.name" /></el-select
      ></el-form-item>
      <el-form-item label="关系"
        ><el-select v-model="tagMatch" style="width: 110px"
          ><el-option label="全部满足" value="ALL" /><el-option
            label="任一满足"
            value="ANY" /></el-select
      ></el-form-item>
      <el-form-item label="名称排序"
        ><el-select v-model="direction" style="width: 100px"
          ><el-option label="升序" value="ASC" /><el-option label="降序" value="DESC" /></el-select
      ></el-form-item>
      <el-form-item
        ><el-button type="primary" :disabled="loading" @click="reload">查询</el-button
        ><el-button :disabled="loading" @click="reset">重置</el-button></el-form-item
      >
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-table
      v-loading="loading"
      :data="items"
      row-key="id"
      @selection-change="selected = $event"
      empty-text="暂无符合条件的素材"
    >
      <el-table-column type="selection" width="50" />
      <el-table-column prop="name" label="素材名称" min-width="200" show-overflow-tooltip />
      <el-table-column label="类型" width="80"
        ><template #default="{ row }">{{
          row.kind === 'IMAGE' ? '图片' : '视频'
        }}</template></el-table-column
      >
      <el-table-column label="状态" min-width="150"
        ><template #default="{ row }"
          ><el-tag
            :type="
              row.state === 'READY' && cleanFor(row)
                ? 'success'
                : row.state.includes('FAILED') || row.state === 'QUARANTINED'
                  ? 'danger'
                  : 'info'
            "
            >{{
              row.state === 'READY' && !cleanFor(row)
                ? '待安全复核（历史状态）'
                : (states[row.state] ?? row.state)
            }}</el-tag
          ></template
        ></el-table-column
      >
      <el-table-column label="分类" width="140"
        ><template #default="{ row }">{{
          categoryName(row.category_id)
        }}</template></el-table-column
      >
      <el-table-column label="安全检查" min-width="150">
        <template #default="{ row }">
          <el-tag :type="cleanFor(row) ? 'success' : 'warning'">{{
            securityLabel(security[row.id])
          }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="标签" min-width="160"
        ><template #default="{ row }"
          ><el-tag v-for="id in row.tag_ids" :key="id" size="small">{{ tagName(id) }}</el-tag
          ><span v-if="!row.tag_ids.length">—</span></template
        ></el-table-column
      >
      <el-table-column label="视频时长（秒）" width="150"
        ><template #default="{ row }">{{ row.duration_seconds ?? '—' }}</template></el-table-column
      >
      <el-table-column label="指标" width="110"><template #default>未知</template></el-table-column>
      <el-table-column prop="revision" label="版本" width="70" />
      <el-table-column label="操作" width="130" fixed="right"
        ><template #default="{ row }"
          ><el-button link type="primary" @click="showDetail(row)">详情</el-button
          ><el-button
            v-if="can('assets.edit')"
            link
            type="primary"
            :disabled="row.state !== 'READY' || !cleanFor(row)"
            @click="openEditor(row)"
            >编辑</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <div class="pagination">
      <el-select v-model="pageSize" aria-label="每页素材数量" style="width: 120px" @change="reload"
        ><el-option
          v-for="n in [20, 50, 100, 200]"
          :key="n"
          :value="n"
          :label="`${n}条/页`" /></el-select
      ><span>第{{ page + 1 }}页</span
      ><el-button :disabled="loading || !page" @click="previous">上一页</el-button
      ><el-button :disabled="loading || !nextCursor" @click="next">下一页</el-button
      ><el-button :disabled="loading" @click="reload">刷新处理状态</el-button>
    </div>
    <el-drawer
      v-model="detailVisible"
      title="素材详情与引用关系"
      size="min(780px, 100%)"
      @closed="clearPreview"
    >
      <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" />
      <p v-if="detailLoading" role="status">正在刷新详情与安全状态，请稍候…</p>
      <template v-if="detail"
        ><el-descriptions :column="1" border
          ><el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item
          ><el-descriptions-item label="素材ID">{{ detail.id }}</el-descriptions-item
          ><el-descriptions-item label="状态">{{
            detail.state === 'READY' && detailSecurity?.scan_status !== 'CLEAN'
              ? '历史READY，安全未验证'
              : (states[detail.state] ?? detail.state)
          }}</el-descriptions-item
          ><el-descriptions-item label="SHA256">{{ detail.sha256 }}</el-descriptions-item
          ><el-descriptions-item label="拥有者">{{
            detail.ownership.owner_user_id
          }}</el-descriptions-item
          ><el-descriptions-item label="团队">{{
            detail.ownership.owner_team_id
          }}</el-descriptions-item
          ><el-descriptions-item label="分类">{{
            categoryName(detail.category_id)
          }}</el-descriptions-item
          ><el-descriptions-item label="标签">{{
            detail.tag_ids.map(tagName).join('、') || '无'
          }}</el-descriptions-item
          ><el-descriptions-item label="视频时长">{{
            detail.duration_seconds ?? '未知或不适用'
          }}</el-descriptions-item
          ><el-descriptions-item label="版本">{{
            detail.revision
          }}</el-descriptions-item></el-descriptions
        >
        <el-alert
          v-if="!detailSecurity || detailSecurity.scan_status !== 'CLEAN'"
          title="此素材尚未完成当前文件的安全检查，暂不可编辑、预览或用于新分配。历史状态不代表已检查通过。"
          type="warning"
          :closable="false"
          show-icon
        />
        <el-descriptions :column="1" border>
          <el-descriptions-item label="安全检查">{{
            securityLabel(detailSecurity)
          }}</el-descriptions-item>
          <el-descriptions-item label="检查时间">{{
            detailSecurity?.receipt_at ?? '尚无有效检查记录'
          }}</el-descriptions-item>
          <el-descriptions-item label="文件匹配">{{
            detailSecurity?.hash_matches ? '与当前文件一致' : '尚未验证'
          }}</el-descriptions-item>
        </el-descriptions>
        <el-button
          v-if="can('assets.upload')"
          :disabled="busy || detailLoading || !detailSecurity?.rescan_allowed"
          @click="rescanDetail"
          >重新安全检查</el-button
        >
        <el-button :disabled="busy || detailLoading" :loading="detailLoading" @click="refreshDetail"
          >刷新安全状态</el-button
        >
        <span v-if="detailSecurity && !detailSecurity.rescan_allowed">{{
          rescanReason(detailSecurity.rescan_reason)
        }}</span>
        <img v-if="previewBlob" :src="previewBlob" alt="服务端处理后的素材预览" class="preview" />
        <h3>引用关系</h3>
        <el-table :data="references" empty-text="无引用关系"
          ><el-table-column prop="kind" label="类型" min-width="160" /><el-table-column
            prop="resource_id"
            label="业务资源ID"
            min-width="260"
          /><el-table-column label="状态" width="90"
            ><template #default="{ row }">{{
              row.active ? '活跃' : '历史'
            }}</template></el-table-column
          ></el-table
        ><el-button v-if="referenceCursor" @click="moreReferences">加载更多引用</el-button>
        <p>活跃分配和执行引用阻止归档；历史证据只阻止物理清理。归档文件至少保留30日。</p>
        <el-button :disabled="busy || detailLoading" @click="refreshDetail">刷新详情</el-button>
      </template>
    </el-drawer>
    <el-dialog
      v-model="editorVisible"
      title="编辑素材元数据"
      :style="{ maxWidth: 'calc(100vw - 24px)' }"
      width="560px"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving"
      :before-close="closeEditor"
    >
      <el-alert v-if="editError" :title="editError" type="error" :closable="false" />
      <el-form label-position="top"
        ><el-form-item label="素材名称（必填）"
          ><el-input v-model="form.name" maxlength="200" :disabled="saving" /></el-form-item
        ><el-form-item label="分类（必填）"
          ><el-select v-model="form.category_id" :disabled="saving"
            ><el-option
              v-for="item in categories.filter((x) => x.state === 'ENABLED')"
              :key="item.id"
              :value="item.id"
              :label="item.name" /></el-select></el-form-item
        ><el-form-item label="标签（最多20个）"
          ><el-select v-model="form.tag_ids" multiple :multiple-limit="20" :disabled="saving"
            ><el-option
              v-for="item in tags"
              :key="item.id"
              :value="item.id"
              :label="`${item.name}${item.state === 'DISABLED' ? '（已停用）' : ''}`"
              :disabled="
                item.state === 'DISABLED' && !editing?.tag_ids.includes(item.id)
              " /></el-select></el-form-item
      ></el-form>
      <template #footer
        ><el-button :disabled="saving" @click="closeEditor()">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save">保存</el-button></template
      >
    </el-dialog>
    <MaterialUpload
      v-if="uploadVisible && caps"
      :key="uploadEpoch"
      v-model="uploadVisible"
      :csrf="caps.csrf_token"
      :categories="categories"
      :tags="tags"
      :default-category="caps.default_category_id"
      @completed="reload"
    />
    <MaterialTaxonomyPanel
      v-if="caps"
      v-model="taxonomyVisible"
      :csrf="caps.csrf_token"
      :can="can"
      @changed="loadTaxonomy"
    />
  </div>
</template>
<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import useUserStore from '@/store/modules/user'
import { orbitAuthHeaders, orbitCredentials } from '@/api/orbit/authentication'
import {
  materialApi,
  type MaterialAsset,
  type MaterialCapabilities,
  type MaterialMetadata,
  type MaterialTaxonomy,
  type MaterialSecurity,
} from '@/api/orbit/materials'
import MaterialUpload from './MaterialUpload.vue'
import MaterialTaxonomyPanel from './MaterialTaxonomy.vue'
const user = useUserStore()
const can = (permission: string) =>
  user.permissions.includes('*:*:*') || user.permissions.includes(permission)
const states: Record<string, string> = {
  INITIATED: '等待上传',
  UPLOADING: '上传中',
  SCANNING: '扫描排队',
  PROCESSING: '处理中',
  READY: '可用',
  UPLOAD_FAILED: '上传失败',
  QUARANTINED: '已隔离',
  PROCESSING_FAILED: '处理失败',
  ARCHIVED: '已归档',
}
const caps = ref<MaterialCapabilities>(),
  items = ref<MaterialAsset[]>([]),
  selected = ref<MaterialAsset[]>([]),
  categories = ref<MaterialTaxonomy[]>([]),
  tags = ref<MaterialTaxonomy[]>([])
const q = ref(''),
  category = ref(''),
  kind = ref(''),
  status = ref(''),
  tagIds = ref<string[]>([]),
  tagMatch = ref('ALL'),
  direction = ref('ASC'),
  pageSize = ref(50)
const loading = ref(false),
  error = ref(''),
  busy = ref(false),
  page = ref(0),
  nextCursor = ref<string | null>(null),
  cursors = ref<string[]>([''])
const uploadVisible = ref(false),
  uploadEpoch = ref(0),
  taxonomyVisible = ref(false),
  detailVisible = ref(false),
  detail = ref<MaterialAsset>(),
  detailError = ref(''),
  previewBlob = ref('')
const references = ref<{ id: string; kind: string; resource_id: string; active: boolean }[]>([]),
  referenceCursor = ref<string | null>(null)
const security = ref<Record<string, MaterialSecurity>>({})
const detailSecurity = ref<MaterialSecurity>()
const detailLoading = ref(false)
const rescanIntents = new Map<string, { reason: string; revision: number; key: string }>()
const cleanFor = (asset: MaterialAsset) =>
  security.value[asset.id]?.revision === asset.revision &&
  security.value[asset.id]?.scan_status === 'CLEAN'
const securityLabel = (value?: MaterialSecurity) =>
  ({ CLEAN: '安全检查通过', INFECTED: '已隔离', SCANNING: '检查中', UNVERIFIED: '待安全复核' })[
    value?.scan_status ?? 'UNVERIFIED'
  ]
const rescanReasons: Record<string, string> = {
  PERMISSION_REQUIRED: '需要素材上传权限',
  ARCHIVED: '归档素材不重新检查',
  OBJECT_UNAVAILABLE: '原文件已进入回收流程',
  SCAN_IN_PROGRESS: '请等待当前处理完成',
  UPLOAD_INCOMPLETE: '请先完成上传',
  ACTIVE_REFERENCE: '请先解除活跃分配或执行引用',
}
const rescanReason = (value: string) => rescanReasons[value] ?? ''
const editorVisible = ref(false),
  editing = ref<MaterialAsset>(),
  saving = ref(false),
  editError = ref(''),
  form = reactive<MaterialMetadata>({ name: '', category_id: '', tag_ids: [] })
let editKey = '',
  detailEpoch = 0
const categoryName = (id: string) => categories.value.find((x) => x.id === id)?.name ?? id
const tagName = (id: string) => tags.value.find((x) => x.id === id)?.name ?? id
/** 每次打开创建新上传会话视图，避免复用上一次文件队列。 */
function openUpload() {
  uploadVisible.value = true
  uploadEpoch.value++
}
async function loadTaxonomy() {
  if (!can('tags.read')) return
  for (const kind of ['categories', 'tags'] as const) {
    const values: MaterialTaxonomy[] = []
    let cursor = ''
    do {
      const response = await materialApi.taxonomy(kind, cursor)
      values.push(...response.items)
      cursor = response.next_cursor ?? ''
      if (values.length > 10000) throw new Error('标签分类目录过大，请使用专门目录页分页管理')
    } while (cursor)
    if (kind === 'categories') categories.value = values
    else tags.value = values
  }
}
function query() {
  const value = new URLSearchParams({
    q: q.value,
    page_size: String(pageSize.value),
    sort: 'name',
    direction: direction.value,
    tag_match: tagMatch.value,
  })
  for (const [k, v] of [
    ['category_id', category.value],
    ['kind', kind.value],
    ['status', status.value],
    ['cursor', cursors.value[page.value]],
  ])
    if (v) value.set(k, v)
  if (tagIds.value.length) value.set('tag_ids', tagIds.value.join(','))
  return value
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await materialApi.list(query())
    security.value = {}
    items.value = response.items
    if (response.items.length) {
      const result = await materialApi.security(response.items.map((item) => item.id))
      security.value = Object.fromEntries(result.items.map((item) => [item.asset_id, item]))
    }
    nextCursor.value = response.next_cursor
    selected.value = []
  } catch (e) {
    items.value = []
    nextCursor.value = null
    error.value = e instanceof Error ? e.message : '素材加载失败'
  } finally {
    loading.value = false
  }
}
async function reload() {
  if (loading.value) return
  page.value = 0
  cursors.value = ['']
  await load()
}
function reset() {
  q.value = ''
  category.value = ''
  kind.value = ''
  status.value = ''
  tagIds.value = []
  tagMatch.value = 'ALL'
  direction.value = 'ASC'
  void reload()
}
async function next() {
  if (!nextCursor.value || loading.value) return
  cursors.value[page.value + 1] = nextCursor.value
  page.value++
  await load()
}
async function previous() {
  if (!page.value || loading.value) return
  page.value--
  await load()
}
function clearPreview() {
  detailEpoch++
  detailLoading.value = false
  if (previewBlob.value) URL.revokeObjectURL(previewBlob.value)
  previewBlob.value = ''
}
async function showDetail(row: MaterialAsset) {
  await loadDetail(row, false)
}
/** 刷新保留已显示元数据；每轮新epoch及loading防止并发刷新或迟到覆盖。 */
async function loadDetail(row: MaterialAsset, preserve: boolean) {
  clearPreview()
  const epoch = detailEpoch
  if (!preserve) {
    detail.value = undefined
    detailSecurity.value = undefined
    references.value = []
    referenceCursor.value = null
  }
  detailLoading.value = true
  detailVisible.value = true
  detailError.value = ''
  try {
    const [response, inspection] = await Promise.all([
      materialApi.get(row.id),
      materialApi.securityDetail(row.id),
    ])
    if (epoch !== detailEpoch) return
    detail.value = response
    detailSecurity.value = inspection
    const refs = await materialApi.references(row.id)
    if (epoch !== detailEpoch) return
    references.value = refs.items
    referenceCursor.value = refs.next_cursor
    if (
      response.preview_url &&
      inspection.scan_status === 'CLEAN' &&
      inspection.revision === response.revision
    ) {
      const result = await fetch(
        `${import.meta.env.VITE_APP_BASE_API}/api/v1/assets/${encodeURIComponent(row.id)}/preview`,
        { credentials: orbitCredentials(), headers: orbitAuthHeaders(), cache: 'no-store' },
      )
      if (!result.ok) throw new Error('预览不可用或授权已失效')
      const blob = await result.blob()
      if (epoch === detailEpoch) previewBlob.value = URL.createObjectURL(blob)
    }
  } catch (e) {
    if (epoch === detailEpoch) detailError.value = e instanceof Error ? e.message : '详情加载失败'
  } finally {
    if (epoch === detailEpoch) detailLoading.value = false
  }
}
async function moreReferences() {
  if (!detail.value || !referenceCursor.value) return
  const epoch = detailEpoch
  try {
    const result = await materialApi.references(detail.value.id, referenceCursor.value)
    if (epoch !== detailEpoch) return
    references.value.push(...result.items)
    referenceCursor.value = result.next_cursor
  } catch (e) {
    if (epoch === detailEpoch) detailError.value = e instanceof Error ? e.message : '引用加载失败'
  }
}
async function openEditor(row: MaterialAsset) {
  try {
    const [asset, inspection] = await Promise.all([
      materialApi.get(row.id),
      materialApi.securityDetail(row.id),
    ])
    if (inspection.scan_status !== 'CLEAN' || inspection.revision !== asset.revision)
      throw new Error('当前文件尚未通过安全检查，请先申请复核')
    editing.value = asset
    form.name = editing.value.name
    form.category_id = editing.value.category_id
    form.tag_ids = [...editing.value.tag_ids]
    editError.value = ''
    editKey = ''
    editorVisible.value = true
  } catch (e) {
    error.value = e instanceof Error ? e.message : '无法编辑'
  }
}
async function rescanDetail() {
  if (!detail.value || !caps.value || busy.value || !detailSecurity.value?.rescan_allowed) return
  const asset = detail.value
  const epoch = detailEpoch
  try {
    const { value } = await ElMessageBox.prompt(
      '重新检查会复核原文件并重新处理预览，请填写原因；活跃分配或执行引用必须先解除。',
      '重新安全检查',
      {
        inputValidator: (v: string) =>
          (!!v?.trim() && [...v.trim()].length <= 1000) || '请填写1至1000字符原因',
      },
    )
    busy.value = true
    const reason = value.trim()
    let intent = rescanIntents.get(asset.id)
    if (!intent || intent.reason !== reason || intent.revision !== asset.revision) {
      intent = { reason, revision: asset.revision, key: crypto.randomUUID() }
      rescanIntents.set(asset.id, intent)
    }
    await materialApi.rescan(asset, reason, caps.value.csrf_token, intent.key)
    rescanIntents.delete(asset.id)
    await reload()
    if (detailVisible.value && epoch === detailEpoch) await showDetail(asset)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      detailError.value = e instanceof Error ? e.message : '申请安全复核失败'
      if ((e as { status?: number }).status) rescanIntents.delete(asset.id)
    }
  } finally {
    busy.value = false
  }
}
/** 统一递增详情epoch并释放旧blob，迟到的安全检查或预览响应不能覆盖新详情。 */
async function refreshDetail() {
  if (detail.value && !busy.value && !detailLoading.value) await loadDetail(detail.value, true)
}
function closeEditor(done?: () => void) {
  if (saving.value) return
  editorVisible.value = false
  done?.()
}
async function save() {
  if (!editing.value || !caps.value || saving.value) return
  if (!form.name.trim() || [...form.name.trim()].length > 100 || !form.category_id) {
    editError.value = '请填写1至100字符名称和有效分类'
    return
  }
  saving.value = true
  editKey ||= crypto.randomUUID()
  try {
    await materialApi.edit(
      editing.value,
      { ...form, name: form.name.trim() },
      caps.value.csrf_token,
      editKey,
    )
    editorVisible.value = false
    await reload()
  } catch (e) {
    editError.value = e instanceof Error ? e.message : '保存失败'
    if ((e as { status?: number }).status) editKey = ''
  } finally {
    saving.value = false
  }
}
async function archiveSelected() {
  if (!caps.value || busy.value) return
  try {
    const { value } = await ElMessageBox.prompt(
      `归档所选${selected.value.length}个素材，任一活跃引用或版本冲突会整批拒绝。请输入原因。`,
      '批量归档',
      { inputValidator: (v: string) => !!v?.trim() || '请输入原因' },
    )
    busy.value = true
    await materialApi.archive(
      selected.value,
      value.trim(),
      caps.value.csrf_token,
      crypto.randomUUID(),
    )
    await reload()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') error.value = e instanceof Error ? e.message : '归档失败'
  } finally {
    busy.value = false
  }
}
onMounted(async () => {
  try {
    caps.value = await materialApi.capabilities()
    await loadTaxonomy()
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '素材页面初始化失败'
  }
})
onBeforeUnmount(clearPreview)
</script>
<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar h2 {
  font-size: 20px;
}
.filters {
  margin-top: 20px;
}
.pagination {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 20px;
}
.preview {
  max-width: 100%;
  max-height: 400px;
  display: block;
  margin: 20px auto;
}
.material-page :deep(.el-dialog) {
  max-width: calc(100vw - 24px);
}
.material-page :deep(.el-descriptions__content) {
  word-break: break-word;
}
.material-page :deep(.el-select) {
  max-width: 100%;
}
@media (max-width: 600px) {
  .toolbar > div {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .toolbar :deep(.el-button) {
    margin-left: 0;
  }
  .filters :deep(.el-form-item) {
    display: flex;
    margin-right: 0;
  }
  .filters :deep(.el-form-item__content) {
    flex: 1;
    min-width: 0;
  }
}
</style>

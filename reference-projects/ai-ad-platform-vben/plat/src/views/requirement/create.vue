<script lang="ts" setup>
import type { UploadProps } from 'ant-design-vue';

import type {
  CreateMaterialTaskContext,
  MaterialOrderWriteResult,
  MaterialOrderSourceLinkState,
} from '#/domain/task';

import {
  computed,
  nextTick,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  shallowRef,
  watch,
} from 'vue';

import { useUserStore } from '@vben/stores';
import dayjs from 'dayjs';
import { useRoute, useRouter } from 'vue-router';

import {
  Alert,
  Button,
  DatePicker,
  Input,
  InputNumber,
  Modal,
  Progress,
  Popover,
  message,
  Popconfirm,
  Select,
  Spin,
  Steps,
  Tag,
  Tooltip,
  TreeSelect,
  RadioGroup,
  RadioButton,
  Upload,
} from 'ant-design-vue';

import type { MaterialOrderProjectOption } from '#/api/requirement';
import {
  downloadAttachmentsZip,
  getMaterialOrderDetail,
  getMaterialOrderOrganization,
  getMaterialOrderFilterOptions,
  uploadMaterialOrderAttachment,
} from '#/api/requirement';
import facebookCountries from '#/data/facebook_countries.json';
import languages from '#/data/languages.json';
import { getDictionaryOptions } from '#/api/system/dictionary';
import {
  canResubmitMaterialOrder,
  canReeditMaterialOrder,
  createMaterialTaskContext,
  createTaskService,
  parseMaterialTaskSourceQuery,
} from '#/domain/task';
import { useTaskCenterStore } from '#/store/task-center';
import { ChevronLeft, IconifyIcon } from '@vben/icons';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import type { VxeGridProps } from '#/adapter/vxe-table';

import { downloadFileByUrl } from '#/utils/download';
import { debounce } from '#/utils';
import { useMaterialOrderAccess } from '#/composables/useMaterialOrderAccess';
import { getCurrentUserRoleCodesApi } from '#/api/core/user';
import type { RequirementTemplateItem } from '#/api/requirement/templates';
import RequirementTemplateModal from './components/RequirementTemplateModal.vue';
import { useUploadQueue } from '#/composables/useUploadQueue';
import {
  COMPRESSED_MIMES,
  ORDER_ATTACHMENT_ALLOWED_EXTS,
  ORDER_ATTACHMENT_ARCHIVE_EXTS,
  validateFileType,
  validateUploadFileSize,
} from '#/utils/upload';

import BaseButton from '#/views/components/BaseButton.vue';
import MediaPreview from '#/views/components/MediaPreview.vue';
import OverflowTooltip from '#/views/components/OverflowTooltip.vue';
import UploadMaterialModal, {
  type UploadFileItem,
} from '#/views/components/RequirementUploadModal.vue';

import ExpandableDescriptionInput from './components/ExpandableDescriptionInput.vue';

const router = useRouter();
const route = useRoute();

// 页内嵌入模式：id/mode 走 props，跳转/返回走事件。
const props = defineProps<{
  embedded?: boolean;
  id?: string;
  mode?: 'new' | 'edit' | 'readonly';
}>();
const emit = defineEmits<{
  (e: 'back'): void;
  (e: 'goAccept', id: string): void;
  (e: 'loaded', info: { orderNo: string; status: string; title: string }): void;
}>();

function getRouteQueryValue(value: unknown) {
  return Array.isArray(value) ? value[0] : value;
}

function getReturnTo() {
  const returnTo = getRouteQueryValue(route.query.returnTo);
  if (
    typeof returnTo === 'string' &&
    (returnTo.startsWith('/requirement/') || returnTo.startsWith('/workbench/'))
  ) {
    return returnTo;
  }
  const from = getRouteQueryValue(route.query.from);
  if (from === 'myTask') return '/requirement/myTask';
  if (from === 'pool') return '/requirement/pool';
  return '';
}

const isTaskCenterCreation = computed(
  () =>
    route.path === '/workbench/tasks/create-material' ||
    getRouteQueryValue(route.query.source) === 'task-center',
);

function buildLinkedDetailQuery(extra: Record<string, string> = {}) {
  const query: Record<string, string> = {
    ...extra,
    returnTo: route.fullPath,
  };
  const from = getRouteQueryValue(route.query.from);
  if (typeof from === 'string') query.from = from;
  return query;
}

function handleBack() {
  if (props.embedded) {
    emit('back');
    return;
  }
  const returnTo = getReturnTo();
  if (returnTo) {
    router.replace(returnTo);
    return;
  }
  router.back();
}

// ---- 只读模式（从 pitcher 跳入查看详情时） ----
const readonlyMode = ref(false);
const draftEditMode = ref(false);
const editOrderMode = ref(false); // 编辑非草稿在途工单
const resubmitLoadError = ref('');
const preserveStatusEdit = computed(
  () => getRouteQueryValue(route.query.preserveStatus) === '1',
);
const originalStatus = ref<string>(''); // 记录被编辑工单的原始状态
const { canCreateMaterialOrder } = useMaterialOrderAccess();
// 复制已完成工单会创建新单，也受创建权限限制；原工单查看、重新编辑独立鉴权。
const creationPermissionDenied = computed(
  () =>
    !canCreateMaterialOrder.value &&
    !(props.embedded ? props.id : getRouteQueryValue(route.query.id)),
);

const countryNameMap = Object.fromEntries(
  (facebookCountries as { code: string; name: string }[]).map((c) => [
    c.code,
    c.name,
  ]),
);

function displayTag(rowKey: string, tag: string) {
  return rowKey === 'country' ? (countryNameMap[tag] ?? tag) : tag;
}

// ---- 步骤条 ----
const steps = [
  { title: '填写需求', description: '提交人' },
  { title: '审核分配', description: '素材中台' },
  { title: '素材制作', description: '素材师' },
  { title: '完成', description: '投放师' },
];
const currentStep = ref(0);

const statusToStep: Record<string, number> = {
  draft: 0,
  pending_review: 1,
  pending_assign: 1,
  assigned: 2,
  in_production: 2,
  pending_accept: 3,
  accepted: steps.length,
  archived: steps.length,
};

// ---- 基础信息 ----
const title = ref('');
const orderCreator = ref('');
const projectLoading = ref(false);
const requirementTypeOptions = reactive([
  { label: '视频', value: 'video' },
  { label: '图片', value: 'image' },
]);

const selectedProject = ref<string>();
const projectNames = ref<string[]>([]);
const projectRecords = ref<MaterialOrderProjectOption[]>([]);
const legacyProjectName = ref('');
const selectedProjectRecord = computed(() =>
  projectRecords.value.find((project) => project.id === selectedProject.value),
);
function getProjectProductInfo(project?: MaterialOrderProjectOption) {
  return project?.product_info?.trim() || '';
}

const projectOptions = computed(() => {
  const names = new Set(projectNames.value);
  const options = projectRecords.value
    .filter((project) => names.has(project.name))
    .map((project) => ({
      disabled: ['archived', 'ended'].includes(project.status),
      label: project.name,
      value: project.id,
    }));
  // project 提供显示名称，project_details 提供稳定 ID；历史名称仅用于回显。
  const linkedNames = new Set(
    projectRecords.value.map((project) => project.name),
  );
  if (legacyProjectName.value) names.add(legacyProjectName.value);
  for (const name of names) {
    if (!linkedNames.has(name)) {
      options.push({
        disabled: true,
        label: `${name}（历史项目）`,
        value: `legacy:${name}`,
      });
    }
  }
  return options;
});
const selectedType = ref<string>();
const deliveryCount = ref<number | null>(null);
const expectedDeliveryTime = ref();
const productInfo = ref<string>('');
const isGreenMaterial = ref<boolean | null>(null);

// 语种
const languageOptions = reactive([
  ...(languages as { label: string; value: string }[]),
]);
const selectedLanguage = ref<string | undefined>();

// 部门
const userStore = useUserStore();
const taskCenterStore = useTaskCenterStore();
const taskService = createTaskService(() => taskCenterStore.tasks, {
  acceptTask: taskCenterStore.acceptTask,
  completeTask: taskCenterStore.completeTask,
  patchTask: taskCenterStore.patchTask,
  rejectTask: taskCenterStore.rejectTask,
});
const userDepartment = ref(String(userStore.userInfo?.department ?? ''));
const taskScope = ref<'department' | 'personal'>('department');
const responsibleDepartmentId = ref<string>();
const ccUserId = ref<string>();
const executionDepartment = ref('美术中台部');
const orderVersion = ref(0);
const organizationLoading = ref(false);
interface OrganizationNode {
  value: string;
  label: string;
  selectable?: boolean;
  children?: OrganizationNode[];
}
const departmentTree = ref<OrganizationNode[]>([]);
const personnelTree = ref<OrganizationNode[]>([]);
const currentCreatorName = computed(
  () => orderCreator.value || String(userStore.userInfo?.full_name ?? ''),
);

/** 组织树中部门仅用于分组，抄送只能选择一个人员。 */
async function loadOrganization() {
  organizationLoading.value = true;
  try {
    const options = await getMaterialOrderOrganization();
    const departmentIds = new Set(options.departments.map((dept) => dept.id));
    function build(
      parentId: string,
      users: boolean,
      visited = new Set<string>(),
    ): OrganizationNode[] {
      return options.departments
        .filter((dept) => dept.parent_id === parentId && !visited.has(dept.id))
        .map((dept) => {
          const next = new Set([...visited, dept.id]);
          return {
            value: users ? `department:${dept.id}` : dept.id,
            label: `部门 · ${dept.name}`,
            selectable: !users,
            children: [
              ...build(dept.id, users, next),
              ...(users
                ? options.users
                    .filter((user) => user.department_id === dept.id)
                    .map((user) => ({
                      value: user.id,
                      label: `人员 · ${user.full_name}`,
                    }))
                : []),
            ],
          };
        });
    }
    const roots = [
      ...new Set(
        options.departments
          .filter((dept) => !departmentIds.has(dept.parent_id))
          .map((dept) => dept.parent_id),
      ),
    ];
    departmentTree.value = roots.flatMap((root) => build(root, false));
    personnelTree.value = roots.flatMap((root) => build(root, true));
    const unassigned = options.users.filter(
      (user) => !departmentIds.has(user.department_id),
    );
    if (unassigned.length)
      personnelTree.value.push({
        value: 'department:none',
        label: '未分配部门',
        selectable: false,
        children: unassigned.map((user) => ({
          value: user.id,
          label: `人员 · ${user.full_name}`,
        })),
      });
  } finally {
    organizationLoading.value = false;
  }
}

watch(taskScope, (scope) => {
  if (scope === 'personal') {
    responsibleDepartmentId.value = undefined;
    ccUserId.value = undefined;
  }
});
onMounted(() => {
  if (!creationPermissionDenied.value) void loadOrganization();
});

/** 服务端返回版本用于后续编辑，防止草稿保存覆盖新分配结果。 */
function applyWriteVersion(result: MaterialOrderWriteResult) {
  const data = result.response as { version?: number };
  if (typeof data?.version === 'number') orderVersion.value = data.version;
}
const sourceTaskContext = ref<CreateMaterialTaskContext>();
const sourceContextError = ref('');
const sourceLinkState = ref<MaterialOrderSourceLinkState>();

// 素材尺寸
const sizeList = ref<string[]>([]);
const sizeOptions = reactive([
  { label: '9*16(竖屏)', value: '9x16' },
  { label: '16*9(横屏)', value: '16x9' },
  { label: '1x1', value: '1x1' },
  { label: '其他', value: '其他' },
]);

// 优先级
type Priority = '' | 'P0' | 'P1' | 'P2';
const priorities = reactive<{ label: string; value: Priority }[]>([
  { label: 'P0 突发紧急', value: 'P0' },
  { label: 'P1 常规/迭代', value: 'P1' },
  { label: 'P2 素材储备', value: 'P2' },
]);
const selectedPriority = ref<Priority>('P2');

// ---- 标签 ----
interface TagRow {
  key: string;
  label: string;
  tags: string[];
  type: 'input' | 'auto';
  inputVisible: boolean;
  inputValue: string;
}

const tagRows = ref<TagRow[]>([
  {
    key: 'country',
    label: '国家',
    tags: [],
    type: 'auto',
    inputVisible: false,
    inputValue: '',
  },
  {
    key: 'theme',
    label: '题材',
    tags: [],
    type: 'input',
    inputVisible: false,
    inputValue: '',
  },
  {
    key: 'gameplay',
    label: '玩法',
    tags: [],
    type: 'input',
    inputVisible: false,
    inputValue: '',
  },
]);

function removeTag(rowKey: string, tag: string) {
  const row = tagRows.value.find((r) => r.key === rowKey);
  if (row) row.tags = row.tags.filter((t) => t !== tag);
}

// 题材/玩法 input 自动聚焦
const tagInputRefs: Record<string, any> = {};

function showTagInput(rowKey: string) {
  const row = tagRows.value.find((r) => r.key === rowKey);
  if (!row) return;
  row.inputVisible = true;
  nextTick(() => {
    tagInputRefs[rowKey]?.focus();
  });
}

// 题材/玩法：用户自由输入确认添加（最多10个，每个最多10字符）
function confirmTagInput(rowKey: string) {
  const row = tagRows.value.find((r) => r.key === rowKey);
  if (!row) return;
  const val = row.inputValue.trim();
  if (val && !row.tags.includes(val) && row.tags.length < 10) {
    if (val.length > 10) {
      message.warning('标签最多 10 个字符');
      return;
    }
    row.tags.push(val);
  }
  row.inputValue = '';
  row.inputVisible = false;
}

const isRestoring = ref(false);

function currentRequester() {
  const userInfo = userStore.userInfo as Record<string, unknown> | undefined;
  const requesterId = [userInfo?.userId, userInfo?.user_id, userInfo?._id].find(
    (value): value is string =>
      typeof value === 'string' ? Boolean(value.trim()) : false,
  );
  const requesterName = [
    userInfo?.realName,
    userInfo?.full_name,
    userInfo?.username,
    userInfo?.userName,
  ].find((value): value is string =>
    typeof value === 'string' ? Boolean(value.trim()) : false,
  );
  return { requesterId: requesterId ?? '', requesterName: requesterName ?? '' };
}

async function resolveSourceTaskContext(
  query: Record<string, unknown> = route.query,
) {
  const source = parseMaterialTaskSourceQuery(query);
  sourceTaskContext.value = undefined;
  sourceContextError.value = '';
  if (source.kind === 'manual') return;
  if (source.kind === 'invalid') {
    sourceContextError.value = source.reason;
    return;
  }

  try {
    const context = createMaterialTaskContext(source, currentRequester());
    const verified = await taskService.resolveMaterialTaskContext(context);
    if (
      !projectRecords.value.some((project) => project.id === verified.projectId)
    ) {
      throw new Error('来源投放任务所属项目已不可用，无法创建素材任务');
    }
    sourceTaskContext.value = verified;
    legacyProjectName.value = '';
    selectedProject.value = verified.projectId;
  } catch (error) {
    sourceContextError.value =
      error instanceof Error ? error.message : '来源投放任务上下文校验失败';
  }
}

watch(selectedProject, (newVal) => {
  if (isRestoring.value) return;
  const countryRow = tagRows.value.find((r) => r.key === 'country');
  if (!countryRow) return;
  const project = projectRecords.value.find((item) => item.id === newVal);
  legacyProjectName.value = '';
  // 清空项目时同步清空自动带入的国家，避免沿用上一个项目的标签。
  countryRow.tags = [...(project?.country_regions ?? [])];
  productInfo.value = getProjectProductInfo(project);
});

// ---- 需求描述 ----
interface AttachmentItem {
  object_key: string;
  name: string;
  download_url?: string;
  basename?: string;
  size?: number;
  content_type?: string;
  filetype?: string;
  url?: string;
  img?: string;
  width?: number;
  height?: number;
  duration?: number | null;
}

interface DescriptionRow {
  _rowId?: string;
  id?: string;
  description: string;
  duration: string;
  quantity: number | undefined;
  link: string;
  remark: string;
  compliance: string;
  attachments: AttachmentItem[];
}

const templatePickerOpen = ref(false);
const canManageRequirementTemplates = ref(false);
onMounted(() => {
  // 使用模板对所有人开放；管理入口只认业务服务返回的角色编码。
  void getCurrentUserRoleCodesApi()
    .then((roles) => {
      canManageRequirementTemplates.value = roles.includes('creator_leader');
    })
    .catch(() => {
      canManageRequirementTemplates.value = false;
    });
});

async function applyRequirementTemplate(
  items: RequirementTemplateItem[],
  mode: 'append' | 'replace',
) {
  if (readonlyMode.value) return;
  const currentRows: DescriptionRow[] =
    descGridApi.grid.getTableData().fullData;
  if (
    currentRows.some((row) =>
      getRowUploadFiles(row).some((file) => file.status === 'uploading'),
    )
  ) {
    message.warning('请等待当前附件上传完成后再使用模板');
    return;
  }
  const apply = async () => {
    // 每次应用都创建新的子需求 ID 和附件数组，工单编辑不会回写模板。
    const rows: DescriptionRow[] = items.map((item) => ({
      id: crypto.randomUUID(),
      description: item.description,
      duration: item.duration,
      quantity: item.quantity,
      link: item.link,
      remark: item.remark,
      compliance: item.compliance,
      attachments: item.attachments.map((file) => ({ ...file })),
    }));
    await descGridApi.grid.clearEdit();
    if (mode === 'replace') {
      for (const row of currentRows) delete localUploadMap[getRowKey(row)];
      await descGridApi.grid.loadData(rows);
    } else {
      await descGridApi.grid.insertAt(rows, -1);
    }
    syncDeliveryCount();
    message.success(
      `已${mode === 'replace' ? '替换' : '追加'} ${rows.length} 条子需求`,
    );
  };
  if (mode === 'replace' && currentRows.length) {
    Modal.confirm({
      title: '替换当前全部需求明细？',
      zIndex: 2300,
      content: `当前 ${currentRows.length} 条明细将被替换，模板内容不受影响。`,
      okText: '替换明细',
      cancelText: '取消',
      onOk: apply,
    });
  } else {
    await apply();
  }
}

const descriptionTableLoading = ref(false);
const pageLoading = ref(false);

const mockDescriptionRows: DescriptionRow[] = [];

const descGridOptions: VxeGridProps<DescriptionRow> = {
  autoResize: true,
  border: true,
  height: 440,
  columns: [
    { title: '序号', width: 70, slots: { default: 'seq_display' } },
    {
      field: 'description',
      title: '需求描述',
      minWidth: 200,
      editRender: { name: 'input', attrs: { placeholder: '请输入需求描述' } },
      slots: { edit: 'desc_edit' },
    },
    {
      field: 'duration',
      title: '时长',
      width: 85,
      editRender: { name: 'input', attrs: { placeholder: '如 15s' } },
      slots: { edit: 'duration_edit' },
    },
    {
      field: 'quantity',
      title: '数量',
      width: 60,
      editRender: {},
      slots: { default: 'quantity_display', edit: 'quantity_edit' },
    },
    {
      field: 'link',
      title: '相关链接',
      minWidth: 160,
      editRender: { name: 'input', attrs: { placeholder: '请输入链接' } },
      slots: { edit: 'link_edit' },
    },
    {
      field: 'remark',
      title: '备注',
      minWidth: 160,
      editRender: { name: 'input', attrs: { placeholder: '请输入备注' } },
      slots: { edit: 'remark_edit' },
    },
    {
      field: 'compliance',
      title: '合规要求',
      minWidth: 160,
      editRender: { name: 'input', attrs: { placeholder: '请输入合规要求' } },
      slots: { edit: 'compliance_edit' },
    },
    {
      field: 'attachments',
      title: '需求附件',
      minWidth: 130,
      slots: { default: 'attachments_display', header: 'attachments_header' },
    },
    {
      title: '操作',
      width: 240,
      align: 'center',
      slots: { default: 'desc_action' },
    },
  ],
  editConfig: {
    mode: 'row',
    showIcon: false,
    trigger: 'manual',
    autoClear: false,
  },
  keepSource: true,
  data: mockDescriptionRows,
  pagerConfig: { enabled: false },
  showOverflow: false,
};

const [DescGrid, descGridApi] = useVbenVxeGrid({
  gridOptions: descGridOptions,
});

function descriptionEditorPlacement(rowIndex: number) {
  // 首行向下、末行向上；空间不足时由编辑组件根据视口翻转。
  if (rowIndex === 0) return 'bottom';
  const lastIndex = descGridApi.grid.getTableData().fullData.length - 1;
  return rowIndex === lastIndex ? 'top' : 'auto';
}

function hasDescEditStatus(row: DescriptionRow) {
  return descGridApi.grid.isEditByRow(row);
}

function syncDeliveryCount() {
  const rows = descGridApi.grid.getTableData().fullData;
  deliveryCount.value = rows.reduce(
    (sum: number, r: DescriptionRow) => sum + (Number(r.quantity) || 0),
    0,
  );
}

function editDescRow(row: DescriptionRow) {
  descGridApi.grid.setEditRow(row);
}

function cancelDescRow() {
  descGridApi.grid.clearEdit();
}

function saveDescRow(row: DescriptionRow) {
  if (!row.description?.trim()) {
    message.error('请输入需求描述');
    return;
  }
  if (!row.quantity) {
    message.error('请输入数量');
    return;
  }
  descGridApi.grid.clearEdit();
  syncDeliveryCount();
}

async function deleteDescRow(row: DescriptionRow) {
  await descGridApi.grid.remove(row);
  syncDeliveryCount();
}

async function addDescRow() {
  const newRow: DescriptionRow = {
    id: crypto.randomUUID(),
    description: '',
    duration: '',
    quantity: undefined,
    link: '',
    remark: '',
    compliance: '',
    attachments: [],
  };
  const { row } = await descGridApi.grid.insertAt(newRow, -1);
  descGridApi.grid.setEditRow(row);
}

// ---- 参考资料 ----
interface RefFile {
  uid: string;
  name: string;
  type: 'image' | 'link' | 'mp4' | 'zip';
  meta: string;
  status?: 'uploading' | 'done';
  percent?: number;
  url?: string;
  // 上传成功后由后端返回的字段
  object_key?: string;
  size?: number;
  content_type?: string;
  filetype?: string;
  basename?: string;
  img?: string;
  width?: number;
  height?: number;
  duration?: number;
}

const refFiles = ref<RefFile[]>([]);
const { enqueue: enqueueRefUpload } = useUploadQueue(5);

const refDraggerHovered = ref(false);

function handleDocumentPaste(e: ClipboardEvent) {
  if (!refDraggerHovered.value) return;
  const items = e.clipboardData?.items;
  if (!items) return;
  for (const item of Array.from(items)) {
    const file = item.getAsFile();
    if (file && beforeUpload) void beforeUpload(file as any, []);
  }
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

function removeRefFile(uid: string) {
  refFiles.value = refFiles.value.filter((f) => f.uid !== uid);
}

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  if (!validateUploadFileSize(file, message.error)) return false;
  if (!validateFileType(file, ORDER_ATTACHMENT_ALLOWED_EXTS, message.error))
    return false;
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  const isCompressed =
    ORDER_ATTACHMENT_ARCHIVE_EXTS.includes(ext) ||
    COMPRESSED_MIMES.includes(file.type);
  const fileType: RefFile['type'] = isCompressed
    ? 'zip'
    : file.type.startsWith('video')
      ? 'mp4'
      : 'image';
  const tempUid = `uploading-${Date.now()}-${Math.random()}`;
  refFiles.value.push({
    uid: tempUid,
    name: file.name,
    type: fileType,
    meta: formatSize(file.size),
    status: 'uploading',
  });
  enqueueRefUpload(async () => {
    try {
      const taskResult: any = await uploadMaterialOrderAttachment(
        file as unknown as File,
        false,
        (p: number) => {
          const target = refFiles.value.find((f) => f.uid === tempUid);
          if (target) target.percent = p;
        },
      );
      const items: any[] = taskResult.items ?? [];
      const idx = refFiles.value.findIndex((f) => f.uid === tempUid);
      if (idx !== -1) {
        refFiles.value.splice(
          idx,
          1,
          ...items.map((res: any) => ({
            uid: res.object_key ?? `${tempUid}-${Math.random()}`,
            name: res.name ?? file.name,
            type: fileType,
            meta: formatSize(res.size ?? file.size),
            status: 'done' as const,
            object_key: res.object_key,
            size: res.size ?? file.size,
            content_type: res.content_type ?? file.type,
            filetype: res.filetype ?? ext,
            basename: res.basename ?? file.name,
            url: res.url,
            img: res.img,
            width: res.width,
            height: res.height,
            duration: res.duration,
          })),
        );
      }
      // 按 object_key 去重
      const seen = new Set<string>();
      const before = refFiles.value.length;
      refFiles.value = refFiles.value.filter((f) => {
        if (!f.object_key) return true;
        if (seen.has(f.object_key)) return false;
        seen.add(f.object_key);
        return true;
      });
      const dedupCount = before - refFiles.value.length;
      if (dedupCount > 0) {
        message.info(`已自动去重 ${dedupCount} 个重复文件`);
      }
    } catch {
      refFiles.value = refFiles.value.filter((f) => f.uid !== tempUid);
    }
  });
  return false;
};

// ---- 需求附件上传 ----
const uploadModalRef = ref<InstanceType<typeof UploadMaterialModal>>();
const rowUploadVisible = ref(false);
const rowUploadKey = ref('');
const uploadTargetRow = shallowRef<DescriptionRow | null>(null);

// localUploadMap 存于父组件响应式作用域，vxe-table slot 访问时可正确建立依赖追踪，
// 从而在文件状态/进度变化时自动重渲染附件列，无需手动调用 updateData()
const localUploadMap = reactive<Record<string, UploadFileItem[]>>({});

function handleUploadChange(key: string, files: UploadFileItem[]) {
  localUploadMap[key] = files;
}

function handleRowUploadAllDone(key: string) {
  const files = localUploadMap[key] ?? [];
  const seen = new Set<string>();
  const deduped = files.filter((f) => {
    if (!f.uploadData?.object_key) return true;
    if (seen.has(f.uploadData.object_key)) return false;
    seen.add(f.uploadData.object_key);
    return true;
  });
  if (deduped.length < files.length) {
    localUploadMap[key] = deduped;
    uploadModalRef.value?.initFiles(key, deduped);
    message.info(`已自动去重 ${files.length - deduped.length} 个重复附件`);
  }
}

// 统一获取行 key
function getRowKey(row: DescriptionRow): string {
  return row._rowId ?? row.id ?? (row as any)._X_ROW_KEY ?? '';
}

// 从 localUploadMap 读当前行所有文件；未初始化时回退到 row.attachments
function getRowUploadFiles(row: DescriptionRow): UploadFileItem[] {
  const key = getRowKey(row);
  const local = localUploadMap[key];
  if (local !== undefined) return local;
  // 尚未在 localUploadMap 中初始化时，从行数据直接派生（保持只读场景展示正常）
  return (row.attachments ?? []).map((a) => ({
    uid: a.object_key,
    name: a.name,
    status: 'done' as const,
    uploadData: a as any,
  }));
}

// 获取单个上传中的文件（避免模板中使用 ! 断言）
function getRowFirstUploading(row: DescriptionRow): UploadFileItem | null {
  return getRowUploadFiles(row).find((f) => f.status === 'uploading') ?? null;
}

// 将 UploadFileItem.uploadData 转为 AttachmentItem（避免模板中 as 类型转换）
function toAttachmentItem(f: UploadFileItem): AttachmentItem | undefined {
  return f.uploadData as AttachmentItem | undefined;
}

function retryRowFile(row: DescriptionRow, f: UploadFileItem) {
  uploadModalRef.value?.retryFile(getRowKey(row), f);
}

function removeErrorFile(row: DescriptionRow, f: UploadFileItem) {
  const key = getRowKey(row);
  const filtered = (localUploadMap[key] ?? []).filter(
    (item) => item.uid !== f.uid,
  );
  localUploadMap[key] = filtered;
  uploadModalRef.value?.initFiles(key, filtered);
}

// 以下包装函数用于模板，避免 ! 非空断言
function previewUploadItem(f: UploadFileItem) {
  const att = toAttachmentItem(f);
  if (att) openAttachmentPreview(att);
}

// ---- 参考资料打包下载 ----
const batchDownloadLoading = ref(false);

async function downloadBatch() {
  const keys = refFiles.value
    .filter((f) => f.status !== 'uploading' && f.object_key)
    .map((f) => f.object_key!);
  if (!keys.length) {
    message.warning('暂无可下载的参考资料');
    return;
  }
  batchDownloadLoading.value = true;
  try {
    const res = (await downloadAttachmentsZip(keys)) as any;
    downloadFileByUrl(res.url, res.filename);
  } catch {
  } finally {
    batchDownloadLoading.value = false;
  }
}

function downloadUploadItem(f: UploadFileItem) {
  const att = toAttachmentItem(f);
  if (att?.url)
    downloadFileByUrl(
      att.download_url || att.url,
      f.name || att.basename || 'download',
    );
}

function removeUploadItem(row: DescriptionRow, f: UploadFileItem) {
  const att = toAttachmentItem(f);
  if (att) removeAttachment(row, att);
}

function uploadItemImg(f: UploadFileItem): string | undefined {
  return toAttachmentItem(f)?.img;
}

function handleRowUploadModalClose(v: boolean) {
  rowUploadVisible.value = v;
  if (!v && uploadTargetRow.value) {
    // 关闭时（取消/点击遮罩）将 done 文件同步回行数据
    // handleCancel 已将 uploading 条目移出 localUploadMap，filter 做安全兜底
    const doneFiles = (localUploadMap[rowUploadKey.value] ?? []).filter(
      (f) => f.status === 'done',
    );
    uploadTargetRow.value.attachments = doneFiles.map(
      (f) => f.uploadData as AttachmentItem,
    );
    uploadTargetRow.value = null;
  }
}

function openRowUpload(row: DescriptionRow) {
  if (!row._rowId && !row.id) {
    row._rowId = `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }
  const key = getRowKey(row);

  // 若 localUploadMap 中尚无该行数据，从 row.attachments 初始化
  if (localUploadMap[key] === undefined) {
    localUploadMap[key] = (row.attachments ?? []).map((a) => ({
      uid: a.object_key,
      name: a.name,
      status: 'done' as const,
      uploadData: a as any,
    }));
  }

  if (getRowUploadFiles(row).length >= 5) {
    message.warning('最多上传 5 个附件');
    return;
  }
  uploadTargetRow.value = row;
  rowUploadKey.value = key;
  // 同步初始化弹窗内部的 uploadMap（供弹窗列表渲染用）
  uploadModalRef.value?.initFilesIfEmpty(key, localUploadMap[key]);
  rowUploadVisible.value = true;
}

function isAttachmentZip(att: AttachmentItem | undefined): boolean {
  if (!att) return false;
  return (
    ORDER_ATTACHMENT_ARCHIVE_EXTS.includes(att.filetype ?? '') ||
    COMPRESSED_MIMES.includes(att.content_type ?? '')
  );
}

function removeAttachment(row: DescriptionRow, att: AttachmentItem) {
  const attId = att.object_key || att.basename;
  row.attachments = row.attachments.filter(
    (a) => (a.object_key || a.basename) !== attId,
  );
  const key = getRowKey(row);
  // 仅在 localUploadMap 已初始化时同步更新，避免写入空 key 导致其他行共享污染
  if (localUploadMap[key] !== undefined) {
    localUploadMap[key] = localUploadMap[key].filter(
      (f) =>
        (f.uploadData?.object_key || (f.uploadData as any)?.basename) !== attId,
    );
    uploadModalRef.value?.initFiles(key, localUploadMap[key]);
  }
}

const rowDownloadingIds = ref<string[]>([]);

async function downloadAllAttachments(row: DescriptionRow) {
  const files = getRowUploadFiles(row).filter(
    (f) => f.status === 'done' && f.uploadData?.url,
  );
  if (!files.length) return;
  const key = getRowKey(row);
  rowDownloadingIds.value.push(key);
  try {
    if (files.length === 1) {
      const att = files[0]!.uploadData!;
      downloadFileByUrl(att.url!, att.basename || files[0]!.name);
    } else {
      const keys = files
        .filter((f) => f.uploadData?.object_key)
        .map((f) => f.uploadData!.object_key!);
      const res = (await downloadAttachmentsZip(keys)) as any;
      downloadFileByUrl(res.url, res.filename);
    }
  } finally {
    rowDownloadingIds.value = rowDownloadingIds.value.filter((k) => k !== key);
  }
}

// 附件预览
function openAttachmentPreview(att: AttachmentItem) {
  previewFile.value = {
    uid: att.object_key,
    name: att.name,
    type: att.content_type?.startsWith('video')
      ? 'mp4'
      : ORDER_ATTACHMENT_ARCHIVE_EXTS.includes(att.filetype ?? '') ||
          COMPRESSED_MIMES.includes(att.content_type ?? '')
        ? 'zip'
        : 'image',
    meta: att.size ? formatSize(att.size) : '',
    url: att.url,
    img: att.img,
    object_key: att.object_key,
    size: att.size,
    content_type: att.content_type,
    filetype: att.filetype,
    basename: att.basename,
    width: att.width,
    height: att.height,
    duration: att.duration ?? undefined,
  };
  previewVisible.value = true;
}

// ---- 操作按钮 ----
function buildOrderPayload(status: string) {
  const project = selectedProjectRecord.value;
  const source = sourceTaskContext.value;
  return {
    task_scope: taskScope.value,
    responsible_department_id:
      taskScope.value === 'department'
        ? (responsibleDepartmentId.value ?? null)
        : null,
    cc_user_id:
      taskScope.value === 'department' ? (ccUserId.value ?? null) : null,
    status,
    title: title.value,
    project:
      project?.name ||
      legacyProjectName.value ||
      selectedProject.value?.replace(/^legacy:/, '') ||
      '',
    ...(project ? { project_id: project.id } : {}),
    ...(source
      ? {
          requester_id: source.requesterId,
          requester_name: source.requesterName,
          source_task_id: source.sourceTaskId,
        }
      : {}),
    demand_type: selectedType.value ?? '',
    sizes: sizeList.value,
    quantity: deliveryCount.value ?? null,
    priority: selectedPriority.value,
    expected_delivery_at: expectedDeliveryTime.value
      ? expectedDeliveryTime.value.format('YYYY-MM-DD')
      : '',
    product_info: productInfo.value,
    is_green_material: isGreenMaterial.value,
    language: selectedLanguage.value ?? '',
    department: userDepartment.value,
    tags: Object.fromEntries(tagRows.value.map((r) => [r.key, r.tags])),
    requirements: descGridApi.grid
      .getTableData()
      .fullData.map((row: DescriptionRow) => {
        const { _rowId, ...rest } = row;
        const key = _rowId ?? rest.id ?? '';
        const localFiles = localUploadMap[key];
        const attachments = (
          localFiles !== undefined
            ? localFiles
                .filter((f: UploadFileItem) => f.status === 'done')
                .map((f: UploadFileItem) => f.uploadData as AttachmentItem)
            : ((rest.attachments ?? []) as AttachmentItem[])
        ).map((att: AttachmentItem) => ({ ...att, url: '' }));
        return {
          id: rest.id,
          description: rest.description,
          duration: rest.duration,
          quantity: rest.quantity ?? null,
          link: rest.link,
          remark: rest.remark,
          compliance: rest.compliance,
          attachments,
        };
      }),
    references: refFiles.value.map((f) => ({
      type: f.type === 'link' ? ('link' as const) : ('upload' as const),
      name: f.name,
      object_key: f.object_key,
      size: f.size,
      content_type: f.content_type,
      filetype: f.filetype,
      basename: f.basename,
      url: f.url,
      img: f.img,
      width: f.width,
      height: f.height,
      duration: f.duration,
    })),
  };
}

// ---- DatePicker 禁用今天之前的日期 ----
function disabledDate(current: dayjs.Dayjs) {
  return current && current < dayjs().startOf('day');
}

// ---- 附件查阅弹窗 ----
const attachViewVisible = ref(false);
const attachViewRow = shallowRef<DescriptionRow | null>(null);

function openAttachView(row: DescriptionRow) {
  if (!row._rowId && !row.id) {
    row._rowId = `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }
  const key = getRowKey(row);
  if (localUploadMap[key] === undefined) {
    localUploadMap[key] = (row.attachments ?? []).map((a) => ({
      uid: a.object_key,
      name: a.name,
      status: 'done' as const,
      uploadData: a as any,
    }));
  }
  attachViewRow.value = row;
  attachViewVisible.value = true;
}

function closeAttachView() {
  attachViewVisible.value = false;
  attachViewRow.value = null;
}

function retryAttachViewFile(f: UploadFileItem) {
  if (attachViewRow.value) retryRowFile(attachViewRow.value, f);
}
function removeAttachViewErrorFile(f: UploadFileItem) {
  if (attachViewRow.value) removeErrorFile(attachViewRow.value, f);
}
function removeAttachViewItem(f: UploadFileItem) {
  if (attachViewRow.value) removeUploadItem(attachViewRow.value, f);
}

// ---- 预览 ----
const previewVisible = ref(false);
const previewFile = ref<RefFile | null>(null);

function openPreview(file: RefFile) {
  previewFile.value = file;
  previewVisible.value = true;
}
function closePreview() {
  previewVisible.value = false;
  previewFile.value = null;
}

function resetForm() {
  taskScope.value = 'department';
  responsibleDepartmentId.value = undefined;
  ccUserId.value = undefined;
  userDepartment.value = String(userStore.userInfo?.department ?? '');
  orderVersion.value = 0;
  title.value = '';
  selectedProject.value = undefined;
  legacyProjectName.value = '';
  selectedType.value = undefined;
  deliveryCount.value = null;
  expectedDeliveryTime.value = undefined;
  productInfo.value = '';
  isGreenMaterial.value = null;
  sizeList.value = [];
  selectedPriority.value = 'P2';
  selectedLanguage.value = undefined;
  tagRows.value.forEach((r) => {
    r.tags = [];
    r.inputVisible = false;
    r.inputValue = '';
  });
  refFiles.value = [];
  descGridApi.grid.loadData([]);
  currentOrderId.value = '';
  currentOrderNo.value = '';
  saveState.value = 'idle';
  currentStep.value = 0;
}

const MSG_KEY = 'submit-result';
const submitting = ref(false);
const countdownTimer = ref<ReturnType<typeof setInterval> | null>(null);

onUnmounted(() => {
  if (countdownTimer.value) clearInterval(countdownTimer.value);
  message.destroy(MSG_KEY);
  document.removeEventListener('paste', handleDocumentPaste);
});
function hasActiveUploads(rows: DescriptionRow[]): boolean {
  return (
    refFiles.value.some((file) => file.status === 'uploading') ||
    rows.some((row) =>
      getRowUploadFiles(row).some((file) => file.status === 'uploading'),
    )
  );
}

function validateDraftForm(): boolean {
  if (sourceContextError.value) {
    message.error(sourceContextError.value);
    return false;
  }
  const rows = descGridApi.grid.getTableData().fullData as DescriptionRow[];
  const hasUserContent = Boolean(
    title.value.trim() ||
      selectedProject.value ||
      selectedType.value ||
      sizeList.value.length ||
      expectedDeliveryTime.value ||
      productInfo.value.trim() ||
      isGreenMaterial.value !== null ||
      selectedLanguage.value ||
      tagRows.value.some((row) => row.tags.length > 0) ||
      rows.length > 0 ||
      refFiles.value.length > 0,
  );

  if (!hasUserContent) {
    message.info('请至少填写一项内容后再保存草稿');
    return false;
  }
  if (hasActiveUploads(rows)) {
    message.warning('仍有文件正在上传，请等待上传完成后再保存草稿');
    return false;
  }
  return true;
}

function validateSubmitForm(): boolean {
  if (sourceContextError.value) {
    message.error(sourceContextError.value);
    return false;
  }
  if (!title.value.trim()) {
    message.error('请输入需求标题');
    return false;
  }
  if (!selectedProject.value) {
    message.error('请选择项目');
    return false;
  }
  if (!selectedProjectRecord.value && !editOrderMode.value) {
    message.error('所选项目已不可用，请重新选择项目');
    return false;
  }
  if (taskScope.value === 'department' && !responsibleDepartmentId.value) {
    message.error('请选择负责部门');
    return false;
  }
  if (!selectedType.value) {
    message.error('请选择需求类型');
    return false;
  }
  if (!sizeList.value.length) {
    message.error('请选择素材尺寸');
    return false;
  }
  if (!expectedDeliveryTime.value) {
    message.error('请选择预期交付时间');
    return false;
  }
  if (!selectedPriority.value) {
    message.error('请选择优先级');
    return false;
  }
  if (!selectedLanguage.value?.trim()) {
    message.error('请选择语种');
    return false;
  }
  if (isGreenMaterial.value === null) {
    message.error('请选择是否按绿通素材要求产出');
    return false;
  }
  if (!descGridApi.grid.getTableData().fullData.length) {
    message.error('请至少添加一条需求描述');
    return false;
  }
  const allDescRows = descGridApi.grid.getTableData()
    .fullData as DescriptionRow[];
  if (hasActiveUploads(allDescRows)) {
    message.warning('仍有文件正在上传，请等待上传完成后再提交');
    return false;
  }
  const editingIdx = allDescRows.findIndex((row) =>
    descGridApi.grid.isEditByRow(row),
  );
  if (editingIdx !== -1) {
    message.warning(
      `需求描述第 ${editingIdx + 1} 行正在编辑中，请保存后再提交`,
    );
    return false;
  }
  for (const row of allDescRows) {
    if (!row.description?.trim()) {
      message.error('需求描述存在未填写描述的行，请填写后再提交');
      return false;
    }
    if (!row.quantity) {
      message.error('需求描述存在未填写数量的行，请填写后再提交');
      return false;
    }
  }
  return true;
}

function getActionErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'string' && error.trim()) return error;
  if (!error || typeof error !== 'object') return fallback;

  const requestError = error as {
    message?: unknown;
    response?: { data?: { detail?: unknown; message?: unknown } };
  };
  const serverMessage =
    requestError.response?.data?.message ??
    requestError.response?.data?.detail ??
    requestError.message;
  return typeof serverMessage === 'string' && serverMessage.trim()
    ? serverMessage
    : fallback;
}

async function handleSubmit() {
  if (!canCreateMaterialOrder.value && !editOrderMode.value) {
    message.warning('没有新建素材工单权限');
    return;
  }
  if (
    readonlyMode.value ||
    projectLoading.value ||
    pageLoading.value ||
    resubmitLoadError.value ||
    saveState.value === 'saving'
  )
    return;
  if (!validateSubmitForm()) return;
  syncDeliveryCount();
  if (submitting.value) return;
  submitting.value = true;
  try {
    let taskCenterTaskCode = '';
    let orderWrite: MaterialOrderWriteResult;
    if (currentOrderId.value) {
      const submitStatus =
        editOrderMode.value &&
        (preserveStatusEdit.value ||
          !['draft', 'demand_rejected'].includes(originalStatus.value))
          ? originalStatus.value
          : 'pending_assign';
      orderWrite = await taskService.updateMaterialOrder(
        currentOrderId.value,
        {
          ...buildOrderPayload(submitStatus),
          version: orderVersion.value,
          ...(preserveStatusEdit.value ? { preserve_status: true } : {}),
        } as any,
        sourceTaskContext.value,
      );
    } else {
      orderWrite = await taskService.createMaterialOrder(
        buildOrderPayload('pending_assign') as any,
        sourceTaskContext.value,
      );
    }
    applyWriteVersion(orderWrite);
    sourceLinkState.value = orderWrite.sourceLinkState;
    const materialOrderId = orderWrite.materialOrderId ?? currentOrderId.value;
    if (materialOrderId) currentOrderId.value = materialOrderId;
    localStorage.removeItem(DRAFT_KEY);

    if (isTaskCenterCreation.value && !preserveStatusEdit.value) {
      taskCenterTaskCode = orderWrite.taskCenterTaskCode ?? '';
      if (!orderWrite.taskCenterTaskId) {
        throw new Error('素材工单未完成任务中心同步，请重试提交');
      }
    }

    if (sourceTaskContext.value && orderWrite.sourceLinkState !== 'linked') {
      message.warning({
        content:
          '素材需求已保存，但旧接口未建立来源投放任务关系；请在素材需求中补充追踪。',
        duration: 5,
      });
    }

    if (props.embedded) {
      message.success({
        content:
          editOrderMode.value || draftEditMode.value
            ? '保存成功'
            : '需求已提交',
        key: MSG_KEY,
      });
      if (!editOrderMode.value && !draftEditMode.value) resetForm();
      emit('back');
    } else if (editOrderMode.value || draftEditMode.value) {
      let count = 3;
      message.success({
        content: `保存成功，${count} 秒后自动返回`,
        key: MSG_KEY,
        duration: 0,
      });
      if (countdownTimer.value) clearInterval(countdownTimer.value);
      countdownTimer.value = setInterval(() => {
        count--;
        if (count > 0) {
          message.success({
            content: `保存成功，${count} 秒后自动返回`,
            key: MSG_KEY,
            duration: 0,
          });
        } else {
          clearInterval(countdownTimer.value!);
          countdownTimer.value = null;
          message.success({
            content: '正在返回...',
            key: MSG_KEY,
            duration: 1,
          });
          handleBack();
        }
      }, 1000);
    } else {
      if (isTaskCenterCreation.value) {
        message.success({
          content: taskCenterTaskCode
            ? `素材任务 ${taskCenterTaskCode} 已创建，当前待分配`
            : '素材任务已创建',
          key: MSG_KEY,
        });
        handleBack();
      } else {
        message.success({ content: '需求已提交', key: MSG_KEY });
        resetForm();
      }
    }
  } catch (error) {
    message.error({
      content: getActionErrorMessage(
        error,
        editOrderMode.value || draftEditMode.value
          ? '保存失败，请检查网络后重试；已填写内容不会丢失'
          : '提交失败，请检查网络后重试；已填写内容不会丢失',
      ),
      key: MSG_KEY,
      duration: 5,
    });
  } finally {
    submitting.value = false;
  }
}

// ---- 自动草稿缓存 ----
const DRAFT_KEY = 'requirement_draft_id';

type SaveState = 'idle' | 'saved' | 'saving';
const saveState = ref<SaveState>('idle');
const currentOrderId = ref<string>('');
const currentOrderNo = ref<string>('');
const currentOrderStatus = ref<string>('');

function markSaved() {
  saveState.value = 'saved';
}

async function autoSaveDraft() {
  if (
    !canCreateMaterialOrder.value ||
    readonlyMode.value ||
    editOrderMode.value ||
    preserveStatusEdit.value ||
    projectLoading.value ||
    pageLoading.value ||
    resubmitLoadError.value ||
    submitting.value ||
    saveState.value === 'saving'
  )
    return;
  if (!validateDraftForm()) return;
  syncDeliveryCount();
  saveState.value = 'saving';
  try {
    let orderWrite: MaterialOrderWriteResult;
    if (currentOrderId.value) {
      // 已有草稿 id，直接更新，不创建新工单
      orderWrite = await taskService.updateMaterialOrder(
        currentOrderId.value,
        { ...buildOrderPayload('draft'), version: orderVersion.value } as any,
        sourceTaskContext.value,
      );
    } else {
      // 首次保存：创建草稿并缓存 id
      orderWrite = await taskService.createMaterialOrder(
        buildOrderPayload('draft') as any,
        sourceTaskContext.value,
      );
      const id = orderWrite.materialOrderId;
      if (id) {
        currentOrderId.value = id;
        localStorage.setItem(DRAFT_KEY, id);
      }
      const response = orderWrite.response as {
        data?: { order_no?: string };
        order_no?: string;
      };
      const orderNo = response?.order_no ?? response?.data?.order_no;
      if (orderNo) currentOrderNo.value = orderNo;
    }
    applyWriteVersion(orderWrite);
    sourceLinkState.value = orderWrite.sourceLinkState;
    markSaved();
    message.success('草稿已保存');
  } catch (error) {
    saveState.value = 'idle';
    message.error({
      content: getActionErrorMessage(
        error,
        '草稿保存失败，请检查网络后重试；已填写内容不会丢失',
      ),
      key: 'save-draft-result',
      duration: 5,
    });
  }
}

// 公共表单回填逻辑
function fillFormFromOrder(order: any) {
  taskScope.value = order.task_scope;
  responsibleDepartmentId.value = order.responsible_department_id ?? undefined;
  ccUserId.value = order.cc_user_id ?? undefined;
  executionDepartment.value = order.execution_department;
  orderVersion.value = order.version;
  title.value = order.title ?? '';
  const storedProject = order.project_id ?? order.project;
  const matchedProject = projectRecords.value.find(
    (project) => project.id === storedProject || project.name === storedProject,
  );
  if (matchedProject) {
    legacyProjectName.value = '';
    selectedProject.value = matchedProject.id;
  } else if (order.project) {
    legacyProjectName.value = order.project;
    selectedProject.value = `legacy:${order.project}`;
  } else {
    legacyProjectName.value = '';
    selectedProject.value = undefined;
  }
  selectedType.value = order.demand_type ?? undefined;
  deliveryCount.value = order.quantity ?? null;
  selectedPriority.value = order.priority ?? '';
  if (order.expected_delivery_at) {
    expectedDeliveryTime.value = dayjs(order.expected_delivery_at).startOf(
      'day',
    );
  }
  // 官方台子名称由当前项目主数据注入；旧工单或已删除项目才回显历史值。
  productInfo.value = matchedProject
    ? getProjectProductInfo(matchedProject)
    : (order.product_info ?? '');
  isGreenMaterial.value = order.is_green_material ?? null;
  selectedLanguage.value = order.language ?? undefined;
  orderCreator.value = order.creator ?? '';
  if (order.department) userDepartment.value = order.department;
  sizeList.value = order.sizes ?? [];
  descGridApi.grid.loadData(
    (Array.isArray(order.requirements) ? order.requirements : []).map(
      (d: any) => ({
        ...d,
        compliance: d.compliance ?? '',
        attachments: d.attachments ?? [],
      }),
    ),
  );
  nextTick(() => syncDeliveryCount());
  const tags = order.tags ?? {};
  tagRows.value.find((r) => r.key === 'country')!.tags = tags.country ?? [];
  tagRows.value.find((r) => r.key === 'theme')!.tags = tags.theme ?? [];
  tagRows.value.find((r) => r.key === 'gameplay')!.tags = tags.gameplay ?? [];
  refFiles.value = (order.references ?? []).map((ref: any) => ({
    uid: ref.object_key ?? String(Date.now() + Math.random()),
    name: ref.name ?? ref.basename ?? '',
    type:
      ref.type === 'link'
        ? 'link'
        : ref.content_type?.startsWith('video')
          ? 'mp4'
          : ORDER_ATTACHMENT_ARCHIVE_EXTS.includes(ref.filetype ?? '') ||
              COMPRESSED_MIMES.includes(ref.content_type ?? '')
            ? 'zip'
            : 'image',
    meta: ref.size ? formatSize(ref.size) : '链接',
    url: ref.url,
    object_key: ref.object_key,
    size: ref.size,
    content_type: ref.content_type,
    filetype: ref.filetype,
    basename: ref.basename,
    img: ref.img,
    width: ref.width,
    height: ref.height,
    duration: ref.duration,
  }));
}

// 恢复草稿：从 localStorage 读取 id → 调接口 → 填回表单
async function restoreDraft() {
  const savedId = localStorage.getItem(DRAFT_KEY);
  if (!savedId) return;
  isRestoring.value = true;
  try {
    const res = await getMaterialOrderDetail(savedId);
    const order: any = (res as any)?.data ?? res;
    if (!order || order.status !== 'draft') {
      localStorage.removeItem(DRAFT_KEY);
      return;
    }
    currentOrderId.value = savedId;
    if (order.order_no) currentOrderNo.value = order.order_no;
    fillFormFromOrder(order);
    markSaved();
    message.success('已恢复上次未完成的草稿');
  } catch {
    localStorage.removeItem(DRAFT_KEY);
  } finally {
    await nextTick();
    isRestoring.value = false;
  }
}

/** 复制只回填需求内容；不走原单查看/编辑加载，避免把原单 ID 带入保存请求。 */
async function loadOrderForResubmit(orderId: string) {
  isRestoring.value = true;
  resubmitLoadError.value = '';
  try {
    const order = await getMaterialOrderDetail(orderId);
    if (!canResubmitMaterialOrder(order)) {
      throw new Error('只有已完成的素材任务可以再次提交');
    }
    resetForm();
    fillFormFromOrder({
      ...order,
      version: 0,
      creator: '',
      department: String(userStore.userInfo?.department ?? ''),
      requirements: order.requirements.map((row) => ({
        id: crypto.randomUUID(),
        description: row.description,
        duration: row.duration,
        quantity: row.quantity,
        link: row.link,
        remark: row.remark,
        compliance: row.compliance,
        attachments: row.attachments,
      })),
    });
    currentOrderStatus.value = 'draft';
    // 继续关联原来源投放任务，请求人仍取当前登录用户，工单和子需求使用新 ID。
    if (order.source_task_id) {
      await resolveSourceTaskContext({
        projectId: selectedProjectRecord.value?.id,
        sourceTaskId: order.source_task_id,
      });
    }
    message.info('已复用原工单信息，提交后将创建新工单');
  } catch (error) {
    resubmitLoadError.value = getActionErrorMessage(
      error,
      '原工单加载失败，请返回列表后重试',
    );
    message.error(resubmitLoadError.value);
  } finally {
    await nextTick();
    isRestoring.value = false;
  }
}

// 只读查看：从详情接口加载并回填表单，不启动自动保存
async function loadOrderForView(orderId: string, prefetchedOrder?: any) {
  isRestoring.value = true;
  try {
    let order: any = prefetchedOrder;
    if (!order) {
      const res = await getMaterialOrderDetail(orderId);
      order = (res as any)?.data ?? res;
    }
    if (!order) return;
    fillFormFromOrder(order);
    if (order.order_no) currentOrderNo.value = order.order_no;
    if (order.id) currentOrderId.value = order.id;
    currentOrderStatus.value = order.status ?? '';
    currentStep.value = statusToStep[order.status] ?? 0;
    if (props.embedded)
      emit('loaded', {
        orderNo: currentOrderNo.value,
        status: currentOrderStatus.value,
        title: title.value,
      });
  } catch {
  } finally {
    // 等 watch(selectedProject) watcher 先 flush，再释放 isRestoring
    // 否则 watcher 会在 isRestoring=false 后触发并覆盖 country tags
    await nextTick();
    isRestoring.value = false;
  }
}

const handleSaveDraft = debounce(autoSaveDraft, 500);
const handleSubmitDebounced = debounce(handleSubmit, 500);

onMounted(async () => {
  if (creationPermissionDenied.value) return;
  document.addEventListener('paste', handleDocumentPaste);
  const viewId = props.embedded ? (props.id ?? '') : (route.query.id as string);
  const resubmitId = props.embedded
    ? undefined
    : getRouteQueryValue(route.query.resubmitOrderId);
  const resubmitOrderId =
    typeof resubmitId === 'string' ? resubmitId.trim() : '';
  const isReadonly = props.embedded
    ? props.mode === 'readonly'
    : route.query.readonly === '1';
  const isEdit = props.embedded
    ? props.mode === 'edit'
    : route.query.edit === '1';
  const isNew = props.embedded
    ? props.mode === 'new'
    : route.path === '/workbench/tasks/create-material' ||
      route.query.new === '1';

  projectLoading.value = true;
  try {
    const projectResult = await getMaterialOrderFilterOptions({
      include_project_details: true,
    });
    if (!Array.isArray(projectResult.project_details)) {
      throw new Error('项目关联信息缺失');
    }
    projectNames.value = projectResult.project;
    projectRecords.value = projectResult.project_details;
    if (isTaskCenterCreation.value) {
      const [types, sizes, priorityOptions, languageValues] = await Promise.all(
        [
          getDictionaryOptions('MATERIAL_DEMAND_TYPE'),
          getDictionaryOptions('MATERIAL_SIZE'),
          getDictionaryOptions('TASK_PRIORITY'),
          getDictionaryOptions('MATERIAL_LANGUAGE'),
        ],
      );
      requirementTypeOptions.splice(0, requirementTypeOptions.length, ...types);
      sizeOptions.splice(0, sizeOptions.length, ...sizes);
      priorities.splice(
        0,
        priorities.length,
        ...(priorityOptions as { label: string; value: Priority }[]),
      );
      languageOptions.splice(0, languageOptions.length, ...languageValues);
    }
  } catch {
    if (isTaskCenterCreation.value) {
      message.error('项目选项或素材任务字典加载失败，请刷新页面后重试');
      pageLoading.value = false;
      return;
    }
  } finally {
    projectLoading.value = false;
  }

  await resolveSourceTaskContext(resubmitOrderId ? {} : route.query);

  if (viewId || resubmitOrderId || !isNew) pageLoading.value = true;
  try {
    if (resubmitOrderId) {
      await loadOrderForResubmit(resubmitOrderId);
    } else if (viewId && isReadonly) {
      readonlyMode.value = true;
      await loadOrderForView(viewId);
    } else if (viewId && isEdit) {
      const res = await getMaterialOrderDetail(viewId);
      const order = res;
      const canEdit = preserveStatusEdit.value
        ? canReeditMaterialOrder(order)
        : order.permissions.edit;
      if (
        !canEdit ||
        (order.status === 'draft' && !canCreateMaterialOrder.value)
      ) {
        readonlyMode.value = true;
        message.warning('当前工单状态或权限不允许编辑，已切换为只读查看');
        await loadOrderForView(viewId, order);
        return;
      }
      if (order.status === 'draft') {
        draftEditMode.value = true;
      } else {
        editOrderMode.value = true;
        originalStatus.value = order?.status ?? '';
      }
      await loadOrderForView(viewId, order);
    } else {
      if (!isNew) {
        // 平台数据加载完后再恢复草稿
        await restoreDraft();
      } else if (!props.embedded) {
        const queryProjectId = getRouteQueryValue(route.query.projectId);
        if (
          !sourceTaskContext.value &&
          typeof queryProjectId === 'string' &&
          projectRecords.value.some((project) => project.id === queryProjectId)
        ) {
          selectedProject.value = queryProjectId;
        }
      }
    }
  } finally {
    pageLoading.value = false;
  }
});
</script>

<template>
  <div class="adpulse-section-page material-task-form">
    <div v-if="creationPermissionDenied" class="space-y-4 p-4">
      <Alert
        type="warning"
        show-icon
        message="没有新建素材工单权限，请联系管理员开通。"
      />
      <Button @click="handleBack">返回</Button>
    </div>
    <div v-else class="w-full min-w-0">
      <div
        class="sticky top-0 z-50 rounded-lg border-b border-gray-200 bg-white p-2 sm:pr-3"
      >
        <div class="flex items-start gap-2 xl:items-center">
          <button
            v-if="!embedded"
            type="button"
            aria-label="返回上一页"
            class="flex min-h-9 min-w-9 items-center justify-center rounded-full bg-white text-sm text-gray-600 shadow-lg ring-1 ring-gray-200 transition-all hover:text-gray-900 hover:shadow-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            @click="handleBack"
          >
            <ChevronLeft class="h-4 w-4" />
          </button>
          <div class="min-w-0 flex-1">
            <div
              class="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between"
            >
              <h1
                class="shrink-0 text-lg font-semibold text-gray-900 sm:text-xl"
              >
                {{
                  readonlyMode
                    ? '需求详情'
                    : editOrderMode
                      ? '编辑需求'
                      : draftEditMode
                        ? '编辑草稿'
                        : isTaskCenterCreation
                          ? '新建素材任务'
                          : '新建素材需求'
                }}
              </h1>

              <div class="min-w-0 flex-1 overflow-x-auto xl:px-4">
                <Steps :current="currentStep" :responsive="false">
                  <Steps.Step v-for="(step, index) in steps" :key="index">
                    <template #title>
                      <span class="whitespace-nowrap text-xs sm:text-sm">{{
                        step.title
                      }}</span>
                      <span
                        class="ml-1.5 hidden text-xs font-normal text-gray-400 2xl:inline"
                        >{{ step.description }}</span
                      >
                    </template>
                  </Steps.Step>
                </Steps>
              </div>

              <div
                class="flex shrink-0 flex-wrap items-center justify-end gap-2"
              >
                <template
                  v-if="
                    currentOrderId &&
                    [
                      'in_production',
                      'pending_accept',
                      'accepted',
                      'archived',
                    ].includes(currentOrderStatus)
                  "
                >
                  <BaseButton
                    v-if="embedded"
                    @click="emit('goAccept', currentOrderId)"
                    >验收详情</BaseButton
                  >
                  <a
                    v-else
                    :href="
                      router.resolve({
                        path: '/requirement/detail',
                        query: buildLinkedDetailQuery({ id: currentOrderId }),
                      }).href
                    "
                    @click="
                      (e) => {
                        if (e.ctrlKey || e.metaKey || e.shiftKey) return;
                        e.preventDefault();
                        router.push({
                          path: '/requirement/detail',
                          query: buildLinkedDetailQuery({ id: currentOrderId }),
                        });
                      }
                    "
                  >
                    <BaseButton>验收详情</BaseButton>
                  </a>
                </template>

                <template v-if="!readonlyMode">
                  <BaseButton
                    v-if="!editOrderMode"
                    class="material-form-button"
                    size="sm"
                    :disabled="
                      projectLoading ||
                      pageLoading ||
                      !!resubmitLoadError ||
                      !canCreateMaterialOrder ||
                      submitting ||
                      saveState === 'saving'
                    "
                    @click="handleSaveDraft"
                  >
                    {{ saveState === 'saving' ? '保存中...' : '保存草稿' }}
                  </BaseButton>
                  <BaseButton
                    size="sm"
                    class="material-form-button material-form-button-primary"
                    variant="blue"
                    :loading="submitting"
                    :disabled="
                      projectLoading ||
                      pageLoading ||
                      !!resubmitLoadError ||
                      (!canCreateMaterialOrder && !editOrderMode) ||
                      saveState === 'saving'
                    "
                    @click="handleSubmitDebounced"
                    >{{
                      preserveStatusEdit ? '保存修改' : '提交需求'
                    }}</BaseButton
                  >
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>

      <Spin :spinning="pageLoading">
        <div class="space-y-3 py-4">
          <div
            v-if="resubmitLoadError || sourceContextError"
            class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-700"
            role="alert"
          >
            <template v-if="resubmitLoadError">{{
              resubmitLoadError
            }}</template>
            <template v-else>
              来源投放任务校验失败：{{
                sourceContextError
              }}。请返回任务中心重新发起。
            </template>
          </div>
          <div
            v-else-if="sourceTaskContext"
            class="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm leading-6 text-blue-700"
          >
            当前素材需求来源于投放任务
            {{ sourceTaskContext.sourceTaskId }}；项目已按稳定 ID 锁定。
            <span v-if="sourceLinkState === 'legacy-unlinked'" class="block">
              当前旧接口未支持来源字段，已按兼容格式保存，未建立来源任务关系。
            </span>
          </div>
          <div
            class="rounded-lg border border-gray-200 bg-white px-4 py-4 sm:px-6 sm:py-5"
          >
            <div class="mb-4 flex items-center justify-between">
              <h2
                class="flex items-center gap-2 text-base font-semibold text-gray-900"
              >
                <span class="bg-primary h-4 w-1 rounded"></span>
                基础信息
                <span
                  v-if="readonlyMode && orderCreator"
                  class="text-sm font-normal text-gray-500"
                  >需求方：{{ orderCreator }}</span
                >
              </h2>
            </div>

            <div
              class="basic-info-form grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6"
            >
              <div>
                <label class="mb-1.5 block text-sm text-gray-600"
                  >需求标题<span class="text-red-500">*</span></label
                >
                <Input
                  v-model:value="title"
                  placeholder="请输入"
                  :disabled="readonlyMode"
                  class="w-full"
                />
              </div>

              <div>
                <label class="mb-1.5 block text-sm text-gray-600"
                  >项目 <span class="text-red-500">*</span></label
                >
                <Select
                  v-model:value="selectedProject"
                  :options="projectOptions"
                  placeholder="请选择"
                  :disabled="readonlyMode || Boolean(sourceTaskContext)"
                  :allow-clear="!sourceTaskContext"
                  show-search
                  :filter-option="
                    (input, opt) =>
                      String(opt?.label ?? '')
                        .toLowerCase()
                        .includes(input.toLowerCase())
                  "
                  class="w-full"
                >
                  <template v-if="projectLoading" #notFoundContent>
                    <div class="flex justify-center py-3">
                      <Spin />
                    </div>
                  </template>
                </Select>
              </div>

              <div>
                <label
                  id="task-scope-label"
                  class="mb-1.5 block text-sm text-gray-600"
                  >任务归属 <span class="text-red-500">*</span></label
                >
                <RadioGroup
                  v-model:value="taskScope"
                  class="task-scope-control"
                  aria-labelledby="task-scope-label"
                  :disabled="
                    readonlyMode ||
                    (editOrderMode &&
                      !['draft', 'demand_rejected'].includes(originalStatus))
                  "
                >
                  <RadioButton value="department">部门任务</RadioButton>
                  <RadioButton value="personal">个人任务</RadioButton>
                </RadioGroup>
              </div>
              <div>
                <label
                  for="task-creator"
                  class="mb-1.5 block text-sm text-gray-600"
                  >创建人</label
                >
                <Input
                  id="task-creator"
                  :value="currentCreatorName"
                  disabled
                  class="w-full"
                />
              </div>
              <div>
                <label
                  for="execution-department"
                  class="mb-1.5 block text-sm text-gray-600"
                  >执行部门</label
                >
                <Input
                  id="execution-department"
                  :value="executionDepartment"
                  disabled
                  class="w-full"
                />
              </div>
              <div v-if="taskScope === 'department'">
                <label
                  for="task-cc-user"
                  class="mb-1.5 block text-sm text-gray-600"
                  >抄送</label
                >
                <TreeSelect
                  id="task-cc-user"
                  v-model:value="ccUserId"
                  :tree-data="personnelTree"
                  :loading="organizationLoading"
                  :disabled="readonlyMode"
                  allow-clear
                  show-search
                  tree-node-filter-prop="label"
                  placeholder="请选择人员（可选）"
                  class="w-full"
                />
              </div>
              <div>
                <label class="mb-1.5 block text-sm text-gray-600"
                  >类型 <span class="text-red-500">*</span></label
                >
                <Select
                  v-model:value="selectedType"
                  :options="requirementTypeOptions"
                  placeholder="请选择"
                  :disabled="readonlyMode"
                  class="w-full"
                />
              </div>

              <div>
                <label class="mb-1.5 block text-sm text-gray-600"
                  >交付数量</label
                >
                <div class="flex items-center gap-2">
                  <InputNumber
                    :value="deliveryCount ?? undefined"
                    disabled
                    placeholder="由需求描述数量自动汇总"
                    class="w-full"
                  />
                </div>
              </div>

              <div>
                <label class="mb-1.5 block text-sm text-gray-600"
                  >素材尺寸 <span class="text-red-500">*</span></label
                >
                <Select
                  v-model:value="sizeList"
                  mode="multiple"
                  :options="sizeOptions"
                  placeholder="请选择"
                  :disabled="readonlyMode"
                  max-tag-count="responsive"
                  show-search
                  :filter-option="
                    (input, opt) =>
                      String(opt?.label ?? '')
                        .toLowerCase()
                        .includes(input.toLowerCase())
                  "
                  class="material-size-select w-full"
                />
              </div>

              <div>
                <label class="mb-1.5 block text-sm text-gray-600"
                  >优先级 <span class="text-red-500">*</span></label
                >
                <Select
                  v-model:value="selectedPriority"
                  :options="priorities"
                  placeholder="请选择"
                  :disabled="readonlyMode"
                  class="w-full"
                />
              </div>

              <div v-if="taskScope === 'department'">
                <label
                  for="responsible-department"
                  class="mb-1.5 block text-sm text-gray-600"
                  >负责部门 <span class="text-red-500">*</span></label
                >
                <TreeSelect
                  id="responsible-department"
                  v-model:value="responsibleDepartmentId"
                  :tree-data="departmentTree"
                  :loading="organizationLoading"
                  :disabled="readonlyMode"
                  show-search
                  allow-clear
                  tree-node-filter-prop="label"
                  placeholder="请选择负责部门"
                  class="w-full"
                />
              </div>
              <div v-else>
                <label
                  for="creator-department"
                  class="mb-1.5 block text-sm text-gray-600"
                  >创建部门</label
                >
                <Input
                  id="creator-department"
                  :value="userDepartment"
                  disabled
                  class="w-full"
                />
              </div>

              <div>
                <label
                  for="material-language"
                  class="mb-1.5 block text-sm text-gray-600"
                  >语种
                  <span class="text-red-500" aria-hidden="true">*</span></label
                >
                <Select
                  id="material-language"
                  v-model:value="selectedLanguage"
                  :options="languageOptions"
                  aria-required="true"
                  placeholder="请选择语种"
                  :disabled="readonlyMode"
                  allow-clear
                  show-search
                  :filter-option="
                    (input, opt) =>
                      String(opt?.label ?? '')
                        .toLowerCase()
                        .includes(input.toLowerCase())
                  "
                  class="w-full"
                />
              </div>

              <div>
                <label
                  class="mb-1.5 flex items-center gap-1 text-sm text-gray-600"
                >
                  按绿通素材要求产出 <span class="text-red-500">*</span>
                  <Tooltip
                    placement="top"
                    :overlay-style="{ maxWidth: '320px' }"
                  >
                    <template #title>
                      <div class="space-y-1 leading-snug">
                        <p>1. 不能出现货币符号（如雷亚尔 R$ 要写成 RS）</p>
                        <p>
                          2. 不能出现 .com（如产品信息是 86W.com，素材里只能出现
                          86W）
                        </p>
                      </div>
                    </template>
                    <span
                      class="icon-[ant-design--info-circle-outlined] text-gray-400"
                    />
                  </Tooltip>
                </label>
                <div
                  aria-label="是否按绿通素材要求产出"
                  class="green-material-options"
                  role="group"
                >
                  <button
                    v-for="opt in [
                      { label: '是', value: true },
                      { label: '否', value: false },
                    ]"
                    :key="String(opt.value)"
                    type="button"
                    :class="[
                      'green-material-option',
                      {
                        'is-selected': isGreenMaterial === opt.value,
                      },
                    ]"
                    :aria-pressed="isGreenMaterial === opt.value"
                    :aria-label="`按绿通素材要求：${opt.label}`"
                    :disabled="readonlyMode"
                    @click="!readonlyMode && (isGreenMaterial = opt.value)"
                  >
                    {{ opt.label }}
                  </button>
                </div>
              </div>

              <div>
                <label class="mb-1.5 block text-sm text-gray-600"
                  >预期交付时间 <span class="text-red-500">*</span></label
                >
                <DatePicker
                  v-model:value="expectedDeliveryTime"
                  format="YYYY-MM-DD"
                  placeholder="请选择"
                  :disabled="readonlyMode"
                  :disabled-date="disabledDate"
                  class="w-full"
                />
              </div>

              <div>
                <label class="mb-1.5 block text-sm text-gray-600"
                  >官方台子名称</label
                >
                <Input
                  v-model:value="productInfo"
                  disabled
                  placeholder="由项目产品信息自动带入"
                  class="w-full"
                />
              </div>
            </div>
          </div>

          <div
            class="rounded-lg border border-gray-200 bg-white px-4 py-4 sm:px-6 sm:py-5"
          >
            <h2
              class="mb-1 flex items-center gap-2 text-base font-semibold text-gray-900"
            >
              <span class="bg-primary h-4 w-1 rounded"></span>
              标签
              <span class="text-sm font-normal text-gray-400"
                >帮助素材中台分类与检索</span
              >
            </h2>

            <div class="mt-4 space-y-3">
              <div
                v-for="row in tagRows"
                :key="row.key"
                class="flex items-center gap-3"
              >
                <span class="w-10 shrink-0 text-sm text-gray-500">{{
                  row.label
                }}</span>
                <div class="flex flex-wrap items-center gap-2">
                  <Tag
                    v-for="tag in row.tags"
                    :key="tag"
                    :closable="!readonlyMode && row.type !== 'auto'"
                    class="rounded px-2 py-0.5 text-sm"
                    @close="removeTag(row.key, tag)"
                  >
                    {{ displayTag(row.key, tag) }}
                  </Tag>

                  <template v-if="row.type === 'auto'">
                    <span
                      v-if="row.tags.length === 0"
                      class="text-sm text-gray-400"
                    >
                      {{ selectedProject ? '项目未配置国家' : '请先选择项目' }}
                    </span>
                  </template>

                  <!-- 题材/玩法 -->
                  <template v-else-if="row.type === 'input' && !readonlyMode">
                    <Input
                      v-if="row.inputVisible"
                      :ref="
                        (el) => {
                          if (el) tagInputRefs[row.key] = el;
                        }
                      "
                      :value="row.inputValue"
                      :maxlength="10"
                      size="small"
                      class="w-[80px] text-sm"
                      @blur="confirmTagInput(row.key)"
                      @change="(e) => (row.inputValue = e.target.value || '')"
                      @pressEnter="confirmTagInput(row.key)"
                    />
                    <button
                      v-else-if="row.tags.length < 10"
                      type="button"
                      class="cursor-pointer rounded border border-dashed border-gray-300 px-2 py-0.5 text-sm text-gray-500 hover:border-blue-400 hover:text-blue-500"
                      @click="showTagInput(row.key)"
                    >
                      + 添加
                    </button>
                    <span
                      v-if="row.tags.length > 0"
                      class="text-sm text-gray-300"
                      >{{ row.tags.length }}/10</span
                    >
                  </template>
                </div>
              </div>
            </div>
          </div>

          <div
            class="space-y-4 rounded-lg border border-gray-200 bg-white px-4 py-4 sm:px-6 sm:py-5"
          >
            <div class="flex items-center justify-between">
              <h2
                class="flex items-center gap-2 text-base font-semibold text-gray-900"
              >
                <span class="bg-primary h-4 w-1 rounded"></span>
                需求描述 <span class="text-red-500">*</span>
              </h2>
              <div
                v-if="!readonlyMode"
                class="flex flex-wrap items-center gap-2"
              >
                <BaseButton
                  class="material-form-button material-form-button-primary material-form-template-button"
                  size="sm"
                  variant="blue"
                  aria-haspopup="dialog"
                  :aria-expanded="templatePickerOpen"
                  @click="templatePickerOpen = true"
                >
                  <IconifyIcon
                    icon="lucide:layout-template"
                    class="size-3 shrink-0"
                    aria-hidden="true"
                  />
                  <span>使用模板</span>
                </BaseButton>
                <BaseButton
                  class="material-form-button material-form-button-primary"
                  variant="blue"
                  @click="addDescRow"
                  ><span>新增</span></BaseButton
                >
              </div>
            </div>
            <Spin :spinning="descriptionTableLoading">
              <DescGrid class="[&_.vxe-grid]:!px-0">
                <template #seq_display="{ rowIndex }"
                  >需求{{ rowIndex + 1 }}</template
                >
                <template #desc_edit="{ row, rowIndex }">
                  <ExpandableDescriptionInput
                    :value="row.description"
                    :label="`需求${rowIndex + 1}的描述`"
                    :placement="descriptionEditorPlacement(rowIndex)"
                    placeholder="素材要求、活动内容、风格要求"
                    @update:value="(v) => (row.description = v)"
                  />
                </template>
                <template #duration_edit="{ row }">
                  <Input
                    :value="row.duration"
                    style="width: 100%"
                    @update:value="(v) => (row.duration = v)"
                  />
                </template>
                <template #quantity_display="{ row }">{{
                  row.quantity ?? '-'
                }}</template>
                <template #quantity_edit="{ row }">
                  <InputNumber
                    :value="row.quantity"
                    :min="1"
                    style="width: 100%"
                    @update:value="(v) => (row.quantity = v)"
                  />
                </template>
                <template #link_edit="{ row, rowIndex }">
                  <ExpandableDescriptionInput
                    :value="row.link"
                    :label="`需求${rowIndex + 1}的相关链接`"
                    :placement="descriptionEditorPlacement(rowIndex)"
                    placeholder="请输入链接"
                    @update:value="(v) => (row.link = v)"
                  />
                </template>
                <template #remark_edit="{ row, rowIndex }">
                  <ExpandableDescriptionInput
                    :value="row.remark"
                    :label="`需求${rowIndex + 1}的备注`"
                    :placement="descriptionEditorPlacement(rowIndex)"
                    placeholder="请输入备注"
                    @update:value="(v) => (row.remark = v)"
                  />
                </template>
                <template #compliance_edit="{ row, rowIndex }">
                  <ExpandableDescriptionInput
                    :value="row.compliance"
                    :label="`需求${rowIndex + 1}的合规要求`"
                    :placement="descriptionEditorPlacement(rowIndex)"
                    placeholder="请输入合规要求"
                    @update:value="(v) => (row.compliance = v)"
                  />
                </template>
                <template #attachments_header>
                  <span>需求附件</span>
                  <Tooltip
                    title="最多上传 5 个附件，如需上传更多文件，请上传压缩包"
                  >
                    <span
                      class="icon-[ant-design--info-circle-outlined] ml-1 cursor-pointer text-gray-400"
                    />
                  </Tooltip>
                </template>
                <template #attachments_display="{ row }">
                  <div class="flex flex-wrap items-center gap-1 py-1">
                    <!-- 上传中：单文件显示进度条，多文件显示 hover popover -->
                    <template
                      v-if="
                        getRowUploadFiles(row).some(
                          (f) => f.status === 'uploading',
                        )
                      "
                    >
                      <template
                        v-if="
                          getRowUploadFiles(row).filter(
                            (f) => f.status === 'uploading',
                          ).length === 1
                        "
                      >
                        <div class="flex min-w-0 items-center gap-1">
                          <span
                            class="max-w-[60px] truncate text-xs text-gray-500"
                            :title="getRowFirstUploading(row)?.name"
                          >
                            {{ getRowFirstUploading(row)?.name }}
                          </span>
                          <template
                            v-if="
                              getRowFirstUploading(row)?.percent !==
                                undefined &&
                              (getRowFirstUploading(row)?.percent ?? 0) < 100
                            "
                          >
                            <Progress
                              :percent="getRowFirstUploading(row)?.percent"
                              :stroke-width="3"
                              style="width: 70px"
                              status="active"
                            />
                          </template>
                          <template
                            v-else-if="
                              getRowFirstUploading(row)?.percent === 100
                            "
                          >
                            <span
                              class="icon-[ant-design--loading-outlined] animate-spin text-xs text-blue-400"
                            />
                            <span class="text-xs text-gray-400">处理中</span>
                          </template>
                          <template v-else>
                            <span
                              class="icon-[ant-design--loading-outlined] animate-spin text-xs text-gray-300"
                            />
                            <span class="text-xs text-gray-300">等待中</span>
                          </template>
                        </div>
                      </template>
                      <template v-else>
                        <Popover placement="bottom" trigger="hover">
                          <template #content>
                            <div
                              class="max-h-[200px] max-w-[260px] space-y-2 overflow-y-auto"
                            >
                              <div
                                v-for="f in getRowUploadFiles(row).filter(
                                  (fi) => fi.status === 'uploading',
                                )"
                                :key="f.uid"
                                class="flex min-w-0 items-center gap-2"
                              >
                                <span
                                  class="flex-1 truncate text-xs text-gray-600"
                                  :title="f.name"
                                  >{{ f.name }}</span
                                >
                                <template
                                  v-if="
                                    f.percent !== undefined && f.percent < 100
                                  "
                                >
                                  <Progress
                                    :percent="f.percent"
                                    :stroke-width="3"
                                    style="width: 70px"
                                    status="active"
                                  />
                                </template>
                                <span
                                  v-else
                                  class="flex-shrink-0 text-xs text-gray-400"
                                  >{{
                                    f.percent === 100 ? '处理中' : '等待中'
                                  }}</span
                                >
                              </div>
                            </div>
                          </template>
                          <div class="flex cursor-pointer items-center gap-1">
                            <span
                              class="icon-[ant-design--loading-outlined] animate-spin text-xs text-blue-400"
                            />
                            <span class="text-xs text-blue-400"
                              >上传中 ({{
                                getRowUploadFiles(row).filter(
                                  (f) => f.status === 'uploading',
                                ).length
                              }})</span
                            >
                          </div>
                        </Popover>
                      </template>
                    </template>

                    <Tooltip
                      v-for="f in getRowUploadFiles(row).filter(
                        (fi) => fi.status === 'done',
                      )"
                      :key="f.uid"
                      placement="top"
                    >
                      <template #title>
                        <div class="flex gap-3">
                          <button
                            v-if="!isAttachmentZip(toAttachmentItem(f))"
                            type="button"
                            class="rounded hover:text-blue-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                            @click="previewUploadItem(f)"
                          >
                            预览
                          </button>
                          <button
                            v-if="toAttachmentItem(f)?.url"
                            type="button"
                            class="rounded hover:text-blue-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                            @click.stop="downloadUploadItem(f)"
                          >
                            下载
                          </button>
                          <button
                            v-if="!readonlyMode"
                            type="button"
                            class="rounded hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                            @click.stop="removeUploadItem(row, f)"
                          >
                            删除
                          </button>
                        </div>
                      </template>
                      <div
                        tabindex="0"
                        :aria-label="`附件 ${f.name}`"
                        :class="[
                          'flex h-8 w-8 flex-shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded text-[9px] font-bold uppercase focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
                          !uploadItemImg(f) &&
                            (toAttachmentItem(f)?.content_type?.startsWith(
                              'video',
                            )
                              ? 'bg-gray-700 text-white'
                              : isAttachmentZip(toAttachmentItem(f))
                                ? 'bg-yellow-200 text-yellow-600'
                                : 'bg-blue-50 text-blue-600'),
                        ]"
                      >
                        <img
                          v-if="uploadItemImg(f)"
                          :src="`data:image/png;base64,${uploadItemImg(f)}`"
                          :alt="f.name"
                          class="h-full w-full object-cover"
                        />
                        <template v-else>
                          {{
                            toAttachmentItem(f)?.content_type?.startsWith(
                              'video',
                            )
                              ? 'MP4'
                              : isAttachmentZip(toAttachmentItem(f))
                                ? 'ZIP'
                                : (
                                    toAttachmentItem(f)?.filetype ??
                                    toAttachmentItem(f)?.content_type?.split(
                                      '/',
                                    )[1] ??
                                    '?'
                                  )
                                    .slice(0, 3)
                                    .toUpperCase()
                          }}
                        </template>
                      </div>
                    </Tooltip>

                    <template v-if="!readonlyMode">
                      <Tooltip
                        v-for="f in getRowUploadFiles(row).filter(
                          (fi) => fi.status === 'error',
                        )"
                        :key="f.uid"
                        placement="top"
                      >
                        <template #title>
                          <div class="flex gap-3">
                            <button
                              type="button"
                              class="rounded hover:text-blue-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                              @click="retryRowFile(row, f)"
                            >
                              重试
                            </button>
                            <button
                              type="button"
                              class="rounded hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                              @click.stop="removeErrorFile(row, f)"
                            >
                              删除
                            </button>
                          </div>
                        </template>
                        <div
                          role="button"
                          tabindex="0"
                          :aria-label="`重试上传 ${f.name}`"
                          class="flex h-8 w-8 flex-shrink-0 cursor-pointer flex-col items-center justify-center rounded border border-red-200 bg-red-50 transition-colors hover:bg-red-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                          @click="retryRowFile(row, f)"
                          @keydown.enter="retryRowFile(row, f)"
                          @keydown.space.prevent="retryRowFile(row, f)"
                        >
                          <span class="text-[10px] leading-none text-red-400"
                            >失败</span
                          >
                        </div>
                      </Tooltip>
                    </template>

                    <!-- "+" 按钮：剩余可上传槽数，非只读时显示 -->
                    <button
                      v-if="
                        !readonlyMode &&
                        hasDescEditStatus(row) &&
                        getRowUploadFiles(row).length < 5
                      "
                      type="button"
                      aria-label="上传需求附件"
                      class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded border border-dashed border-gray-300 text-base leading-none text-gray-400 transition-colors hover:border-blue-400 hover:text-blue-500"
                      @click="openRowUpload(row)"
                    >
                      +
                    </button>

                    <!-- 只读且无文件时 -->
                    <span
                      v-if="
                        readonlyMode &&
                        getRowUploadFiles(row).every(
                          (f) =>
                            f.status !== 'done' && f.status !== 'uploading',
                        )
                      "
                      class="text-xs text-gray-300"
                      >-</span
                    >
                  </div>
                </template>
                <template #desc_action="{ row }">
                  <template v-if="!readonlyMode">
                    <template v-if="hasDescEditStatus(row)">
                      <Button danger class="mr-1" @click="saveDescRow(row)"
                        >保存</Button
                      >
                      <Button @click="cancelDescRow()">取消</Button>
                    </template>
                    <template v-else>
                      <Button class="mr-1" @click="editDescRow(row)"
                        >编辑</Button
                      >
                      <Button
                        v-if="
                          getRowUploadFiles(row).filter(
                            (f) => f.status === 'done',
                          ).length > 0
                        "
                        size="small"
                        class="mr-1"
                        @click="openAttachView(row)"
                        >查看附件</Button
                      >
                      <Button
                        v-if="
                          getRowUploadFiles(row)
                            .filter((f) => f.status === 'done')
                            .some((f) => f.uploadData?.url)
                        "
                        size="small"
                        class="mr-1"
                        :disabled="rowDownloadingIds.includes(getRowKey(row))"
                        @click="downloadAllAttachments(row)"
                        >{{
                          rowDownloadingIds.includes(getRowKey(row))
                            ? '下载中...'
                            : '下载'
                        }}</Button
                      >
                      <Popconfirm
                        :title="`确定删除「${row.description || '该条'}」需求描述吗？`"
                        ok-text="确定"
                        cancel-text="取消"
                        @confirm="deleteDescRow(row)"
                      >
                        <Button danger>删除</Button>
                      </Popconfirm>
                    </template>
                  </template>
                  <template
                    v-else-if="
                      getRowUploadFiles(row).filter((f) => f.status === 'done')
                        .length > 0
                    "
                  >
                    <Button class="mr-2" @click="openAttachView(row)"
                      >查看附件</Button
                    >
                    <Button
                      v-if="
                        getRowUploadFiles(row)
                          .filter((f) => f.status === 'done')
                          .some((f) => f.uploadData?.url)
                      "
                      size="small"
                      :disabled="rowDownloadingIds.includes(getRowKey(row))"
                      @click="downloadAllAttachments(row)"
                      >{{
                        rowDownloadingIds.includes(getRowKey(row))
                          ? '下载中...'
                          : '全部下载'
                      }}</Button
                    >
                  </template>
                </template>
              </DescGrid>
            </Spin>
          </div>

          <div
            class="rounded-lg border border-gray-200 bg-white px-4 py-4 sm:px-6 sm:py-5"
          >
            <div class="mb-4 flex items-center justify-between">
              <h2
                class="flex items-center gap-2 text-base font-semibold text-gray-900"
              >
                <span class="bg-primary h-4 w-1 rounded"></span>
                参考资料
                <span class="text-sm font-normal text-gray-400"
                  >支持图片 / 视频 / 压缩文件</span
                >
              </h2>
              <BaseButton
                v-if="readonlyMode"
                :loading="batchDownloadLoading"
                @click="downloadBatch"
                >打包下载</BaseButton
              >
            </div>

            <!-- 拖拽上传（hover 后支持 Ctrl+V 粘贴） -->
            <div
              v-if="!readonlyMode"
              class="mb-4"
              @mouseenter="refDraggerHovered = true"
              @mouseleave="refDraggerHovered = false"
            >
              <Upload.Dragger
                :before-upload="beforeUpload"
                :show-upload-list="false"
                :multiple="true"
              >
                <div class="py-8 text-center">
                  <div
                    class="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full border border-gray-200 text-[28px] font-bold text-gray-600"
                  >
                    ↑
                  </div>
                  <p class="text-base text-gray-700">
                    拖拽文件到此处，或悬停后 Ctrl+V 粘贴
                  </p>
                  <p class="text-sm text-gray-400">
                    单文件 ≤ 10 GB，支持视频（MP4/MOV）/
                    图片（PNG/JPG/JPEG/GIF）/ 压缩包（ZIP/7Z）
                  </p>
                </div>
              </Upload.Dragger>
            </div>

            <!-- <div v-if="!readonlyMode" class="mb-4 flex items-center gap-2">
          <BaseButton @click="addLinkRef">
            <IconifyIcon class="mr-1" icon="lucide:library" />从素材库引用
          </BaseButton>
        </div> -->

            <!-- 文件列表 -->
            <div
              v-if="refFiles.length"
              class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6"
            >
              <div
                v-for="file in refFiles"
                :key="file.uid"
                class="flex items-center justify-between rounded border border-gray-100 px-3 py-2"
              >
                <!-- 上传中 -->
                <template v-if="file.status === 'uploading'">
                  <div class="flex min-w-0 flex-1 items-center gap-2">
                    <div
                      class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded bg-gray-50"
                    >
                      <span
                        class="icon-[ant-design--loading-outlined] animate-spin text-lg text-blue-400"
                      />
                    </div>
                    <div class="min-w-0 flex-1">
                      <p class="truncate text-sm text-gray-800">
                        {{ file.name }}
                      </p>
                      <template
                        v-if="file.percent !== undefined && file.percent < 100"
                      >
                        <Progress
                          :percent="file.percent"
                          :stroke-width="3"
                          status="active"
                        />
                      </template>
                      <template v-else-if="file.percent === 100">
                        <p class="text-xs text-gray-400">处理中...</p>
                      </template>
                      <template v-else>
                        <p class="text-xs text-blue-400">上传中...</p>
                      </template>
                    </div>
                  </div>
                </template>
                <!-- 已完成 -->
                <template v-else>
                  <div class="flex min-w-0 items-center gap-2">
                    <div
                      :class="[
                        'flex h-10 w-10 flex-shrink-0 items-center justify-center overflow-hidden rounded text-sm font-bold uppercase',
                        !file.img &&
                          (file.type === 'mp4'
                            ? 'bg-gray-700 text-white'
                            : file.type === 'zip'
                              ? 'bg-yellow-50 text-yellow-600'
                              : file.type === 'image'
                                ? 'bg-blue-50 text-blue-600'
                                : 'bg-green-100 text-green-700'),
                      ]"
                    >
                      <img
                        v-if="file.img"
                        :src="`data:image/png;base64,${file.img}`"
                        :alt="file.name"
                        class="h-full w-full object-cover"
                      />
                      <template v-else>
                        {{
                          file.type === 'link'
                            ? 'LINK'
                            : file.type.toUpperCase()
                        }}
                      </template>
                    </div>
                    <div class="min-w-0">
                      <p
                        class="truncate text-sm text-gray-800"
                        :title="file.name"
                      >
                        {{ file.name }}
                      </p>
                      <p class="text-sm text-gray-400">{{ file.meta }}</p>
                    </div>
                  </div>
                  <div class="ml-2 flex flex-shrink-0 items-center gap-2">
                    <button
                      v-if="file.type !== 'zip'"
                      type="button"
                      class="rounded text-sm text-blue-500 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                      @click="openPreview(file)"
                    >
                      预览
                    </button>
                    <button
                      v-if="file.url"
                      type="button"
                      class="rounded text-sm text-blue-500 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                      @click="
                        downloadFileByUrl(
                          file.url,
                          file.name || file.basename || 'download',
                        )
                      "
                    >
                      下载
                    </button>
                    <button
                      v-if="!readonlyMode"
                      type="button"
                      :aria-label="`删除参考资料 ${file.name}`"
                      class="rounded px-1 text-gray-400 hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                      @click="removeRefFile(file.uid)"
                    >
                      ×
                    </button>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </div>
      </Spin>
    </div>

    <!-- 附件查阅弹窗 -->
    <Modal
      :open="attachViewVisible"
      :footer="null"
      :width="'min(700px, calc(100vw - 24px))'"
      :body-style="{ maxHeight: '72dvh', overflowY: 'auto' }"
      destroy-on-close
      @cancel="closeAttachView"
    >
      <template #title>
        <div class="flex min-w-0 items-center">
          <span class="shrink-0">需求附件</span>
          <OverflowTooltip
            v-if="attachViewRow?.description"
            :text="attachViewRow.description"
            class="ml-2 mr-4 min-w-0 flex-1 text-sm font-normal text-gray-400"
          />
        </div>
      </template>

      <div v-if="attachViewRow" class="min-h-[120px] pt-1">
        <!-- 上传中进度 -->
        <div
          v-for="f in getRowUploadFiles(attachViewRow).filter(
            (fi) => fi.status === 'uploading',
          )"
          :key="f.uid"
          class="mb-2 flex items-center gap-2 rounded bg-blue-50 px-2 py-1.5"
        >
          <span
            class="icon-[ant-design--loading-outlined] flex-shrink-0 animate-spin text-sm text-blue-400"
          />
          <span class="flex-1 truncate text-sm text-gray-700" :title="f.name">{{
            f.name
          }}</span>
          <template v-if="f.percent !== undefined && f.percent < 100">
            <Progress
              :percent="f.percent"
              :stroke-width="3"
              style="width: 80px"
              status="active"
            />
          </template>
          <span v-else class="flex-shrink-0 text-xs text-gray-400">{{
            f.percent === 100 ? '处理中' : '等待中'
          }}</span>
        </div>

        <!-- 失败文件 -->
        <div
          v-for="f in getRowUploadFiles(attachViewRow).filter(
            (fi) => fi.status === 'error',
          )"
          :key="f.uid"
          class="mb-2 flex items-center gap-2 rounded border border-red-100 bg-red-50 px-2 py-1.5"
        >
          <span
            class="icon-[ant-design--warning-outlined] flex-shrink-0 text-sm text-red-400"
          />
          <span class="flex-1 truncate text-sm text-red-600"
            >{{ f.name }} - 上传失败</span
          >
          <button
            type="button"
            class="rounded text-xs text-blue-500 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            @click="retryAttachViewFile(f)"
          >
            重试
          </button>
          <button
            type="button"
            class="ml-1 rounded text-xs text-red-400 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            @click.stop="removeAttachViewErrorFile(f)"
          >
            删除
          </button>
        </div>

        <!-- 附件卡片网格 -->
        <div
          v-if="
            getRowUploadFiles(attachViewRow).filter((f) => f.status === 'done')
              .length
          "
          class="grid max-h-[77vh] grid-cols-1 gap-3 overflow-y-auto sm:grid-cols-2 lg:grid-cols-4"
        >
          <div
            v-for="f in getRowUploadFiles(attachViewRow).filter(
              (fi) => fi.status === 'done',
            )"
            :key="f.uid"
            class="overflow-hidden rounded-lg border border-gray-100 bg-white"
          >
            <!-- 缩略图区 -->
            <div
              class="group relative flex h-[110px] items-center justify-center overflow-hidden"
              :role="
                isAttachmentZip(toAttachmentItem(f)) ? undefined : 'button'
              "
              :tabindex="isAttachmentZip(toAttachmentItem(f)) ? -1 : 0"
              :aria-label="
                isAttachmentZip(toAttachmentItem(f))
                  ? undefined
                  : `预览附件 ${f.name}`
              "
              :class="[
                !uploadItemImg(f)
                  ? toAttachmentItem(f)?.content_type?.startsWith('video')
                    ? 'bg-gray-700'
                    : isAttachmentZip(toAttachmentItem(f))
                      ? 'bg-yellow-50'
                      : 'bg-blue-50'
                  : 'bg-gray-100',
                isAttachmentZip(toAttachmentItem(f))
                  ? 'cursor-default'
                  : 'cursor-pointer',
              ]"
              @click="
                isAttachmentZip(toAttachmentItem(f))
                  ? undefined
                  : previewUploadItem(f)
              "
              @keydown.enter="
                isAttachmentZip(toAttachmentItem(f))
                  ? undefined
                  : previewUploadItem(f)
              "
              @keydown.space.prevent="
                isAttachmentZip(toAttachmentItem(f))
                  ? undefined
                  : previewUploadItem(f)
              "
            >
              <img
                v-if="uploadItemImg(f)"
                :src="`data:image/png;base64,${uploadItemImg(f)}`"
                :alt="f.name"
                class="pointer-events-none absolute inset-0 h-full w-full object-contain"
              />
              <template v-else>
                <span
                  class="text-2xl font-bold"
                  :class="
                    toAttachmentItem(f)?.content_type?.startsWith('video')
                      ? 'text-white'
                      : isAttachmentZip(toAttachmentItem(f))
                        ? 'text-yellow-500'
                        : 'text-blue-400'
                  "
                >
                  {{
                    toAttachmentItem(f)?.content_type?.startsWith('video')
                      ? 'MP4'
                      : isAttachmentZip(toAttachmentItem(f))
                        ? 'ZIP'
                        : (toAttachmentItem(f)?.filetype ?? '?')
                            .slice(0, 3)
                            .toUpperCase()
                  }}
                </span>
              </template>
              <!-- 悬浮操作 -->
              <div
                class="absolute inset-0 flex items-center justify-center gap-5 bg-black/40 opacity-100 transition-opacity sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100"
              >
                <button
                  v-if="!isAttachmentZip(toAttachmentItem(f))"
                  type="button"
                  class="flex flex-col items-center rounded text-white transition-colors hover:text-blue-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                  @click.stop="previewUploadItem(f)"
                >
                  <span class="icon-[ant-design--eye-outlined] text-xl" />
                  <span class="mt-0.5 text-xs">预览</span>
                </button>
                <button
                  v-if="toAttachmentItem(f)?.url"
                  type="button"
                  class="flex flex-col items-center rounded text-white transition-colors hover:text-blue-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                  @click.stop="downloadUploadItem(f)"
                >
                  <span class="icon-[ant-design--download-outlined] text-xl" />
                  <span class="mt-0.5 text-xs">下载</span>
                </button>
                <Popconfirm
                  v-if="!readonlyMode"
                  title="确认删除此附件？"
                  ok-text="删除"
                  ok-type="danger"
                  cancel-text="取消"
                  @confirm.stop="removeAttachViewItem(f)"
                >
                  <button
                    type="button"
                    class="flex flex-col items-center rounded text-white transition-colors hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                    @click.stop
                  >
                    <span class="icon-[ant-design--delete-outlined] text-xl" />
                    <span class="mt-0.5 text-xs">删除</span>
                  </button>
                </Popconfirm>
              </div>
            </div>
            <!-- 文件信息 -->
            <div class="px-2 py-1.5">
              <p class="truncate text-xs text-gray-700" :title="f.name">
                {{ f.name }}
              </p>
              <p
                v-if="toAttachmentItem(f)?.size"
                class="mt-0.5 text-xs text-gray-400"
              >
                {{ formatSize(toAttachmentItem(f)?.size ?? 0) }}
              </p>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div
          v-if="!getRowUploadFiles(attachViewRow).length"
          class="flex flex-col items-center justify-center py-12 text-gray-300"
        >
          <span class="icon-[ant-design--file-outlined] mb-2 text-2xl" />
          <span class="text-sm">暂无附件</span>
        </div>
      </div>
    </Modal>

    <RequirementTemplateModal
      v-model:open="templatePickerOpen"
      :can-manage="canManageRequirementTemplates"
      @apply="applyRequirementTemplate"
    />

    <!-- 需求附件上传弹窗 -->
    <UploadMaterialModal
      ref="uploadModalRef"
      :open="rowUploadVisible"
      :demand-type="''"
      :persist-key="rowUploadKey"
      :is-unzip="false"
      :max-files="5"
      title="上传需求附件"
      @update:open="handleRowUploadModalClose"
      @upload-change="handleUploadChange"
      @all-done="(key) => handleRowUploadAllDone(key)"
    />

    <!-- 预览弹窗 -->
    <MediaPreview
      :open="previewVisible"
      :url="previewFile?.url"
      :filetype="previewFile?.type"
      :z-index="2100"
      @update:open="
        (v) => {
          if (!v) closePreview();
        }
      "
    />
  </div>
</template>

<style scoped>
/* 原型中的按钮蓝色独立于全局主题，避免主题切换改变选中态与操作色。 */
.material-task-form {
  --material-form-accent: 225 100% 60%;
  --material-template-surface: #edf3ff;
}

/* 新建任务的局部控件样式，保留公共按钮和单选组的业务行为。 */
.green-material-option:focus-visible {
  /* 全局焦点规则使用 important；这里保持原型蓝色并保留键盘焦点提示。 */
  outline: 2px solid hsl(var(--material-form-accent) / 45%) !important;
  outline-offset: 2px;
}

.green-material-options {
  display: flex;
  gap: var(--adpulse-action-gap);
  padding-top: 4px;
}

.green-material-option {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  justify-content: center;
  height: 30px;
  min-height: 30px;
  padding: 0 12px;
  font-size: 14px;
  font-weight: 400;
  line-height: 20px;
  color: var(--adpulse-text);
  white-space: nowrap;
  cursor: pointer;
  background: var(--adpulse-surface);
  border: 1px solid #cbd5e1;
  border-radius: 3px;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease,
    color 0.15s ease;
}

.green-material-option:hover:not(:disabled) {
  color: hsl(var(--material-form-accent));
  background: hsl(var(--material-form-accent) / 6%);
  border-color: hsl(var(--material-form-accent) / 60%);
}

.green-material-option.is-selected {
  color: hsl(var(--material-form-accent));
  background: hsl(var(--material-form-accent) / 9%);
  border-color: hsl(var(--material-form-accent));
}

.green-material-option:disabled {
  color: var(--adpulse-text-muted);
  cursor: not-allowed;
  background: var(--adpulse-surface-muted);
  opacity: 0.7;
}

.green-material-option:disabled.is-selected {
  color: hsl(var(--material-form-accent));
  background: hsl(var(--material-form-accent) / 9%);
}
</style>

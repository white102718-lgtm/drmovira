<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Form,
  FormItem,
  Input,
  Progress,
  Row,
  Select,
  Statistic,
  Table,
  Tag,
  message,
} from 'ant-design-vue';

import { useProjectContextStore } from '#/store';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';

interface ProductProfile {
  audience: string;
  categoryCount: number;
  completeness: number;
  id: string;
  imageCount: number;
  positioning: string;
  prohibitedClaims: string;
  productId: string;
  productName: string;
  projectId: string;
  projectName: string;
  sellingPoints: string;
  status: 'complete' | 'draft' | 'review';
  updatedAt: string;
  videoCount: number;
}

const router = useRouter();
const projectStore = useProjectContextStore();
const keyword = ref('');
const statusFilter = ref<ProductProfile['status'] | 'all'>('all');
const currentPage = ref(1);
const pageSize = ref(10);
const drawerOpen = ref(false);
const editingId = ref('');

const profiles = ref<ProductProfile[]>([
  {
    audience: '18–34 岁欧美中重度策略游戏玩家',
    categoryCount: 12,
    completeness: 92,
    id: 'profile-starfall',
    imageCount: 38,
    positioning: '快节奏太空策略与联盟战争',
    prohibitedClaims: '禁止承诺固定收益；禁止使用未授权影视角色。',
    productId: 'product-project-starfall',
    productName: 'Starfall',
    projectId: 'project-starfall',
    projectName: 'Starfall 全球增长',
    sellingPoints: '即时战斗反馈、联盟协作、低门槛首日成长、跨服赛季',
    status: 'complete',
    updatedAt: '2026-08-07 10:42',
    videoCount: 21,
  },
  {
    audience: '美国 25–44 岁末日题材与生存建造玩家',
    categoryCount: 8,
    completeness: 76,
    id: 'profile-ark',
    imageCount: 19,
    positioning: '末日生存与基地经营',
    prohibitedClaims: '不使用真实灾难画面，不出现血腥特写。',
    productId: 'product-project-ark',
    productName: 'Project Ark',
    projectId: 'project-ark',
    projectName: 'Project Ark 美国市场',
    sellingPoints: '基地建设、资源取舍、英雄收集、联盟生存',
    status: 'review',
    updatedAt: '2026-08-06 18:20',
    videoCount: 13,
  },
  {
    audience: '日本 18–30 岁像素 RPG 与轻度收集玩家',
    categoryCount: 5,
    completeness: 44,
    id: 'profile-pixel',
    imageCount: 10,
    positioning: '怀旧像素冒险与轻量收集',
    prohibitedClaims: '避免使用未经本地化审核的俚语和绝对化用语。',
    productId: 'product-project-pixel',
    productName: 'Pixel Quest',
    projectId: 'project-pixel',
    projectName: 'Pixel Quest 日本首发',
    sellingPoints: '像素画风、轻量战斗、角色收集、短时任务',
    status: 'draft',
    updatedAt: '2026-08-05 09:10',
    videoCount: 4,
  },
]);

const { commitQueryState, restoreFromRoute } = useListRouteState({
  onRouteStateRestored: () => {
    // 客户端列表无需重新请求，恢复 ref 后过滤结果会自动更新。
  },
  pagination: {
    defaultPageSize: 10,
    page: currentPage,
    pageSize,
    pageSizes: [10, 20, 50],
  },
  state: createListRouteStateTarget({
    keyword,
    status: statusFilter,
  }),
});

async function handleListStateChange(pagination: {
  current?: number;
  pageSize?: number;
}) {
  const sizeChanged =
    pagination.pageSize !== undefined && pagination.pageSize !== pageSize.value;
  pageSize.value = pagination.pageSize ?? pageSize.value;
  currentPage.value = sizeChanged ? 1 : (pagination.current ?? 1);
  await commitQueryState();
}

async function handleFilterChange() {
  currentPage.value = 1;
  await commitQueryState();
}

const formState = reactive({
  audience: '',
  positioning: '',
  prohibitedClaims: '',
  productId: '',
  productName: '',
  projectId: '',
  projectName: '',
  sellingPoints: '',
  status: 'draft' as ProductProfile['status'],
});

const statusMeta = {
  complete: { color: 'green', label: '可用于生产' },
  draft: { color: 'default', label: '草稿' },
  review: { color: 'orange', label: '待审核' },
};

const selectedMasterProject = computed(() =>
  projectStore.projectOptions.find((item) => item.id === formState.projectId),
);

const productOptions = computed(() =>
  selectedMasterProject.value
    ? [
        {
          label: selectedMasterProject.value.productName,
          value: `product-${selectedMasterProject.value.id}`,
        },
      ]
    : [],
);

const filteredProfiles = computed(() => {
  const search = keyword.value.trim().toLowerCase();
  return profiles.value.filter((item) => {
    const matchesKeyword =
      !search ||
      `${item.productName}${item.projectName}${item.positioning}`
        .toLowerCase()
        .includes(search);
    const matchesStatus =
      statusFilter.value === 'all' || item.status === statusFilter.value;
    return matchesKeyword && matchesStatus;
  });
});

const stats = computed(() => [
  { label: '产品档案', value: profiles.value.length },
  {
    label: '可用于生产',
    value: profiles.value.filter((item) => item.status === 'complete').length,
  },
  {
    label: '参考图片',
    value: profiles.value.reduce((sum, item) => sum + item.imageCount, 0),
  },
  {
    label: '参考视频',
    value: profiles.value.reduce((sum, item) => sum + item.videoCount, 0),
  },
]);

const columns: TableColumnsType<ProductProfile> = [
  { key: 'product', title: '产品与项目', width: 260 },
  { dataIndex: 'positioning', key: 'positioning', title: '产品定位' },
  { key: 'assets', title: '知识内容', width: 180 },
  { key: 'completeness', title: '完整度', width: 180 },
  { dataIndex: 'status', key: 'status', title: '状态', width: 130 },
  { dataIndex: 'updatedAt', key: 'updatedAt', title: '更新时间', width: 170 },
  { key: 'actions', title: '操作', width: 190, fixed: 'right' },
];

function resetForm() {
  Object.assign(formState, {
    audience: '',
    positioning: '',
    prohibitedClaims: '',
    productId: '',
    productName: '',
    projectId: '',
    projectName: '',
    sellingPoints: '',
    status: 'draft',
  });
}

function createProfile() {
  editingId.value = '';
  resetForm();
  const project = projectStore.currentProject ?? projectStore.projectOptions[0];
  if (project) selectMasterProject(project.id);
  drawerOpen.value = true;
}

function selectMasterProject(projectId: string) {
  const project = projectStore.projectOptions.find(
    (item) => item.id === projectId,
  );
  formState.projectId = projectId;
  formState.projectName = project?.name ?? '';
  formState.productId = project ? `product-${project.id}` : '';
  formState.productName = project?.productName ?? '';
}

function editProfile(profile: ProductProfile | Record<string, any>) {
  const current = profile as ProductProfile;
  editingId.value = current.id;
  Object.assign(formState, {
    audience: current.audience,
    positioning: current.positioning,
    prohibitedClaims: current.prohibitedClaims,
    productId: current.productId,
    productName: current.productName,
    projectId: current.projectId,
    projectName: current.projectName,
    sellingPoints: current.sellingPoints,
    status: current.status,
  });
  drawerOpen.value = true;
}

function saveProfile() {
  if (!formState.productId || !formState.projectId) {
    message.warning('请选择正式产品和所属项目');
    return;
  }
  if (!formState.positioning.trim() || !formState.sellingPoints.trim()) {
    message.warning('请完善产品定位和核心卖点');
    return;
  }

  const now = new Date().toLocaleString('zh-CN', { hour12: false });
  const existing = profiles.value.find((item) => item.id === editingId.value);
  if (existing) {
    Object.assign(existing, formState, {
      completeness: Math.max(existing.completeness, 80),
      updatedAt: now,
    });
  } else {
    profiles.value = [
      {
        ...formState,
        categoryCount: 0,
        completeness: 52,
        id: `profile-${Date.now()}`,
        imageCount: 0,
        updatedAt: now,
        videoCount: 0,
      },
      ...profiles.value,
    ];
  }
  drawerOpen.value = false;
  message.success('产品创意知识库已保存');
}

function startCreative(profile: ProductProfile | Record<string, any>) {
  const current = profile as ProductProfile;
  router.push({
    path: '/fusion/ai-studio',
    query: { capability: 'creative-batch', product: current.id },
  });
}

onMounted(async () => {
  await restoreFromRoute();
  await projectStore.loadProjectOptions();
});
</script>

<template>
  <Page class="bg-slate-50" content-class="pb-6">
    <div class="flex w-full min-w-0 flex-col gap-4">
      <section
        class="flex flex-col justify-between gap-4 lg:flex-row lg:items-end"
      >
        <div>
          <h1 class="m-0 text-2xl font-semibold text-slate-950">
            产品与创意知识库
          </h1>
          <p class="mb-0 mt-2 text-sm leading-6 text-slate-600">
            Java Product 是正式产品主数据；这里维护 AdGen
            生产所需的卖点、受众、禁用信息和参考素材。
          </p>
        </div>
        <Button class="" type="primary" @click="createProfile">
          <span class="flex items-center gap-2">
            <IconifyIcon icon="lucide:plus" />新建创意档案
          </span>
        </Button>
      </section>

      <Alert
        message="数据边界：客户、项目和正式产品由 Java 维护；AdGen 只保存通过 product_id 关联的 CreativeProfile，不再创建第二套 Product 主数据。"
        type="info"
        show-icon
      />

      <Row :gutter="[12, 12]">
        <Col v-for="item in stats" :key="item.label" :xs="12" :lg="6">
          <Card class="border-slate-200" :body-style="{ padding: '14px 16px' }">
            <Statistic :title="item.label" :value="item.value" />
          </Card>
        </Col>
      </Row>

      <Card class="border-slate-200" :body-style="{ padding: 0 }">
        <div
          class="flex flex-col gap-3 border-b border-slate-200 p-4 md:flex-row"
        >
          <Input.Search
            v-model:value="keyword"
            allow-clear
            class="md:max-w-md"
            placeholder="搜索产品、项目或产品定位"
            @update:value="handleFilterChange"
          />
          <Select
            v-model:value="statusFilter"
            class="w-full md:w-44"
            :options="[
              { label: '全部状态', value: 'all' },
              ...Object.entries(statusMeta).map(([value, item]) => ({
                label: item.label,
                value,
              })),
            ]"
            @change="handleFilterChange"
          />
        </div>
        <Table
          :columns="columns"
          :data-source="filteredProfiles"
          :pagination="{
            current: currentPage,
            pageSize,
            showSizeChanger: true,
          }"
          :row-key="(row: ProductProfile) => row.id"
          :scroll="{ x: 1280 }"
          @change="handleListStateChange"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'product'">
              <div class="font-medium text-slate-900">
                {{ record.productName }}
              </div>
              <div class="mt-1 text-xs text-slate-500">
                {{ record.projectName }}
              </div>
            </template>
            <template v-else-if="column.key === 'assets'">
              <div class="text-sm text-slate-700">
                {{ record.categoryCount }} 类内容
              </div>
              <div class="mt-1 text-xs text-slate-500">
                {{ record.imageCount }} 图 · {{ record.videoCount }} 视频
              </div>
            </template>
            <template v-else-if="column.key === 'completeness'">
              <Progress :percent="record.completeness" />
            </template>
            <template v-else-if="column.key === 'status'">
              <Tag
                :color="
                  statusMeta[record.status as ProductProfile['status']].color
                "
              >
                {{
                  statusMeta[record.status as ProductProfile['status']].label
                }}
              </Tag>
            </template>
            <template v-else-if="column.key === 'actions'">
              <Button type="link" @click="editProfile(record)">编辑</Button>
              <Button type="link" @click="startCreative(record)"
                >开始创作</Button
              >
            </template>
          </template>
        </Table>
      </Card>
    </div>

    <Drawer
      v-model:open="drawerOpen"
      :title="editingId ? '编辑产品创意档案' : '新建产品创意档案'"
      width="min(560px, 100vw)"
    >
      <Alert
        class="mb-5"
        message="正式环境中产品与项目字段从 Java 主数据选择，不允许在此自由创建。"
        type="warning"
        show-icon
      />
      <Form layout="vertical">
        <Row :gutter="16">
          <Col :xs="24" :md="12">
            <FormItem label="所属项目" required>
              <Select
                v-model:value="formState.projectId"
                :options="
                  projectStore.projectOptions.map((item) => ({
                    label: `${item.customerName} / ${item.name}`,
                    value: item.id,
                  }))
                "
                placeholder="选择 Java Project"
                show-search
                option-filter-prop="label"
                @change="(value) => selectMasterProject(String(value))"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="正式产品" required>
              <Select
                v-model:value="formState.productId"
                :options="productOptions"
                :disabled="!formState.projectId"
                placeholder="先选择所属项目"
              />
            </FormItem>
          </Col>
        </Row>
        <FormItem label="产品定位" required>
          <Input.TextArea
            v-model:value.trim="formState.positioning"
            :rows="3"
            placeholder="说明产品类型、核心体验和差异化定位"
          />
        </FormItem>
        <FormItem label="目标受众">
          <Input.TextArea
            v-model:value.trim="formState.audience"
            :rows="3"
            placeholder="地区、年龄、兴趣、使用场景与购买动机"
          />
        </FormItem>
        <FormItem label="核心卖点" required>
          <Input.TextArea
            v-model:value.trim="formState.sellingPoints"
            :rows="4"
            placeholder="每行一个可用于创意生产的核心卖点"
          />
        </FormItem>
        <FormItem label="禁用信息与合规边界">
          <Input.TextArea
            v-model:value.trim="formState.prohibitedClaims"
            :rows="4"
            placeholder="禁用词、不可使用的品牌或人物、平台合规要求"
          />
        </FormItem>
        <FormItem label="档案状态">
          <Select
            v-model:value="formState.status"
            :options="
              Object.entries(statusMeta).map(([value, item]) => ({
                label: item.label,
                value,
              }))
            "
          />
        </FormItem>
      </Form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <Button class="" @click="drawerOpen = false">取消</Button>
          <Button class="" type="primary" @click="saveProfile">
            保存档案
          </Button>
        </div>
      </template>
    </Drawer>
  </Page>
</template>

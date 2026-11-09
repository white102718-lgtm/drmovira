<script setup lang="ts">
import type { TableColumnsType } from 'ant-design-vue';
import type { Key } from 'ant-design-vue/es/table/interface';

import { computed, h, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';

import { CircleHelp } from '@vben/icons';

import {
  Button,
  Card,
  Modal,
  Pagination,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'ant-design-vue';
import dayjs from 'dayjs';
import isoWeek from 'dayjs/plugin/isoWeek';
import isToday from 'dayjs/plugin/isToday';

import { getDashboardDetail } from '#/api/dashboard';
import DateRangePicker from '#/views/components/DateRangePicker.vue';

dayjs.extend(isoWeek);
dayjs.extend(isToday);

// Naive UI使用时间戳 [开始时间戳, 结束时间戳]
const dateRange = ref<[number, number]>([
  dayjs(dayjs.tz().format('YYYY-MM-DD')).valueOf(),
  dayjs(dayjs.tz().format('YYYY-MM-DD')).endOf('day').valueOf(),
]);

// Naive UI DatePicker的值变化回调（用于shortcuts和确认）
const handleDateUpdate = async (value: [number, number] | null) => {
  if (!value) return;
  // shortcuts选择会立即触发update，需要等待下一个tick确保dateRange已更新
  await updateDateParams();
  await fetchDashboardData();
};

interface DataItem {
  [key: string]: any;
  id: string;
  name: string;
}

interface TabInfo {
  select_ids: string[];
  title: string;
}

interface TabList {
  account_id: TabInfo;
  agent_line: TabInfo;
  game_platform: TabInfo;
  placer_id: TabInfo;
}

const tabList = ref<TabList>({
  game_platform: { select_ids: [], title: '项目名称' },
  agent_line: { select_ids: [], title: '代理线' },
  account_id: { select_ids: [], title: '账户' },
  placer_id: { select_ids: [], title: '投手' },
});

type TabKey = keyof TabList;
const activeTab = ref<TabKey>('game_platform');
const tabOrder = ref<TabKey[]>([
  'game_platform',
  'agent_line',
  'placer_id',
  'account_id',
]);
const loading = ref(false);
const tableHeight = ref(600);
const isInitializing = ref(false);

// 分页相关状态
const currentPage = ref(1);
const pageSize = ref(100);
const total = ref(0);
const totalPages = ref(0);

// 排序相关状态
const sortRules = ref<Array<{ field: string; order: 'asc' | 'desc' }>>([
  { field: '花费金额', order: 'desc' },
]);
const showSortManager = ref(false);

const tabKeys = computed<TabKey[]>(() => {
  return tabOrder.value;
});

const data = ref<DataItem[]>([]);

const baseColumns = ref<TableColumnsType>([]);

// 获取可排序的列
const sortableColumns = computed(() => {
  return baseColumns.value
    .filter((col) => col.dataIndex && col.dataIndex !== 'action')
    .map((col) => ({
      key: col.dataIndex as string,
      label: col.title as string,
    }));
});

// 多列排序函数
const multiSort = (
  data: DataItem[],
  rules: Array<{ field: string; order: 'asc' | 'desc' }>,
) => {
  // 过滤掉无效的排序规则
  const validRules = rules.filter((rule) => rule.field && rule.order);
  if (validRules.length === 0) return data;

  return [...data].sort((a, b) => {
    for (const rule of validRules) {
      const aVal = a[rule.field];
      const bVal = b[rule.field];

      let result = 0;
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        result = aVal.localeCompare(bVal, 'zh-CN', { numeric: true });
      } else if (typeof aVal === 'number' && typeof bVal === 'number') {
        result = aVal - bVal;
      } else {
        const aStr = String(aVal || '');
        const bStr = String(bVal || '');
        result = aStr.localeCompare(bStr, 'zh-CN', { numeric: true });
      }

      if (result !== 0) {
        return rule.order === 'desc' ? -result : result;
      }
    }
    return 0;
  });
};

// 计算显示的数据
const displayData = computed(() => {
  const validRules = sortRules.value.filter((rule) => rule.field && rule.order);
  if (validRules.length > 0) {
    return multiSort(data.value, sortRules.value);
  }
  return data.value;
});

// 添加排序规则
const addSortRule = () => {
  sortRules.value.push({ field: '', order: 'desc' });
};

// 删除排序规则
const removeSortRule = (index: number) => {
  sortRules.value.splice(index, 1);
};

// 清空排序
const clearSort = () => {
  sortRules.value = [];
  showSortManager.value = false;
};

// TODO 将url存入localstorage, 不然每次都要重新选择
const replaceUrl = (query: Record<string, any>) => {
  const queryString = Object.entries(query)
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join('&');
  const currentPath = window.location.href.split('?')[0];
  const url = `${currentPath}${queryString ? `?${queryString}` : ''}`;
  window.history.replaceState({ ...history.state }, '', url);
};

const getUrlParams = () => {
  const searchParams = new URLSearchParams(window.location.search);
  const params: Record<string, any> = {};

  for (const [key, value] of searchParams.entries()) {
    params[key] = value;
  }

  return params;
};

const updateDateParams = async () => {
  const query = getUrlParams();
  delete query.date;
  if (dateRange.value && dateRange.value.length === 2) {
    const startDate = dayjs(dateRange.value[0]).format('YYYY-MM-DD');
    const endDate = dayjs(dateRange.value[1]).format('YYYY-MM-DD');
    query.date = `${startDate},${endDate}`;
  }
  replaceUrl(query);
};

const restoreDateParams = async () => {
  const query = getUrlParams();
  const dateParam = query.date;
  if (dateParam) {
    if (dateParam.includes(',')) {
      const [startDate, endDate] = dateParam.split(',');
      if (startDate && endDate) {
        dateRange.value = [
          dayjs(startDate).valueOf(),
          dayjs(endDate).valueOf(),
        ];
      }
    }
  } else {
    await updateDateParams();
  }
};

const updateSelectedIdsParams = async (tabKey: TabKey) => {
  const query = getUrlParams();
  const select_ids = tabList.value[tabKey].select_ids;
  if (select_ids.length > 0) {
    query[tabKey] = select_ids.map(String).join(',');
  } else if (query[tabKey]) {
    delete query[tabKey];
  }
  replaceUrl(query);
};

const restoreSelectedIds = async () => {
  const query = getUrlParams();

  Object.entries(query).forEach(([key, value]) => {
    if (key === 'tab') return;
    if (tabKeys.value.includes(key as TabKey)) {
      const ids = value.split(',');
      tabList.value[key as TabKey].select_ids = ids.filter((id: string) =>
        data.value.some((item: DataItem) => item.id === id),
      );
    }
  });
};

const restoreActiveTab = async () => {
  const query = getUrlParams();
  if (query.tab) {
    activeTab.value = query.tab as TabKey;
  } else {
    query.tab = activeTab.value;
    replaceUrl(query);
  }
};

const restoreParams = async () => {
  await restoreDateParams();
  await restoreSelectedIds();
  await restoreActiveTab();
};

const rowSelection = {
  onChange: async (selectedRowKeys: Key[]) => {
    tabList.value[activeTab.value].select_ids = selectedRowKeys.map((key) =>
      key.toString(),
    );
    await updateSelectedIdsParams(activeTab.value);
  },
  get selectedRowKeys() {
    return tabList.value[activeTab.value].select_ids;
  },
};

const handleTabChange = async (key: number | string) => {
  const newKey = key.toString() as TabKey;
  if (tabKeys.value.includes(newKey)) {
    isInitializing.value = true;
    activeTab.value = newKey;
    currentPage.value = 1;
    await fetchDashboardData();
    isInitializing.value = false;
  }
};

const handlePageSizeChange = (current: number, size: number) => {
  currentPage.value = 1;
  pageSize.value = size;
};

const handleTagClose = async (key: TabKey) => {
  if (tabList.value[key]) {
    tabList.value[key].select_ids = [];
    await updateSelectedIdsParams(key);
    if (activeTab.value !== key) {
      await fetchDashboardData();
    }
  }
};

const handleResizeColumn = (w: number, col: any) => {
  col.width = w;
};

const fetchDashboardData = async () => {
  try {
    loading.value = true;
    data.value = [];
    const urlParams = getUrlParams();
    const params: Record<string, string> = {};
    Object.entries(urlParams).forEach(([key, value]) => {
      params[key] = value;
      if (tabKeys.value.includes(key as TabKey)) {
        tabList.value[key as TabKey].select_ids = value.split(',');
      }
    });
    // 添加分页参数
    params.page = currentPage.value.toString();
    params.page_size = pageSize.value.toString();

    const response = await getDashboardDetail(activeTab.value, params);
    const { data: items, pagination } = response;
    data.value = items.map((item: DataItem) => {
      return {
        ...item,
        key: `${item.id}`,
      };
    });

    if (pagination) {
      total.value = pagination.total;
      totalPages.value = pagination.total_pages;
    }

    baseColumns.value = response.columns.map((column: string) => {
      switch (column) {
        case 'name': {
          return {
            dataIndex: column,
            fixed: 'left',
            resizable: true,
            title: '名称',
            width: 200,
          };
        }
        case 'status': {
          return {
            dataIndex: column,
            title: '状态',
            customRender: ({ text }: { text: string }) =>
              h(Tag, { color: text === '0' ? 'green' : 'gray' }, () =>
                text === '0' ? '投放中' : '已暂停',
              ),
          };
        }
        case '花费金额': {
          return {
            dataIndex: column,
            title: '花费金额',
            width: 140,
            fixed: 'left',
          };
        }
        default: {
          return {
            dataIndex: column,
            title: column,
            width: 140,
          };
        }
      }
    });
  } catch {
    data.value = [];
  } finally {
    loading.value = false;
  }
};

const handleLinkClick = async (record: Record<string, any>) => {
  const after_tabs = tabKeys.value.slice(
    tabKeys.value.indexOf(activeTab.value),
  );
  if (after_tabs.length <= 1) {
    return;
  }

  for (const tab of after_tabs) {
    tabList.value[tab].select_ids = tab === activeTab.value ? [record.id] : [];
    await updateSelectedIdsParams(tab);
  }

  activeTab.value = after_tabs[1] as TabKey;
  await fetchDashboardData();
};

const calculateTableHeight = () => {
  const windowHeight = window.innerHeight;
  const fixedHeight = 235;
  tableHeight.value = windowHeight - fixedHeight;
};

const handleResize = () => {
  calculateTableHeight();
};

onMounted(async () => {
  isInitializing.value = true;
  await restoreParams();
  await fetchDashboardData();
  isInitializing.value = false;

  await nextTick();
  calculateTableHeight();

  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
});

watch(
  () => activeTab.value,
  (newTab) => {
    const updateUrl = async () => {
      const query = getUrlParams();
      query.tab = newTab;
      replaceUrl(query);
    };
    updateUrl();
  },
);

watch([() => currentPage.value, () => pageSize.value], () => {
  if (isInitializing.value) return;
  fetchDashboardData();
});
</script>

<template>
  <Card class="h-full" :body-style="{ padding: '4px 8px 8px 8px' }">
    <Tabs v-model:active-key="activeTab" @change="handleTabChange" type="card">
      <Tabs.TabPane v-for="key in tabKeys" :key="key" :disabled="loading">
        <template #tab>
          <div style="width: 150px; overflow: hidden">
            <span style="float: left">{{ tabList[key].title }}</span>
            <Tag
              v-if="tabList[key].select_ids.length > 0"
              color="blue"
              closable
              @close="handleTagClose(key)"
              style="float: right"
            >
              选中{{ tabList[key].select_ids.length }}项
            </Tag>
          </div>
        </template>
        <Table
          :columns="baseColumns"
          :data-source="displayData"
          :row-selection="rowSelection"
          :pagination="false"
          :loading="loading"
          @resize-column="handleResizeColumn"
          :scroll="{ y: tableHeight }"
          bordered
        >
          <template #bodyCell="{ column, text, record }">
            <template v-if="column.dataIndex === 'name'">
              <Typography.Link @click="handleLinkClick(record)">
                {{ text || 'null' }}
              </Typography.Link>
            </template>
          </template>
        </Table>

        <!-- 分页器 -->
        <div class="mt-[6px] flex justify-end">
          <Pagination
            :current="currentPage"
            :page-size="pageSize"
            :total="total"
            :show-size-changer="true"
            :show-quick-jumper="true"
            :show-total="(total) => `共 ${total} 条`"
            :page-size-options="['50', '100', '200']"
            @change="(page) => (currentPage = page)"
            @show-size-change="handlePageSizeChange"
          />
        </div>
      </Tabs.TabPane>

      <template #rightExtra>
        <div class="flex items-center gap-1">
          <Button @click="showSortManager = true"> 排序 </Button>
          <Tooltip>
            <template #title>
              <div>日期选择的是广告账户时区</div>
            </template>
            <CircleHelp class="h-4 w-4 cursor-pointer text-gray-400" />
          </Tooltip>
          <DateRangePicker
            v-model:value="dateRange"
            type="daterange"
            width="250px"
            format="yyyy-MM-dd"
            @update:value="handleDateUpdate"
          />
        </div>
      </template>
    </Tabs>

    <!-- 排序管理器弹窗 -->
    <Modal
      v-model:open="showSortManager"
      title="自定义排序"
      :width="600"
      :footer="null"
    >
      <div class="sort-manager">
        <div
          v-for="(rule, index) in sortRules"
          :key="index"
          class="sort-rule mb-3"
        >
          <Space>
            <span class="text-sm text-gray-600">第{{ index + 1 }}级：</span>
            <Select
              v-model:value="rule.field"
              placeholder="选择列"
              style="width: 150px"
            >
              <Select.Option
                v-for="col in sortableColumns"
                :key="col.key"
                :value="col.key"
              >
                {{ col.label }}
              </Select.Option>
            </Select>
            <Select
              v-model:value="rule.order"
              placeholder="排序方向"
              style="width: 100px"
            >
              <Select.Option value="asc">升序</Select.Option>
              <Select.Option value="desc">降序</Select.Option>
            </Select>
            <Button @click="removeSortRule(index)" type="text" danger>
              删除
            </Button>
          </Space>
        </div>
        <div class="mt-4">
          <Space>
            <Button @click="addSortRule" type="dashed"> + 添加排序规则 </Button>
            <Button @click="clearSort" type="text" v-if="sortRules.length > 0">
              清空所有排序
            </Button>
          </Space>
        </div>
      </div>
    </Modal>
  </Card>
</template>

<style scoped>
/* tab后的选中项的位置 */

/* 表格的padding */
</style>

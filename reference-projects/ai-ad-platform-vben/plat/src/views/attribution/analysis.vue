<script setup lang="ts">
import type { UploadProps } from 'ant-design-vue';

import { computed, markRaw, onMounted, reactive, ref, watch } from 'vue';

import {
  Button,
  Card,
  Col,
  DatePicker,
  InputNumber,
  message,
  Radio,
  Row,
  Select,
  Upload,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { useVbenForm } from '#/adapter/form';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  getAllAttribution,
  uploadAttributionData,
} from '#/api/attribution/all';

interface AttributionData {
  created_at: string;
  default?: any;
  id: string;
  mode?: string;
  name: string;
  options: string[];
  title: string;
  updated_at: string;
}

const [BaseForm, baseFormApi] = useVbenForm({
  commonConfig: {
    colon: true,
    componentProps: {
      class: 'w-full',
    },
  },
  layout: 'horizontal',
  schema: [],
  wrapperClass: 'grid-cols-5',
});
baseFormApi.setState({ showDefaultActions: false });

const [fixFieldForm, fixFieldFormApi] = useVbenForm({
  commonConfig: {
    colon: true,
    componentProps: {
      class: 'w-full',
    },
    labelWidth: 130,
  },
  layout: 'horizontal',
  schema: [
    {
      component: 'InputNumber',
      componentProps: {
        controls: false,
        placeholder: '请输入',
      },
      fieldName: 'first_day_reg',
      label: '首日注册',
      rules: 'required',
    },
    {
      component: 'InputNumber',
      componentProps: {
        controls: false,
        placeholder: '请输入',
      },
      fieldName: 'first_day_new',
      label: '首日新增',
      rules: 'required',
    },
    {
      component: 'InputNumber',
      componentProps: {
        controls: false,
        placeholder: '请输入',
      },
      fieldName: 'daily_new_users_first_recharge',
      label: '首日新增首次充值',
      rules: 'required',
    },
    {
      component: 'InputNumber',
      componentProps: {
        controls: false,
        placeholder: '请输入',
      },
      fieldName: 'total_reg',
      label: '总注册',
      rules: 'required',
    },
    {
      component: 'InputNumber',
      componentProps: {
        controls: false,
        placeholder: '请输入',
      },
      fieldName: 'total_new',
      label: '总新增',
      rules: 'required',
    },
    {
      component: 'InputNumber',
      componentProps: {
        controls: false,
        placeholder: '请输入',
      },
      fieldName: 'total_new_recharge',
      label: '总新增首次充值',
      rules: 'required',
    },
  ],
  wrapperClass: 'grid-cols-4',
});
fixFieldFormApi.setState({ showDefaultActions: false });

const options = reactive<AttributionData[]>([]);
const initData = async () => {
  try {
    const response = await getAllAttribution();
    if (response) {
      options.length = 0;
      options.push(...response);
    }
    // 设置默认选项
    const defaultValues: Record<string, any> = {};
    options.forEach((row) => {
      if (row.default !== undefined) {
        defaultValues[row.name] = row.default;
      }
    });
    await baseFormApi.setValues(defaultValues);
  } catch {
    message.error('获取归因选项失败');
  }
};
const generateSchema = () => {
  return options.map((row) => ({
    component: 'Select',
    componentProps: {
      allowClear: true,
      filterOption: true,
      mode: row.mode || 'single',
      options: row.options.map((option: string) => ({
        label: option,
        value: option,
      })),
      placeholder: '请选择',
      showSearch: true,
      style: { width: '200px' },
    },
    fieldName: row.name,
    label: row.title,
    rules: 'required',
  }));
};
const fileList = ref<UploadProps['fileList']>([]);
const uploading = ref<boolean>(false);
const uploading1 = ref<boolean>(false);

const beforeUpload: UploadProps['beforeUpload'] = async (file) => {
  // 上传文件校验表单字段
  const aValidate = await baseFormApi.validate();
  const bValidate = await fixFieldFormApi.validate();
  if (aValidate.valid && bValidate.valid) {
    fileList.value = [...(fileList.value || []), file];
    return false;
  } else {
    message.error('请填写所有表单字段后再上传文件');
    return Upload.LIST_IGNORE; // 阻止上传
  }
};

const handleRemove: UploadProps['onRemove'] = (file) => {
  const index = fileList.value.indexOf(file);
  const newFileList = [...fileList.value];
  newFileList.splice(index, 1);
  fileList.value = newFileList;
};
const tables = ref<Record<string, any>>({});
const generateColumns = (data) => {
  if (!data || data.length === 0) return [];
  const firstItem = data[0];
  return Object.keys(firstItem).map((key) => ({
    field: key,
    title: key,
  }));
};

const gridComponents = reactive<Record<string, any>>({});
watch(
  tables,
  (newTables) => {
    const tableNames = Object.keys(newTables);

    tableNames.forEach((tableName) => {
      if (gridComponents[tableName]) {
        gridComponents[tableName].gridApi.setGridOptions({
          columns: generateColumns(tables.value[tableName] || []),
          data: tables.value[tableName] || [],
        });
      } else {
        const [Grid, gridApi] = useVbenVxeGrid({
          gridOptions: computed(() => ({
            border: true,
            columns: generateColumns(tables.value[tableName] || []),
            data: tables.value[tableName] || [],
            pagerConfig: {
              enabled: false,
            },
            showOverflow: true,
          })),
          tableTitle: tableName,
        });

        gridComponents[tableName] = {
          Grid: markRaw(Grid),
          gridApi,
        };
      }
    });
  },
  { deep: true, immediate: true },
);

const budgetAllocation = ref<any[]>([]);
const totalBudget = ref<number | undefined>(undefined);
const recBudget = ref<number | undefined>(undefined);
const budgetAllocationGrid = ref();

watch(
  budgetAllocation,
  (newData) => {
    if (newData && Array.isArray(newData) && newData.length > 0) {
      const [Grid] = useVbenVxeGrid({
        gridOptions: computed(() => ({
          border: true,
          columns: generateColumns(newData),
          data: newData,
          pagerConfig: {
            enabled: false,
          },
          showOverflow: true,
        })),
        tableTitle: '预算分配结果',
      });
      budgetAllocationGrid.value = markRaw(Grid);
    }
  },
  { deep: true },
);

const handleUpload = async () => {
  if (fileList.value.length === 0) {
    message.warning('请先上传文件');
    return;
  }

  uploading.value = true;

  try {
    const baseFormValues = baseFormApi.form.values;
    const fixFieldValues = fixFieldFormApi.form.values;

    const formData = new FormData();

    fileList.value.forEach((file: any) => {
      formData.append('files', file as any);
    });

    Object.entries(baseFormValues).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        value.forEach((item) => {
          formData.append(key, item);
        });
      } else if (value !== null && value !== undefined) {
        formData.append(key, value);
      }
    });

    Object.entries(fixFieldValues).forEach(([key, value]) => {
      if (value !== null && value !== undefined) {
        formData.append(key, value);
      }
    });
    formData.append(
      'time',
      selectedHour.value === undefined
        ? selectedDate.value.format('YYYY-MM-DD')
        : `${selectedDate.value.format('YYYY-MM-DD')}-${selectedHour.value}`,
    );
    formData.append('reportType', reportType.value);

    const response = await uploadAttributionData(formData);
    message.success(`成功上传 ${response.files.length} 个文件`);
    fileList.value = [];
    await new Promise((resolve) => setTimeout(resolve, 3000));
    tables.value = {
      Summary数据表: [
        {
          付费率: 0.25,
          总注册: 20,
          总注册成本: 4.47,
          总消耗: 89.5,
          新增: 5,
          时间: '2025/03/18 12:00',
          点击成本: 0.56,
          点击注册转化: 0.12,
          点击点击量: 160,
          首充成本: 17.9,
        },
      ],
      微调: [
        {
          'Ad name': 'Pb0d2ff4b',
          'Ad Set Name': 'set_004a14',
          'Campaign name': 'yyl_ad221_AK6687_030401_apch',
          'Cost per purchase': 99,
          'Cost per registration completed': null,
          Purchases: null,
          'Registrations Completed': 99,
          操作: '同组计素材',
        },
      ],
    };
    totalBudget.value = 200;
    recBudget.value = 150;
    uploading.value = false;
  } catch (error) {
    message.error(
      `文件上传失败: ${error instanceof Error ? error.message : String(error)}`,
    );
  } finally {
    uploading.value = false;
  }
};
const handleAllocation = async () => {
  try {
    uploading1.value = true;
    await new Promise((resolve) => setTimeout(resolve, 3000));
    budgetAllocation.value = [
      {
        'Amount spent (USD)': 67.33,
        'Campaign Budget': 150,
        'Campaign name': 'yyl_ad221_AK6688_030801_apch',
        'Cost per purchase': 16.83,
        'Cost per registration completed': 4.21,
        'new budget': 150,
        Purchases: 4,
        'Registrations Completed': 16,
      },
      {
        'Amount spent (USD)': 22.17,
        'Campaign Budget': 50,
        'Campaign name': 'yyl_ad221_AK6687_030401_apch',
        'Cost per purchase': 22.17,
        'Cost per registration completed': 5.54,
        'new budget': '暂停',
        Purchases: 1,
        'Registrations Completed': 4,
      },
    ];
    uploading1.value = false;
  } catch (error) {
    message.error(
      `预算分配失败: ${error instanceof Error ? error.message : String(error)}`,
    );
  } finally {
    uploading1.value = false;
  }
};
watch(
  [options],
  () => {
    const schema = generateSchema();
    baseFormApi.setState(() => ({
      schema,
    }));
  },
  { deep: true, immediate: false },
);
onMounted(async () => {
  await initData();
});

const reportType = ref('hourly');
const dateFormat = 'YYYY-MM-DD';
const availableHours = [0, 3, 6, 9, 12, 15, 18, 21];
const selectedDate = ref(dayjs.tz());
const getNearestHour = () => {
  const currentHour = dayjs.tz().hour();
  return (
    [...availableHours].sort(
      (a, b) => Math.abs(a - currentHour) - Math.abs(b - currentHour),
    )[0] || 0
  );
};
const selectedHour = ref<number | undefined>(getNearestHour());

const setDateAndHour = (date: dayjs.Dayjs, hour?: number | undefined) => {
  selectedDate.value = date;
  selectedHour.value = hour;
};

watch(reportType, (newValue) => {
  if (newValue === 'hourly') {
    setDateAndHour(dayjs.tz(), getNearestHour());
  } else {
    setDateAndHour(dayjs.tz().subtract(1, 'day'));
  }
});

onMounted(() => {
  if (reportType.value === 'hourly') {
    setDateAndHour(dayjs.tz(), getNearestHour());
  } else {
    setDateAndHour(dayjs.tz().subtract(1, 'day'));
  }
});
</script>

<template>
  <div
    class="adpulse-section-page bg-background min-h-full p-[var(--adpulse-page-gap)]"
  >
    <Card title="表格上传">
      <Row :gutter="80">
        <BaseForm />
      </Row>
      <Row justify="space-evenly">
        <fixFieldForm />
      </Row>
      <Row>
        <Col :span="24">
          <div class="upload-container" style="position: relative">
            <Upload.Dragger
              name="files"
              :multiple="true"
              :before-upload="beforeUpload"
              :show-upload-list="true"
              style="height: 200px; overflow: auto"
              :file-list="fileList"
              @remove="handleRemove"
            >
              <p class="ant-upload-text">上传投放平台文档</p>
              <span class="icon-[ant-design--inbox-outlined] text-2xl"></span>
              <p class="ant-upload-hint">点击或拖拽文件,支持单个或批量上传</p>
            </Upload.Dragger>
          </div>
        </Col>
      </Row>
      <Row justify="space-evenly" style="margin-top: 10px">
        <Col>
          <Radio.Group v-model:value="reportType">
            <Radio.Button value="hourly">时报</Radio.Button>
            <Radio.Button value="daily">日报</Radio.Button>
          </Radio.Group>
          <DatePicker
            v-model:value="selectedDate"
            :disabled="false"
            :format="dateFormat"
          />
          <Select v-if="reportType === 'hourly'" v-model:value="selectedHour">
            <Select.Option
              v-for="hour in availableHours"
              :key="hour"
              :value="hour"
            >
              {{ hour }}
            </Select.Option>
          </Select>
        </Col>
      </Row>
      <Row style="margin-top: 20px" justify="space-evenly">
        <Col>
          <Button :loading="uploading" @click="handleUpload">
            {{ uploading ? '分析中...' : '开始分析' }}
          </Button>
        </Col>
      </Row>
      <Row>
        <Col :span="24">
          <div v-for="(table, name) in gridComponents" :key="name" class="mb-4">
            <component :is="table.Grid" />
          </div>
        </Col>
      </Row>
      <Row v-if="totalBudget" justify="center" :gutter="16" align="middle">
        <Col>
          <span>总预算: {{ totalBudget }}</span>
        </Col>
        <Col style="padding-right: 0">
          <span>计划分配预算:</span>
        </Col>
        <Col style="padding-left: 0">
          <InputNumber
            :controls="false"
            style="width: 100px"
            v-model:value="recBudget"
          />
        </Col>
        <Col>
          <Button :loading="uploading1" @click="handleAllocation">
            {{ uploading1 ? '预算分配中...' : '开始分配预算' }}
          </Button>
        </Col>
      </Row>
      <Row v-if="budgetAllocationGrid">
        <Col :span="24">
          <div class="mb-4">
            <component :is="budgetAllocationGrid" />
          </div>
        </Col>
      </Row>
    </Card>
  </div>
</template>

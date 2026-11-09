<script lang="ts" setup>
import { computed, markRaw, onMounted, ref } from 'vue';

const props = defineProps<{ showButton?: boolean }>();

import { Button, message, Modal, notification } from 'ant-design-vue';
import dayjs, { Dayjs } from 'dayjs';
import isBetween from 'dayjs/plugin/isBetween';
import utc from 'dayjs/plugin/utc';

import { useVbenForm } from '#/adapter/form';
import { submitHourlyReport } from '#/api/dashboard';
import AgentLineSelect from '#/views/components/AgentLineSelect.vue';
import PlatformSelect from '#/views/components/PlatformSelect.vue';

dayjs.extend(utc);
dayjs.extend(isBetween);

const isModalVisible = ref(false);
const loading = ref(false);
const dateTimeFormat = 'YYYY-MM-DD HH';

// 控制 DatePicker 面板的开关
const reportDatePickerOpen = ref(false);
const chinaDatePickerOpen = ref(false);

// 按钮配置
const submitBtnOptions = computed(() => ({
  content: '提交',
  loading: loading.value,
}));

// 设置全局通知配置
onMounted(async () => {
  notification.config({
    maxCount: 10, // 最大显示数量，设置足够大的数量以允许堆叠
  });
});

// 提交表单
const handleSubmit = async (values: any) => {
  loading.value = true;
  // 检查是否在允许的时间范围内
  if (!isWithinLastDay(values.report_date)) {
    message.error('只允许修改最近2天的数据');
    return;
  }
  const fieldsInfo = `
报告时间: ${dayjs.tz(values.report_date).format(dateTimeFormat)}
渠道号: ${values.agent_line}
项目名称: ${values.game_platform}
注册人数: ${values.registrations}
首充金额: ${values.first_recharge_amount}
首充人数: ${values.first_recharge_users}`;

  try {
    const response = await submitHourlyReport(
      dayjs.tz(values.report_date).format(dateTimeFormat),
      dayjs.tz(values.china_date).format(dateTimeFormat),
      values.agent_line,
      values.game_platform,
      values.registrations,
      values.first_recharge_amount,
      values.first_recharge_users,
    );

    if (response.code === 0) {
      notification.success({
        description: `${response.message}\n${fieldsInfo}`,
        duration: 0, // 设置为0表示不会自动关闭
        message: '分析成功',
        placement: 'bottomLeft',
      });
      isModalVisible.value = false;
    } else {
      notification.error({
        description: `${response.message}\n${fieldsInfo}`,
        duration: 0, // 设置为0表示不会自动关闭
        message: '后台分析失败',
        placement: 'bottomLeft',
      });
    }
  } catch (error: any) {
    notification.error({
      description: `${error.message}\n${fieldsInfo}`,
      duration: 0,
      message: '填写失败',
      placement: 'bottomLeft',
    });
  } finally {
    loading.value = false;
  }
};

// 表单创建
const [CreateForm, createFormApi] = useVbenForm({
  handleSubmit,
  resetButtonOptions: {
    content: '重置',
  },
  schema: [
    {
      component: 'DatePicker',
      componentProps: {
        allowClear: false,
        disabledDate: (current: Dayjs) => {
          return current && current > dayjs.tz().endOf('day');
        },
        format: dateTimeFormat,
        showTime: { format: 'HH' },
        valueFormat: dateTimeFormat,
        get open() {
          return reportDatePickerOpen.value;
        },
        onOpenChange: (open: boolean) => {
          reportDatePickerOpen.value = open;
        },
        onSelect: (value: any) => {
          // 当选择日期时，自动关闭
          if (value) {
            createFormApi.setFieldValue(
              'report_date',
              dayjs.tz(value).format(dateTimeFormat),
            );
            reportDatePickerOpen.value = false;
          }
        },
      },
      defaultValue: dayjs.tz().format(dateTimeFormat),
      fieldName: 'report_date',
      help: '请换算成账户时区而非中国时区',
      label: '账户时间',
      rules: 'required',
    },
    {
      component: 'DatePicker',
      componentProps: {
        allowClear: false,
        disabledDate: (current: Dayjs) => {
          return current && current > dayjs.tz().endOf('day');
        },
        format: dateTimeFormat,
        showTime: { format: 'HH' },
        valueFormat: dateTimeFormat,
        get open() {
          return chinaDatePickerOpen.value;
        },
        onOpenChange: (open: boolean) => {
          chinaDatePickerOpen.value = open;
        },
        onSelect: (value: any) => {
          // 当选择日期时，自动关闭
          if (value) {
            createFormApi.setFieldValue(
              'china_date',
              dayjs.tz(value).format(dateTimeFormat),
            );
            chinaDatePickerOpen.value = false;
          }
        },
      },
      defaultValue: dayjs.tz().format(dateTimeFormat),
      fieldName: 'china_date',
      help: '请输入账户时间对应的中国时间, 一般为当前小时',
      label: '中国时间',
      rules: 'required',
    },
    {
      component: markRaw(PlatformSelect),
      componentProps: {
        placeholder: '请选择项目名称（将根据渠道号自动填充）',
        style: { width: '50%' },
        disabled: true,
      },
      defaultValue: 'okjkt',
      fieldName: 'game_platform',
      label: '项目名称',
      rules: 'required',
    },
    {
      component: markRaw(AgentLineSelect),
      componentProps: {
        placeholder: '请选择渠道号',
        style: { width: '50%' },
        onChange: (value: string, platform?: string) => {
          if (platform) {
            createFormApi.setFieldValue('game_platform', platform);
          }
        },
      },
      defaultValue: 'ad1026',
      fieldName: 'agent_line',
      label: '渠道号',
      rules: 'required',
    },
    {
      component: 'InputNumber',
      componentProps: {
        style: { width: '100%' },
      },
      fieldName: 'registrations',
      label: '注册人数',
      rules: 'required',
    },
    {
      component: 'InputNumber',
      componentProps: {
        style: { width: '100%' },
      },
      fieldName: 'first_recharge_users',
      label: '首充人数',
      rules: 'required',
    },
    {
      component: 'InputNumber',
      componentProps: {
        style: { width: '100%' },
      },
      fieldName: 'first_recharge_amount',
      label: '首充金额',
      rules: 'required',
    },
    // {
    //   component: 'Select',
    //   componentProps: {
    //     options: [
    //       { label: 'Asia/Bangkok(泰国/西部印尼)', value: 'Asia/Bangkok' },
    //       // { label: 'Antarctica/Davis(新西兰)', value: 'Antarctica/Davis' },
    //     ],
    //     style: { width: '100%' },
    //   },
    //   defaultValue: 'Asia/Bangkok',
    //   fieldName: 'timezone_name',
    //   help: '默认不管, 开发者的账户时区在多个地区(开发者同时有积分墙和其他项目)时需要',
    //   label: '账户时区',
    //   rules: 'required',
    // },
  ],
  submitButtonOptions: submitBtnOptions,
});

const openModal = () => {
  isModalVisible.value = true;
};

defineExpose({ openModal });

const isWithinLastDay = (date: Dayjs): boolean => {
  const selectedDay = dayjs.tz(date).format('YYYY-MM-DD');
  const today = dayjs.tz().format('YYYY-MM-DD');
  const yesterday = dayjs.tz().subtract(1, 'day').format('YYYY-MM-DD');
  return selectedDay === today || selectedDay === yesterday;
};
</script>

<template>
  <div>
    <Button v-if="props.showButton !== false" @click="openModal">填写BI</Button>
    <Modal
      v-model:open="isModalVisible"
      title="填写BI数据"
      :footer="null"
      width="500px"
    >
      <div class="[&_.pb-6]:!pb-4">
        <CreateForm />
      </div>
    </Modal>
  </div>
</template>

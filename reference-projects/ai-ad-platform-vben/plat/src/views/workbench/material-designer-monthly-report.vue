<script lang="ts" setup>
import type { MaterialSettlementReportFormValue } from '#/domain/material-designer-settlement';

import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { useUserStore } from '@vben/stores';
import { Button, Card, message, Modal, PageHeader } from 'ant-design-vue';

import { dailyReportApi } from '#/api';
import { MATERIAL_DESIGNER_DAILY_REPORT_ID } from '#/domain/fixed-daily-report-rules';
import {
  createMaterialSettlementReportFields,
  queryMaterialSettlementTaskLineSpends,
} from '#/domain/material-designer-settlement';
import { loadMonthlyReports, saveMonthlyReports } from '#/domain/report-rules';

import MaterialSettlementReportForm from './components/MaterialSettlementReportForm.vue';

defineOptions({ name: 'WorkbenchMaterialDesignerMonthlyReport' });

interface MaterialSettlementReportFormInstance {
  validate: () => Promise<MaterialSettlementReportFormValue | undefined>;
}

const router = useRouter();
const userStore = useUserStore();
const submitting = ref(false);
const materialSettlementFormRef = ref<MaterialSettlementReportFormInstance>();
const materialDesignerName = computed(
  () =>
    userStore.userInfo?.realName || userStore.userInfo?.full_name || '当前用户',
);
const currentUserId = computed(() => {
  const userInfo = userStore.userInfo as Record<string, unknown> | undefined;
  const candidate = userInfo?.userId ?? userInfo?.user_id ?? userInfo?._id;

  if (typeof candidate === 'number') return String(candidate);
  return typeof candidate === 'string' ? candidate.trim() : '';
});

function confirmOverwriteReport(settlementMonth: string) {
  return new Promise<boolean>((resolve) => {
    Modal.confirm({
      cancelText: '继续编辑',
      content: `结算月份 ${settlementMonth} 已提交日报。确认后将以当前填写内容覆盖原日报，并重新提交通知。`,
      okText: '确认覆盖',
      onCancel: () => resolve(false),
      onOk: () => resolve(true),
      title: '确认覆盖原日报？',
    });
  });
}

async function findCurrentPeriodReport(settlementMonth: string) {
  const reports = await dailyReportApi.listReports();

  // 服务端按提交人 ID 和结算月份保证唯一性，前端也以相同条件定位原记录，避免同名人员相互覆盖。
  return reports.find(
    (report) =>
      report.ruleId === MATERIAL_DESIGNER_DAILY_REPORT_ID &&
      report.authorId === currentUserId.value &&
      report.fields.settlementMonth === settlementMonth,
  );
}

async function submitReport() {
  submitting.value = true;
  try {
    const formValue = await materialSettlementFormRef.value?.validate();
    if (!formValue) return;

    const existingReport = await findCurrentPeriodReport(
      formValue.settlementMonth,
    );
    if (
      existingReport &&
      !(await confirmOverwriteReport(formValue.settlementMonth))
    ) {
      return;
    }

    let taskLines;
    try {
      taskLines = await queryMaterialSettlementTaskLineSpends(
        formValue.settlementMonth,
        formValue.taskLines,
      );
    } catch {
      message.error('花费读取失败，月报未提交，请稍后重试');
      return;
    }
    const fields = createMaterialSettlementReportFields(
      { ...formValue, taskLines },
      materialDesignerName.value,
    );

    const report = existingReport
      ? await dailyReportApi.update(existingReport.id, { fields })
      : await dailyReportApi.submit({
          fields,
          ruleId: MATERIAL_DESIGNER_DAILY_REPORT_ID,
        });
    saveMonthlyReports([
      report,
      ...loadMonthlyReports().filter((item) => item.id !== report.id),
    ]);
    message.success(
      existingReport ? '原日报已覆盖并重新提交' : '素材师月报已提交',
    );
    await router.push('/workbench/daily-reports');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Page auto-content-height>
    <main class="mx-auto max-w-[1200px] space-y-4">
      <PageHeader
        :ghost="false"
        :on-back="() => router.back()"
        sub-title="按项目管理中的投放师、项目和任务线填写结算范围；提交后按日报配置通知相关人员。"
        title="素材师月报"
      >
        <template #extra>
          <Button :loading="submitting" type="primary" @click="submitReport">
            提交汇报
          </Button>
        </template>
      </PageHeader>

      <Card :bordered="false" class="border-border border shadow-none">
        <template #title>结算报表</template>
        <p class="text-muted-foreground mb-4 mt-0 text-sm leading-6">
          选择投放师后会自动勾选其可结算项目和任务线，可继续按项目或任务线调整范围。
        </p>
        <MaterialSettlementReportForm ref="materialSettlementFormRef" />
      </Card>
    </main>
  </Page>
</template>

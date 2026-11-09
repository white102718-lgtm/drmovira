import { dailyReportApi } from '#/api/daily-report';

/**
 * 日报消息统一入口。服务端必须按同一个业务事件同时创建站内消息和飞书消息，
 * 前端不直接请求飞书 webhook，避免泄露凭据或出现两个渠道状态不一致。
 */
export async function notifyDailyReportSubmitted(input: {
  businessId: string;
  businessType: 'daily-report' | 'daily-report-application';
  reportName: string;
}) {
  try {
    await dailyReportApi.notify(
      {
        ...input,
        channels: ['system', 'feishu'],
      },
      { skipErrorMessage: true },
    );
    return true;
  } catch {
    // 日报记录已提交时，通知故障不能回滚或阻断已完成的业务流转。
    return false;
  }
}

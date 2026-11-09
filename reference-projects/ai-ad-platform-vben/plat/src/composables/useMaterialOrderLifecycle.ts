import type { MaterialOrderLifecycleAction } from '#/api/requirement';
import { onScopeDispose, ref } from 'vue';
import { Modal, message } from 'ant-design-vue';
import { changeMaterialOrderLifecycle } from '#/api/requirement';

/** 列表和详情共用取消确认、提交反馈与刷新；确认期间固定工单及版本快照。 */
export function useMaterialOrderLifecycle(onChanged: () => Promise<unknown>) {
  const pendingOrderId = ref('');
  const pendingAction = ref<MaterialOrderLifecycleAction | ''>('');
  let closeLoading: (() => void) | undefined;
  let confirmation: ReturnType<typeof Modal.confirm> | undefined;
  onScopeDispose(() => {
    confirmation?.destroy();
    closeLoading?.();
  });

  async function execute(
    order: { id: string; title?: string; version: number },
    action: MaterialOrderLifecycleAction,
  ) {
    if (pendingOrderId.value) return;
    pendingOrderId.value = order.id;
    pendingAction.value = action;
    closeLoading = message.loading(
      {
        pause: '正在暂停任务…',
        resume: '正在开启任务…',
        cancel: '正在取消任务…',
      }[action],
      0,
    );
    try {
      try {
        await changeMaterialOrderLifecycle(order.id, action, order.version);
      } catch {
        // 请求层已提示原因；刷新使版本冲突、权限变化后的旧操作入口失效。
        closeLoading?.();
        await onChanged();
        return;
      }
      // 刷新结束前保持加载和禁用，避免旧状态按钮短暂恢复后被重复点击。
      await onChanged();
      closeLoading?.();
      message.success(
        { pause: '任务已暂停', resume: '任务已开启', cancel: '任务已取消' }[
          action
        ],
      );
    } finally {
      closeLoading?.();
      closeLoading = undefined;
      pendingAction.value = '';
      pendingOrderId.value = '';
    }
  }

  function run(
    order: { id: string; title?: string; version: number },
    action: MaterialOrderLifecycleAction,
  ) {
    if (pendingOrderId.value || confirmation) return;
    if (action !== 'cancel') return execute({ ...order }, action);
    const snapshot = { ...order };
    confirmation = Modal.confirm({
      title: `确认取消“${order.title || '该素材工单'}”？`,
      content:
        '取消后不可恢复，任务将停止分配、制作和验收。已有素材和历史记录仍可查看。',
      okText: '确认取消',
      okType: 'danger',
      cancelText: '暂不取消',
      autoFocusButton: 'cancel',
      onOk: () => execute(snapshot, action),
      afterClose: () => {
        confirmation = undefined;
      },
    });
  }
  return { pendingOrderId, pendingAction, run };
}

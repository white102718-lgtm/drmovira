import { computed } from 'vue';
import { useAccess } from '@vben/access';

/** 新建投放任务统一使用登录会话下发的按钮权限，不再按角色判断。 */
export function useDeliveryTaskAccess() {
  const { hasAccessByCodes } = useAccess();
  const canCreateDeliveryTask = computed(() =>
    hasAccessByCodes(['operate:button:add']),
  );

  return { canCreateDeliveryTask };
}

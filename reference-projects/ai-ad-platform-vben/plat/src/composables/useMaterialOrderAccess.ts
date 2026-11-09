import { computed } from 'vue';
import { useAccess } from '@vben/access';

/** 新建素材工单统一使用登录会话下发的权限码，不以角色或管理员身份兜底。 */
export function useMaterialOrderAccess() {
  const { hasAccessByCodes } = useAccess();
  const canCreateMaterialOrder = computed(() =>
    hasAccessByCodes(['media:button:add']),
  );

  return { canCreateMaterialOrder };
}

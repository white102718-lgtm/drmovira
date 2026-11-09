<script lang="ts" setup>
import { useVbenModal } from '@vben/common-ui';

import message from 'ant-design-vue/es/message';

defineOptions({ name: 'MfaRebindModal' });

const [Modal, modalApi] = useVbenModal({
  fullscreenButton: false,
  footer: null,
  showCancelButton: false,
  showConfirmButton: true,
  title: '更换验证器',
  confirmText: '我知道了',
  onConfirm() {
    modalApi.close();
  },
  onOpenChange(open) {
    if (open) {
      // 打开时提示当前不可用，由管理员重置MFA后在下次登录时重新绑定
      message.info(
        '更换验证器暂未开放。如已丢失验证器，请联系管理员重置MFA，重置后在下次登录时可重新绑定。',
      );
    }
  },
});
</script>

<template>
  <Modal width="480px">
    <div class="px-2 py-3">
      <div class="mb-3">
        <p class="text-foreground mb-1 text-base font-semibold">
          更换验证器暂未开放
        </p>
        <p class="text-muted-foreground text-sm leading-6">
          如需更换验证器或MFA密钥已丢失，请联系系统管理员为您重置MFA。
          管理员重置后，您在下次登录时会自动进入绑定新验证器的流程，无需手动操作。
        </p>
      </div>
    </div>
  </Modal>
</template>

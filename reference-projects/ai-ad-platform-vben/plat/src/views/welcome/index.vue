<script setup lang="ts">
import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
</script>

<template>
  <Page auto-content-height class="bg-muted/40">
    <div class="flex h-full min-h-0 items-center justify-center p-4">
      <section
        aria-labelledby="welcome-title"
        class="border-border bg-card w-full max-w-xl rounded-xl border p-8 text-center sm:p-10"
      >
        <div
          aria-hidden="true"
          class="bg-muted text-muted-foreground mx-auto flex h-12 w-12 items-center justify-center rounded-full"
        >
          <IconifyIcon icon="lucide:hand" class="text-xl" />
        </div>
        <h1
          id="welcome-title"
          class="text-foreground mb-0 mt-5 text-xl font-semibold"
        >
          欢迎使用 AdPulse
        </h1>
        <p class="text-muted-foreground mb-0 mt-3 text-sm leading-6">
          当前账号暂无可访问功能，请联系管理员为角色分配菜单权限。
        </p>
      </section>
    </div>
  </Page>
</template>

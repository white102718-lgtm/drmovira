<script lang="ts" setup>
/**
 * 必须用同源 HTTP 地址下载。Chrome 对 blob: / data: 会丢掉文件名，下载栏只剩 UUID。
 * 中文名走响应头 filename*；download 属性和 URL 末段只放带后缀的 ASCII 名。
 */
import { computed, onMounted } from 'vue';

import { rememberAgentDownloadCookie } from '#/api/agent';
import {
  agentBlobHref,
  asciiDownloadName,
  safeDownloadName,
} from '#/utils/download';

defineOptions({ inheritAttrs: false });

const props = defineProps<{
  filename: string;
  url?: string;
}>();

const name = computed(() => safeDownloadName(props.filename));
const ascii = computed(() => asciiDownloadName(props.filename));
const href = computed(() => agentBlobHref(props.url || '', true, name.value));

onMounted(() => {
  rememberAgentDownloadCookie();
});
</script>

<template>
  <a
    v-if="href"
    v-bind="$attrs"
    :href="href"
    :download="ascii"
    :title="name"
    @click="rememberAgentDownloadCookie"
  >
    <slot></slot>
  </a>
  <span v-else class="opacity-50">
    <slot></slot>
  </span>
</template>

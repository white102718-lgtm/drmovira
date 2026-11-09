<script lang="ts" setup>
import AssetManagementPanel from '#/views/media-resources/components/AssetManagementPanel.vue';
import MediaResourcePage from '#/views/media-resources/components/MediaResourcePage.vue';

defineOptions({ name: 'WorkbenchMyAssets' });
</script>

<template>
  <!--
    后端动态菜单可能仍指向历史工作台组件；这里复用真实资产台账，确保办理结果始终来自
    /asset-flow/assets/mine，而不是浏览器本地演示数据。
  -->
  <MediaResourcePage content-class="!p-3 sm:!p-4">
    <AssetManagementPanel />
  </MediaResourcePage>
</template>

<script lang="ts" setup>
import { useRoute } from 'vue-router';
import AdgenCanvasEmbed from './adgen-canvas-embed.vue';
import CanvasReadonlyView from './readonly-view.vue';
const route = useRoute();
</script>

<template>
  <CanvasReadonlyView v-if="route.query.view === 'readonly'" />
  <AdgenCanvasEmbed v-else />
</template>

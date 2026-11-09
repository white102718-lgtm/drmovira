<script setup lang="ts">
import type { AgencyLine } from '#/domain/agency-line';
import { ref } from 'vue';
import { Button, message, Popover } from 'ant-design-vue';
import { changeAgencyLineOptimizer } from '#/api/agency-line-actions';
import StableUserTreeSelect from '../../../components/StableUserTreeSelect.vue';

const props = defineProps<{ line: AgencyLine; disabled?: boolean }>();
const emit = defineEmits<{
  saved: [line: AgencyLine];
  busy: [value: boolean];
}>();
const open = ref(false);
const saving = ref(false);

/** 选人即提交，成功前保留旧值；失败后可重新选择。 */
async function selectOptimizer(value: string | string[] | undefined) {
  if (
    saving.value ||
    props.disabled ||
    Array.isArray(value) ||
    value === props.line.optimizerId
  )
    return;
  saving.value = true;
  emit('busy', true);
  try {
    const line = await changeAgencyLineOptimizer(props.line.id, value);
    emit('saved', line);
    open.value = false;
    message.success('投手已更新');
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '投手更新失败，请重试',
    );
  } finally {
    saving.value = false;
    emit('busy', false);
  }
}
</script>

<template>
  <Popover v-model:open="open" trigger="click" placement="bottomLeft">
    <template #content>
      <div class="w-72 max-w-[80vw] space-y-2">
        <div class="font-medium">按组织架构选择投手</div>
        <StableUserTreeSelect
          class="w-full"
          v-if="open"
          :model-value="line.optimizerId"
          :legacy-label="line.optimizerName"
          :disabled="saving || disabled"
          placeholder="展开部门选择人员"
          @change="selectOptimizer"
        />
        <div class="text-muted-foreground text-sm">
          {{ saving ? '正在更新…' : '选择后立即生效' }}
        </div>
      </div>
    </template>
    <Button type="link" :disabled="disabled" :loading="saving"
      >{{ line.optimizerName || '未分配'
      }}{{ line.optimizerStatus === 0 ? '（已停用）' : '' }}</Button
    >
  </Popover>
</template>

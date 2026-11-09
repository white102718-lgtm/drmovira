<script setup lang="ts">
import type {
  ImportDepartment,
  ImportUser,
  ImportedAllocation,
} from '#/domain/task/allocation-import';
import AntDataTable from '#/components/ui/AntDataTable.vue';
import { computed, ref, watch } from 'vue';
import { Alert, Button, Input, Modal } from 'ant-design-vue';
import { parseAllocationImport } from '#/domain/task/allocation-import';
import { getSharedOrganizationUsers } from '../../components/organization-options-cache';

const props = defineProps<{
  open: boolean;
  departments: ImportDepartment[];
  existingTeams: string[];
}>();
const emit = defineEmits<{
  'update:open': [value: boolean];
  import: [rows: ImportedAllocation[]];
}>();
const text = ref('');
const users = ref<ImportUser[]>([]);
const loading = ref(false);
const loadError = ref('');
const previewedText = ref<string | undefined>();
const result = computed(() =>
  parseAllocationImport(
    text.value,
    props.departments,
    users.value,
    props.existingTeams,
  ),
);
const canImport = computed(
  () =>
    !loading.value &&
    !loadError.value &&
    previewedText.value === text.value &&
    result.value.rows.length > 0 &&
    !result.value.errors.length,
);

async function loadUsers() {
  loading.value = true;
  loadError.value = '';
  try {
    users.value = await getSharedOrganizationUsers();
  } catch {
    loadError.value = '负责人列表加载失败，请重试';
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    text.value = '';
    previewedText.value = undefined;
    void loadUsers();
  },
);

function confirmImport() {
  if (!canImport.value) return;
  emit('import', result.value.rows);
  emit('update:open', false);
}
</script>

<template>
  <Modal
    :open="open"
    title="批量导入团队分配"
    :width="800"
    :body-style="{ maxHeight: '65vh', overflowY: 'auto' }"
    @cancel="emit('update:open', false)"
  >
    <div class="space-y-4">
      <p class="text-muted-foreground text-sm">
        从 Excel
        复制四列后粘贴：部门、负责人、PWA线路数、H5线路数。支持部门名称或
        ID，以及负责人姓名、账号或 ID；重名时请使用 ID。一次最多 200 行。
      </p>
      <div class="bg-muted overflow-x-auto rounded-md border p-3 text-sm">
        <pre class="m-0">
部门名称或ID&#9;负责人姓名或ID&#9;PWA线路数&#9;H5线路数</pre
        >
      </div>
      <Alert
        message="导入将追加到当前分配，重复部门会报错。所有行校验通过后才会导入，现有分配不会被覆盖。"
        type="info"
        show-icon
      />
      <Alert v-if="loadError" :message="loadError" type="error" show-icon>
        <template #action
          ><Button :loading="loading" @click="loadUsers">重试</Button></template
        >
      </Alert>
      <div>
        <label
          for="allocation-import-text"
          class="mb-2 block text-sm font-medium"
          >表格数据</label
        >
        <Input.TextArea
          id="allocation-import-text"
          v-model:value="text"
          :rows="7"
          :maxlength="100000"
          placeholder="在此粘贴 Excel 单元格（四列，以制表符分隔）"
        />
      </div>
      <template v-if="previewedText === text">
        <Alert
          v-if="result.errors.length"
          type="error"
          show-icon
          :message="`${result.errors.length} 行校验未通过，请修正后重新预览`"
        >
          <template #description
            ><ul class="max-h-40 overflow-y-auto pl-4">
              <li v-for="error in result.errors" :key="error">{{ error }}</li>
            </ul></template
          >
        </Alert>
        <div
          v-if="result.rows.length"
          class="max-h-64 overflow-auto rounded-md border"
        >
          <p class="p-3">校验通过 {{ result.rows.length }} 行</p>
          <AntDataTable
            :data="result.rows"
            row-key="line"
            :page-size="10"
            :columns="[
              { key: 'line', title: '行号' },
              { key: 'teamName', title: '部门' },
              { key: 'assigneeName', title: '负责人' },
              { key: 'pwaCount', title: 'PWA', align: 'right' },
              { key: 'h5Count', title: 'H5', align: 'right' },
            ]"
          />
        </div>
      </template>
    </div>
    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <Button @click="emit('update:open', false)">取消</Button>
        <Button
          :loading="loading"
          :disabled="!!loadError || !text.trim()"
          @click="previewedText = text"
          >校验并预览</Button
        >
        <Button type="primary" :disabled="!canImport" @click="confirmImport"
          >确认导入</Button
        >
      </div>
    </template>
  </Modal>
</template>

<script lang="ts" setup>
import type { MaterialGroup } from '#/api/advertisement/materialGroup';

import { computed, ref } from 'vue';

import { Button, Input, message, Modal, Tooltip } from 'ant-design-vue';
import dayjs from 'dayjs';

import {
  deleteMaterialGroup,
  getMaterialGroups,
} from '#/api/advertisement/materialGroup';

defineProps<{
  hasCurrentMaterials?: boolean; // 当前是否有素材
}>();

const emit = defineEmits<{
  apply: [groupId: string, mode: 'append' | 'replace'];
  history: [];
}>();

const modalVisible = ref(false);

// 搜索和筛选
const searchName = ref('');

// 素材组列表
const materialGroupList = ref<MaterialGroup[]>([]);
const selectedGroup = ref<string | undefined>(undefined);
const loadingGroups = ref(false);
const deletingGroup = ref(false);

// 分页
const pagination = ref({
  page: 1,
  size: 20,
  total: 0,
});

const applying = ref(false);

// 计算筛选后的列表
const filteredGroups = computed(() => {
  let groups = materialGroupList.value;

  // 按名称搜索
  if (searchName.value) {
    const keyword = searchName.value.toLowerCase();
    groups = groups.filter((g) => g.name.toLowerCase().includes(keyword));
  }

  return groups;
});

// 加载素材组列表
async function loadMaterialGroups() {
  try {
    loadingGroups.value = true;

    const params: any = {
      page: pagination.value.page,
      size: pagination.value.size,
    };

    const res: any = await getMaterialGroups(params);

    if (res && res.items) {
      materialGroupList.value = res.items || [];
      pagination.value.total = res.total || 0;
    } else {
      materialGroupList.value = [];
      pagination.value.total = 0;
    }
  } catch (error: any) {
  } finally {
    loadingGroups.value = false;
  }
}

// 刷新列表
async function refresh() {
  await loadMaterialGroups();
}

defineExpose({
  refresh,
  finishApply,
});

// 应用素材组（替换模式）
function handleApplyGroup(mode: 'append' | 'replace' = 'replace') {
  if (!selectedGroup.value) {
    message.warning('请先选择要应用的素材组');
    return;
  }

  applying.value = true;
  emit('apply', selectedGroup.value, mode);
}

// 完成应用（由父组件调用）
function finishApply() {
  applying.value = false;
  modalVisible.value = false;
}

// 取消
function handleCancel() {
  if (applying.value) return;
  modalVisible.value = false;
}

// 删除素材组
function handleDeleteGroup(groupId: string, event?: Event) {
  if (event) {
    event.stopPropagation();
  }

  Modal.confirm({
    title: '确认删除',
    content: '确定要删除该素材组吗？此操作不可恢复。',
    okText: '确认',
    cancelText: '取消',
    okType: 'danger',
    onOk: async () => {
      try {
        deletingGroup.value = true;
        await deleteMaterialGroup(groupId);

        materialGroupList.value = materialGroupList.value.filter(
          (g) => g.id !== groupId,
        );

        if (selectedGroup.value === groupId) {
          selectedGroup.value = undefined;
        }

        message.success('素材组删除成功');
      } catch (error: any) {
      } finally {
        deletingGroup.value = false;
      }
    },
  });
}

// 查看历史
function handleViewHistory() {
  emit('history');
  modalVisible.value = false;
}

// 格式化时间
function formatTime(time: string) {
  return dayjs.tz(time).format('YYYY-MM-DD HH:mm');
}

// 打开弹窗
function handleOpen() {
  modalVisible.value = true;
  loadMaterialGroups();
}
</script>

<template>
  <div class="material-group-load-tab">
    <Tooltip title="加载已保存的素材组">
      <Button
        type="primary"
        class="flex items-center gap-2 rounded-md"
        @click="handleOpen"
      >
        <span class="icon-[ant-design--folder-open-outlined] text-white"></span>
        加载素材组
      </Button>
    </Tooltip>

    <!-- 加载素材组弹窗 -->
    <Modal
      :open="modalVisible"
      title="加载素材组"
      :footer="null"
      width="560px"
      @cancel="handleCancel"
    >
      <!-- 搜索和筛选 -->
      <div class="mb-4">
        <!-- 名称搜索 -->
        <div class="flex items-center gap-3">
          <span class="w-16 text-sm text-gray-700">搜索:</span>
          <Input
            v-model:value="searchName"
            placeholder="按名称搜索"
            allow-clear
          >
            <template #prefix>
              <span class="icon-[ant-design--search-outlined]"></span>
            </template>
          </Input>
        </div>
      </div>

      <!-- 素材组列表 -->
      <div class="mb-4">
        <div class="mb-2 flex items-center justify-between">
          <span class="text-sm text-gray-700">
            素材组列表 ({{ filteredGroups.length }})
          </span>
          <Button type="link" @click="handleViewHistory">
            <span class="icon-[ant-design--history-outlined] mr-1"></span>
            查看历史
          </Button>
        </div>

        <div
          class="h-[var(--adpulse-popup-table-height)] space-y-2 overflow-y-auto rounded border border-gray-200 p-2"
        >
          <div
            v-if="loadingGroups"
            class="flex h-full items-center justify-center text-gray-400"
          >
            <span
              class="icon-[ant-design--loading-outlined] mr-2 animate-spin"
            ></span>
            加载中...
          </div>

          <div
            v-else-if="filteredGroups.length === 0"
            class="flex h-full items-center justify-center text-gray-400"
          >
            暂无素材组
          </div>

          <div
            v-for="group in filteredGroups"
            v-else
            :key="group.id"
            class="cursor-pointer rounded border p-3 transition-all hover:border-blue-500 hover:bg-blue-50"
            :class="{
              'border-blue-500 bg-blue-50': selectedGroup === group.id,
            }"
            @click="selectedGroup = group.id"
          >
            <div class="flex items-start justify-between">
              <div class="flex-1">
                <div class="mb-1 font-medium text-gray-800">
                  {{ group.name }}
                </div>
                <div
                  v-if="group.description"
                  class="mb-2 text-xs text-gray-500"
                >
                  {{ group.description }}
                </div>
                <div class="flex flex-wrap items-center gap-2">
                  <span class="text-xs text-gray-500">
                    {{ group.materials_count }} 个素材
                  </span>
                  <span class="text-xs text-gray-400">
                    {{ formatTime(group.created_at) }}
                  </span>
                </div>
              </div>
              <span
                class="icon-[ant-design--delete-outlined] ml-2 cursor-pointer text-red-500 hover:text-red-600"
                @click="handleDeleteGroup(group.id, $event)"
              ></span>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部操作 -->
      <div
        class="flex items-center justify-end gap-2 border-t border-gray-200 pt-3"
      >
        <Button :disabled="applying" @click="handleCancel">取消</Button>
        <Button
          :disabled="!selectedGroup"
          :loading="applying"
          @click="handleApplyGroup('append')"
        >
          追加到当前
        </Button>
        <Button
          type="primary"
          :disabled="!selectedGroup"
          :loading="applying"
          @click="handleApplyGroup('replace')"
        >
          全部替换
        </Button>
      </div>
    </Modal>
  </div>
</template>

<style lang="scss" scoped>
.material-group-load-tab {
  display: inline-block;
}
</style>

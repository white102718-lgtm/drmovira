<script setup lang="ts">
import type { CreativeEnhancement, MaterialItem } from '../types';

import { Button, Divider, Input, Popover, Switch } from 'ant-design-vue';

import ChatToolTemplatePopover from './ChatToolTemplatePopover.vue';

const props = defineProps<{ material: MaterialItem }>();
const emit = defineEmits<{ newChatTool: [] }>();

const imageRequired: { field: keyof CreativeEnhancement; label: string }[] = [
  { field: 'show_summary', label: '显示摘要' },
  { field: 'inline_comment', label: '相关评论' },
  { field: 'enhance_cta', label: '增强行动号召' },
  { field: 'reveal_details_over_time', label: '逐步显示详情' },
  { field: 'show_destination_blurbs', label: '显示精选' },
  { field: 'image_brightness_and_contrast', label: '调整亮度和对比度' },
];

const imageOptional: { field: keyof CreativeEnhancement; label: string }[] = [
  { field: 'image_templates', label: '叠加文字' },
  { field: 'image_touchups', label: '图片润色' },
  { field: 'add_music', label: '添加音乐' },
  { field: 'image_animation', label: '添加动画' },
  { field: 'text_optimizations', label: '文案改进' },
];

const videoRequired: { field: keyof CreativeEnhancement; label: string }[] = [
  { field: 'show_summary', label: '显示摘要' },
  { field: 'inline_comment', label: '相关评论' },
  { field: 'enhance_cta', label: '增强行动号召' },
  { field: 'reveal_details_over_time', label: '逐步显示详情' },
  { field: 'show_destination_blurbs', label: '显示精选' },
  { field: 'video_filtering', label: '添加视频特效' },
];

const videoOptional: { field: keyof CreativeEnhancement; label: string }[] = [
  { field: 'detail_to_layout', label: '在广告布局中添加详细信息' },
  { field: 'video_auto_crop', label: '视频润色' },
  { field: 'text_optimizations', label: '文案改进' },
];

function applyTemplate(tpl: any) {
  props.material.chatToolData = {
    ...tpl.data,
    questions: JSON.parse(JSON.stringify(tpl.data.questions)),
  };
  props.material.chatToolTemplateName = tpl.name;
}
</script>

<template>
  <Popover
    trigger="hover"
    placement="right"
    :overlay-style="{ width: '260px' }"
  >
    <template #content>
      <div style="max-height: 480px; overflow-y: auto">
        <!-- 广告中显示的链接 -->
        <div class="mb-2">
          <div class="mb-1 text-xs text-gray-500">广告中显示的链接</div>
          <Input
            v-model:value="material.displayLink"
            placeholder="广告中显示的链接"
            allow-clear
          />
        </div>

        <!-- 聊天模板 -->
        <div class="mb-2">
          <div class="mb-1 text-xs text-gray-500">聊天模板</div>
          <ChatToolTemplatePopover
            @apply="applyTemplate"
            @new="emit('newChatTool')"
          >
            <Button
              style="width: 100%"
              :title="material.chatToolTemplateName || '选择聊天模板'"
            >
              <span class="block truncate">
                {{ material.chatToolTemplateName || '选择聊天模板' }}
              </span>
            </Button>
          </ChatToolTemplatePopover>
        </div>

        <Divider style="margin: 8px 0" />

        <!-- 文案优化 & 网站位置优化 -->
        <div class="flex items-center justify-between py-1">
          <span class="text-xs">文案优化</span>
          <Switch
            v-model:checked="
              (material.enhancement as any).text_transformation_types
            "
          />
        </div>
        <div class="flex items-center justify-between py-1">
          <span class="text-xs">网站位置优化</span>
          <Switch
            v-model:checked="
              (material.enhancement as any).website_destination_optimization
            "
          />
        </div>

        <Divider style="margin: 8px 0" />

        <!-- 创意增强 -->
        <div class="mb-1 text-xs font-semibold text-gray-700">创意增强</div>

        <!-- 图片配置（filetype 为 image 或未知时展示） -->
        <template v-if="material.filetype !== 'video'">
          <div class="mb-1 text-xs text-gray-400">必要功能</div>
          <div
            v-for="item in imageRequired"
            :key="item.field"
            class="flex items-center justify-between py-0.5"
          >
            <span class="text-xs">{{ item.label }}</span>
            <Switch
              v-model:checked="(material.enhancement as any)[item.field]"
            />
          </div>
          <div class="mb-1 mt-2 text-xs text-gray-400">优化功能</div>
          <div
            v-for="item in imageOptional"
            :key="item.field"
            class="flex items-center justify-between py-0.5"
          >
            <span class="text-xs">{{ item.label }}</span>
            <Switch
              v-model:checked="(material.enhancement as any)[item.field]"
            />
          </div>
        </template>

        <!-- 视频配置 -->
        <template v-else>
          <div class="mb-1 text-xs text-gray-400">必要功能</div>
          <div
            v-for="item in videoRequired"
            :key="item.field"
            class="flex items-center justify-between py-0.5"
          >
            <span class="text-xs">{{ item.label }}</span>
            <Switch
              v-model:checked="(material.enhancement as any)[item.field]"
            />
          </div>
          <div class="mb-1 mt-2 text-xs text-gray-400">优化功能</div>
          <div
            v-for="item in videoOptional"
            :key="item.field"
            class="flex items-center justify-between py-0.5"
          >
            <span class="text-xs">{{ item.label }}</span>
            <Switch
              v-model:checked="(material.enhancement as any)[item.field]"
            />
          </div>
        </template>
      </div>
    </template>

    <Button style="width: 147px">更多配置 ▾</Button>
  </Popover>
</template>

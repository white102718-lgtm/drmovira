<template>
  <div>
    <div
      v-for="(section, sectionKey) in tagDescription"
      :key="sectionKey"
      style="margin-bottom: 8px"
    >
      <div style="font-weight: bold">{{ sectionKey }}</div>

      <!-- 元素分布与占比分析 -->
      <template
        v-if="sectionKey && sectionKey.toString() === '元素分布与占比分析'"
      >
        <div style="padding-left: 8px">
          <div
            v-for="(item, itemKey) in section"
            :key="itemKey"
            style="margin-bottom: 4px"
          >
            <div>{{ itemKey }}:</div>
            <div style="padding-left: 8px">
              <div v-if="item.位置">位置: {{ item.位置.join(', ') }}</div>
              <div v-if="item.占比">占比: {{ item.占比 }}</div>
              <div v-if="item.层级">层级: {{ item.层级 }}</div>
            </div>
          </div>
        </div>
      </template>

      <!-- 主色调与辅助色 -->
      <template
        v-else-if="sectionKey && sectionKey.toString() === '主色调与辅助色'"
      >
        <div style="padding-left: 8px">
          <div v-if="section.主色调">主色调: {{ section.主色调 }}</div>
          <div v-if="section.辅助色">
            辅助色:
            {{
              Array.isArray(section.辅助色)
                ? section.辅助色.join(', ')
                : section.辅助色
            }}
          </div>
        </div>
      </template>

      <!-- 行动号召 -->
      <template v-else-if="sectionKey && sectionKey.toString() === '行动号召'">
        <div style="padding-left: 8px">
          <div v-if="section.类型">
            类型:
            {{
              Array.isArray(section.类型) ? section.类型.join(', ') : section.类型
            }}
          </div>
          <div v-if="section.文字内容">
            文字内容:
            {{
              Array.isArray(section.文字内容)
                ? section.文字内容.join(', ')
                : section.文字内容
            }}
          </div>
        </div>
      </template>

      <!-- 文案内容 -->
      <template v-else-if="sectionKey && sectionKey.toString() === '文案内容'">
        <div style="padding-left: 8px">
          <div v-if="section.行动号召文案">
            行动号召文案: {{ section.行动号召文案 }}
          </div>
          <div v-if="section.游戏名称">
            游戏名称:
            {{
              Array.isArray(section.游戏名称)
                ? section.游戏名称.join(', ')
                : section.游戏名称
            }}
          </div>
          <div v-if="section.文案">文案: {{ section.文案 }}</div>
        </div>
      </template>

      <!-- 其他类型的字段 -->
      <template v-else>
        <div style="padding-left: 8px">
          <pre>{{ JSON.stringify(section, null, 2) }}</pre>
        </div>
      </template>
    </div>
  </div>
</template>

<script lang="ts" setup>
defineProps({
  tagDescription: {
    type: Object,
    required: true,
  },
});
</script> 
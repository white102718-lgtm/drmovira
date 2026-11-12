<template>
  <div class="vertical-launch">
    <section
      v-for="(tier, index) in tiers"
      :id="`launch-tier-${index}`"
      :key="tier.kind"
      :data-launch-section="tier.kind"
      class="launch-tier"
    >
      <header class="tier-heading">
        <div>
          <span class="tier-number">{{ index + 2 }}</span>
          <h3>{{ tier.title }}</h3>
          <span class="tier-count">{{ tier.rows.length }} 项配置</span>
        </div>
        <div class="tier-actions">
          <el-button :disabled="disabled || !tier.canAdd" @click="add(index)">{{
            tier.addLabel
          }}</el-button>
          <el-button :disabled="disabled || !tier.current" @click="copy(index)">{{
            index === activeTier ? '复制配置' : `复制${tier.title}`
          }}</el-button>
          <el-button
            :disabled="disabled || !tier.current"
            text
            type="danger"
            @click="remove(index)"
            >{{ index === activeTier ? '移除节点' : `删除${tier.title}` }}</el-button
          >
        </div>
      </header>
      <div v-if="tier.rows.length" class="tier-tabs" role="tablist" :aria-label="tier.title">
        <button
          v-for="(row, ri) in tier.rows"
          :key="row.local_id"
          type="button"
          role="tab"
          :aria-selected="tier.current?.local_id === row.local_id"
          :class="{ active: tier.current?.local_id === row.local_id }"
          @click="choose(index, row.local_id)"
        >
          {{ ('name' in row && row.name) || `${tier.title} ${ri + 1}` }}
          <small>×{{ row.copies }}</small>
        </button>
      </div>
      <LaunchNodeEditor
        v-if="tier.current"
        :ref="(value) => setEditor(index, value)"
        :model-value="modelValue"
        :local-id="tier.current.local_id"
        :asset-ids="assetIds"
        :objective="campaign?.objective"
        :disabled="disabled"
        :metric-read-allowed="metricReadAllowed"
        :metric-context-key="metricContextKey"
        @update:model-value="emit('update:modelValue', $event)"
        @browsing="emit('browsing', $event)"
      />
      <el-empty
        v-else
        :description="
          index === 0
            ? '新增一个系列，开始配置投放'
            : `先选择${index === 1 ? '系列' : '广告组'}，再${tier.addLabel}`
        "
        :image-size="42"
      />
    </section>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import type { CampaignConfig, AdSetConfig, AdConfig } from '@/api/orbit/launch'
import { cloneBranch, newCampaign, newAdSet, newAd } from '@/api/orbit/launch-form'
import LaunchNodeEditor from './LaunchNodeEditor.vue'
const props = withDefaults(
  defineProps<{
    modelValue: CampaignConfig[]
    disabled?: boolean
    metricReadAllowed?: boolean
    metricContextKey?: string
    assetIds?: string[]
  }>(),
  { disabled: false, metricReadAllowed: false, metricContextKey: '', assetIds: () => [] },
)
const emit = defineEmits<{
  'update:modelValue': [CampaignConfig[]]
  browsing: [boolean]
  'clone-branch': [Record<string, string>]
  'remove-branch': [string[]]
}>()
const ids = ref(['', '', '']),
  activeTier = ref(0)
const campaign = computed(
  () => props.modelValue.find((row) => row.local_id === ids.value[0]) ?? props.modelValue[0],
)
const group = computed(
  () =>
    campaign.value?.adsets.find((row) => row.local_id === ids.value[1]) ??
    campaign.value?.adsets[0],
)
const ad = computed(
  () => group.value?.ads.find((row) => row.local_id === ids.value[2]) ?? group.value?.ads[0],
)
const tiers = computed(() => [
  {
    kind: 'campaign',
    title: '广告系列',
    addLabel: '新增系列',
    rows: props.modelValue,
    current: campaign.value,
    canAdd: true,
  },
  {
    kind: 'adset',
    title: '广告组',
    addLabel: '新增广告组',
    rows: campaign.value?.adsets ?? [],
    current: group.value,
    canAdd: !!campaign.value,
  },
  {
    kind: 'ad',
    title: '广告',
    addLabel: '新增广告',
    rows: group.value?.ads ?? [],
    current: ad.value,
    canAdd: !!group.value,
  },
])
type Node = CampaignConfig | AdSetConfig | AdConfig
type Editor = { focusField(id: string, path: string[]): Promise<boolean> }
const editors: (Editor | undefined)[] = []
function setEditor(index: number, value: Element | ComponentPublicInstance | null) {
  editors[index] = value as unknown as Editor | undefined
}
function choose(index: number, id: string) {
  ids.value[index] = id
  activeTier.value = index
}
function touch() {
  emit('update:modelValue', [...props.modelValue])
}
function add(index: number) {
  if (props.disabled || !tiers.value[index].canAdd) return
  const node =
    index === 0 ? newCampaign() : index === 1 ? newAdSet(campaign.value?.objective) : newAd()
  if (index === 0) emit('update:modelValue', [...props.modelValue, node as CampaignConfig])
  else {
    ;(tiers.value[index].rows as Node[]).push(node)
    touch()
  }
  choose(index, node.local_id)
}
function copy(index: number) {
  const tier = tiers.value[index]
  if (props.disabled || !tier.current) return
  const node = cloneBranch(tier.current)
  const mapping: Record<string, string> = {}
  function visit(original: Node, cloned: Node) {
    mapping[original.local_id] = cloned.local_id
    if ('adsets' in original && 'adsets' in cloned)
      original.adsets.forEach((child, i) => visit(child, cloned.adsets[i]))
    if ('ads' in original && 'ads' in cloned)
      original.ads.forEach((child, i) => visit(child, cloned.ads[i]))
  }
  visit(tier.current, node)
  ;(tier.rows as Node[]).push(node)
  touch()
  emit('clone-branch', mapping)
  choose(index, node.local_id)
}
function remove(index: number) {
  const tier = tiers.value[index]
  if (props.disabled || !tier.current) return
  const removed: string[] = []
  function collect(node: Node) {
    removed.push(node.local_id)
    if ('adsets' in node) node.adsets.forEach(collect)
    if ('ads' in node) node.ads.forEach(collect)
  }
  collect(tier.current)
  tier.rows.splice(
    tier.rows.findIndex((row) => row.local_id === tier.current!.local_id),
    1,
  )
  ids.value[index] = ''
  touch()
  emit('remove-branch', removed)
}
async function focusField(id: string, path: string[]) {
  for (const c of props.modelValue) {
    let index = c.local_id === id ? 0 : -1
    let foundGroup: AdSetConfig | undefined, foundAd: AdConfig | undefined
    for (const g of c.adsets) {
      if (g.local_id === id) {
        index = 1
        foundGroup = g
        break
      }
      const a = g.ads.find((item) => item.local_id === id)
      if (a) {
        index = 2
        foundGroup = g
        foundAd = a
        break
      }
    }
    if (index < 0) continue
    ids.value = [c.local_id, foundGroup?.local_id ?? '', foundAd?.local_id ?? '']
    activeTier.value = index
    await nextTick()
    return (await editors[index]?.focusField(id, path)) ?? false
  }
  return false
}
defineExpose({ focusField })
</script>
<style scoped>
.vertical-launch {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.launch-tier {
  min-width: 0;
  padding: 24px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 14px;
  background: var(--el-bg-color);
  scroll-margin-top: 24px;
}
.tier-heading,
.tier-heading > div {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.tier-heading {
  justify-content: space-between;
  margin-bottom: 20px;
}
.tier-heading h3 {
  margin: 0;
  font-size: 17px;
}
.tier-number {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 9px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}
.tier-count {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.tier-tabs {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 16px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.tier-tabs button {
  flex: 0 0 auto;
  cursor: pointer;
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-regular);
  padding: 9px 16px;
  border-radius: 8px;
}
.tier-tabs button.active {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
}
.tier-tabs small {
  margin-left: 10px;
  opacity: 0.7;
}
@media (max-width: 700px) {
  .launch-tier {
    padding: 16px;
  }
  .tier-heading {
    gap: 16px;
  }
  .tier-actions {
    gap: 4px !important;
  }
  .tier-actions .el-button {
    margin-left: 0;
  }
}
</style>

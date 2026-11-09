<script setup lang="ts">
import type { RegionGroup } from '../types';

import { computed, ref, watch } from 'vue';

import { Select } from 'ant-design-vue';

// Props 定义
interface Props {
  modelValue: RegionGroup;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  'update:modelValue': [value: RegionGroup];
}>();

// 面板展开状态
const isExpanded = ref(props.modelValue.isExpanded ?? false);

// ===== 选项常量定义 =====

// 设备平台选项（第一个下拉框）- 对应 device_platforms 字段
const devicePlatformOptions = [
  { value: 'all', label: '所有设备（推荐）' },
  { value: 'mobile', label: '移动设备' },
  { value: 'desktop', label: '桌面设备' },
] as const;

// 操作系统模式选项（第二个下拉框）
const osModeOptions = [
  { value: 'all', label: '所有操作系统' },
  { value: 'android', label: '仅限 Android 设备' },
  { value: 'ios', label: '仅限 iOS 设备' },
] as const;

// Android 版本列表
const androidVersionOptions = [
  { value: '7.0', label: '7.0' },
  { value: '7.1', label: '7.1' },
  { value: '8.0', label: '8.0' },
  { value: '8.1', label: '8.1' },
  { value: '9.0', label: '9.0' },
  { value: '10.0', label: '10.0' },
  { value: '11.0', label: '11.0' },
  { value: '12.0', label: '12.0' },
  { value: '13.0', label: '13.0' },
  { value: '14.0', label: '14.0' },
  { value: '15.0', label: '15.0' },
  { value: '16.0', label: '16.0' },
] as const;

// iOS 版本列表
const iosVersionOptions = [
  { value: '11.0', label: '11.0' },
  { value: '11.1', label: '11.1' },
  { value: '11.2', label: '11.2' },
  { value: '11.3', label: '11.3' },
  { value: '11.4', label: '11.4' },
  { value: '12.0', label: '12.0' },
  { value: '12.1', label: '12.1' },
  { value: '12.2', label: '12.2' },
  { value: '12.3', label: '12.3' },
  { value: '12.4', label: '12.4' },
  { value: '12.5', label: '12.5' },
  { value: '13.0', label: '13.0' },
  { value: '13.1', label: '13.1' },
  { value: '13.2', label: '13.2' },
  { value: '13.3', label: '13.3' },
  { value: '13.4', label: '13.4' },
  { value: '13.5', label: '13.5' },
  { value: '13.6', label: '13.6' },
  { value: '13.7', label: '13.7' },
  { value: '14.0', label: '14.0' },
  { value: '14.1', label: '14.1' },
  { value: '14.2', label: '14.2' },
  { value: '14.3', label: '14.3' },
  { value: '14.4', label: '14.4' },
  { value: '14.5', label: '14.5' },
  { value: '14.6', label: '14.6' },
  { value: '14.7', label: '14.7' },
  { value: '14.8', label: '14.8' },
  { value: '15.0', label: '15.0' },
  { value: '15.1', label: '15.1' },
  { value: '15.2', label: '15.2' },
  { value: '15.3', label: '15.3' },
  { value: '15.4', label: '15.4' },
  { value: '15.5', label: '15.5' },
  { value: '15.6', label: '15.6' },
  { value: '15.7', label: '15.7' },
  { value: '15.8', label: '15.8' },
  { value: '16.0', label: '16.0' },
  { value: '16.1', label: '16.1' },
  { value: '16.2', label: '16.2' },
  { value: '16.3', label: '16.3' },
  { value: '16.4', label: '16.4' },
  { value: '16.5', label: '16.5' },
  { value: '16.6', label: '16.6' },
  { value: '16.7', label: '16.7' },
  { value: '16.8', label: '16.8' },
  { value: '17.0', label: '17.0' },
  { value: '17.1', label: '17.1' },
  { value: '17.2', label: '17.2' },
  { value: '17.3', label: '17.3' },
  { value: '17.4', label: '17.4' },
  { value: '17.5', label: '17.5' },
  { value: '17.6', label: '17.6' },
  { value: '17.7', label: '17.7' },
  { value: '18.0', label: '18.0' },
  { value: '18.1', label: '18.1' },
  { value: '18.2', label: '18.2' },
  { value: '18.3', label: '18.3' },
  { value: '18.4', label: '18.4' },
  { value: '18.5', label: '18.5' },
  { value: '18.6', label: '18.6' },
  { value: '18.7', label: '18.7' },
  { value: '26.0', label: '26.0' },
] as const;

// Android 设备类型
const androidDeviceTypes = [
  { value: 'Android_Smartphone', label: 'Android 智能手机（所有）' },
  { value: 'Android_Tablet', label: 'Android 平板（所有）' },
] as const;

// iOS 设备类型
const iosDeviceTypes = [
  { value: 'iPhone', label: 'iPhone（所有）' },
  { value: 'iPad', label: 'iPad（所有）' },
  { value: 'iPod', label: 'iPod（所有）' },
] as const;

// ===== 内部状态 =====

// 设备平台模式（第一个下拉框）: 'all' | 'mobile' | 'desktop'
const devicePlatformMode = ref<'all' | 'desktop' | 'mobile'>('all');

// 操作系统模式（第二个下拉框）: 'all' | 'android' | 'ios'
const osMode = ref<'all' | 'android' | 'ios'>('all');

// 操作系统版本
const osVersionMin = ref<string | undefined>(undefined);
const osVersionMax = ref<string | undefined>(undefined);

// ===== 计算属性 =====

// 根据当前操作系统模式返回版本选项
const currentOsVersionOptions = computed(() => {
  if (osMode.value === 'android') {
    return androidVersionOptions;
  } else if (osMode.value === 'ios') {
    return iosVersionOptions;
  }
  return [];
});

// 已选择的设备列表
const selectedDevices = computed(() => props.modelValue.user_device ?? []);

// 摘要文本
const summaryText = computed(() => {
  // 设备平台文本
  let deviceText = '所有设备';
  if (devicePlatformMode.value === 'mobile') {
    deviceText = '移动设备';
  } else if (devicePlatformMode.value === 'desktop') {
    deviceText = '桌面设备';
  }

  // 操作系统文本
  let osText = '';
  if (osMode.value === 'android') {
    osText = 'Android 操作系统';
  } else if (osMode.value === 'ios') {
    osText = 'iOS 操作系统';
  }

  return osText ? `${deviceText}和${osText}` : deviceText;
});

// ===== 方法 =====

// 更新父组件数据
function updateModelValue(updates: Partial<RegionGroup>) {
  emit('update:modelValue', { ...props.modelValue, ...updates });
}

// 获取设备标签显示文本
function getDeviceLabel(deviceValue: string): string {
  const allDevices = [...androidDeviceTypes, ...iosDeviceTypes];
  const device = allDevices.find((d) => d.value === deviceValue);
  return device ? device.label : deviceValue;
}

// 处理设备平台变更（第一个下拉框）
function handleDevicePlatformChange(value: unknown) {
  const mode = value as 'all' | 'desktop' | 'mobile';
  devicePlatformMode.value = mode;
  if (mode === 'all') {
    updateModelValue({ device_platforms: undefined });
  } else {
    updateModelValue({ device_platforms: [mode] });
  }
}

// 处理操作系统模式变更（第二个下拉框）
function handleOsModeChange(value: unknown) {
  const mode = value as 'all' | 'android' | 'ios';
  osMode.value = mode;
  switch (mode) {
    case 'all': {
      updateModelValue({
        user_os: undefined,
        user_device: undefined,
        user_os_version: undefined,
      });

      break;
    }
    case 'android': {
      updateModelValue({
        user_os: ['Android'],
        user_device: ['Android_Smartphone', 'Android_Tablet'],
        user_os_version: undefined,
      });

      break;
    }
    case 'ios': {
      updateModelValue({
        user_os: ['iOS'],
        user_device: ['iPhone', 'iPad', 'iPod'],
        user_os_version: undefined,
      });

      break;
    }
    // No default
  }
  // 重置版本选择
  osVersionMin.value = undefined;
  osVersionMax.value = undefined;
}

// 处理操作系统版本
function handleOsVersionChange() {
  if (osMode.value === 'all') {
    return;
  }
  const osType = osMode.value === 'android' ? 'Android' : 'iOS';

  if (osVersionMin.value && osVersionMax.value) {
    // 同时有最小和最大版本，格式：{OS}_ver_{min}_to_{max}
    const versionString = `${osType}_ver_${osVersionMin.value}_to_${osVersionMax.value}`;
    updateModelValue({
      user_os: [versionString] as any,
      user_os_version: undefined,
    });
  } else if (osVersionMin.value) {
    // 只有最小版本，格式：{OS}_ver_{version}_and_above
    const versionString = `${osType}_ver_${osVersionMin.value}_and_above`;
    updateModelValue({
      user_os: [versionString] as any,
      user_os_version: undefined,
    });
  } else {
    updateModelValue({
      user_os: [osType] as any,
      user_os_version: undefined,
    });
  }
}

// 移除设备
function removeDevice(device: string) {
  const currentDevices = selectedDevices.value.filter((d) => d !== device);
  updateModelValue({
    user_device: currentDevices.length > 0 ? currentDevices : undefined,
  });
}

// 监听 isExpanded 变化
watch(isExpanded, (newVal) => {
  updateModelValue({ isExpanded: newVal });
});

// 初始化：根据 props 设置内部状态
watch(
  () => props.modelValue,
  (newVal) => {
    if (newVal.isExpanded !== undefined) {
      isExpanded.value = newVal.isExpanded;
    }

    // 根据 device_platforms 设置设备平台模式
    if (
      newVal.device_platforms?.includes('mobile') &&
      newVal.device_platforms.length === 1
    ) {
      devicePlatformMode.value = 'mobile';
    } else if (
      newVal.device_platforms?.includes('desktop') &&
      newVal.device_platforms.length === 1
    ) {
      devicePlatformMode.value = 'desktop';
    } else {
      devicePlatformMode.value = 'all';
    }

    // 根据 user_os 设置操作系统模式和版本信息
    const userOs = newVal.user_os?.[0] || '';

    if (userOs.startsWith('Android')) {
      osMode.value = 'android';
      // 解析版本字符串：支持 {OS}_ver_{min}_to_{max} 和 {OS}_ver_{version}_and_above 两种格式
      const matchTo = userOs.match(/^Android_ver_(.+)_to_(.+)$/);
      const matchAbove = userOs.match(/^Android_ver_(.+)_and_above$/);
      if (matchTo) {
        osVersionMin.value = matchTo[1];
        osVersionMax.value = matchTo[2];
      } else if (matchAbove) {
        osVersionMin.value = matchAbove[1];
        osVersionMax.value = undefined;
      } else {
        osVersionMin.value = undefined;
        osVersionMax.value = undefined;
      }
    } else if (userOs.startsWith('iOS')) {
      osMode.value = 'ios';
      // 解析版本字符串：支持 {OS}_ver_{min}_to_{max} 和 {OS}_ver_{version}_and_above 两种格式
      const matchTo = userOs.match(/^iOS_ver_(.+)_to_(.+)$/);
      const matchAbove = userOs.match(/^iOS_ver_(.+)_and_above$/);
      if (matchTo) {
        osVersionMin.value = matchTo[1];
        osVersionMax.value = matchTo[2];
      } else if (matchAbove) {
        osVersionMin.value = matchAbove[1];
        osVersionMax.value = undefined;
      } else {
        osVersionMin.value = undefined;
        osVersionMax.value = undefined;
      }
    } else {
      osMode.value = 'all';
      osVersionMin.value = undefined;
      osVersionMax.value = undefined;
    }
  },
  { immediate: true, deep: true },
);
</script>

<template>
  <div class="device-os-panel rounded-sm border border-gray-200 p-2">
    <!-- 收起状态 -->
    <div
      v-if="!isExpanded"
      class="collapsed-view flex cursor-pointer items-center justify-between rounded-[4px] transition-colors hover:border-blue-400"
      @click="isExpanded = true"
    >
      <div class="flex flex-col">
        <span class="font-medium text-gray-800">设备和操作系统</span>
        <span class="text-sm text-gray-500">{{ summaryText }}</span>
      </div>
      <span
        class="icon-[ant-design--edit-outlined] cursor-pointer text-lg text-blue-500"
      ></span>
    </div>

    <!-- 展开状态 -->
    <div v-else class="expanded-view rounded-lg">
      <!-- 面板头部 -->
      <div class="mb-4 flex items-center justify-between">
        <span class="font-medium text-gray-800">设备和操作系统</span>
        <span
          class="icon-[ant-design--up-outlined] cursor-pointer text-gray-400 hover:text-gray-600"
          @click="isExpanded = false"
        ></span>
      </div>

      <!-- 设备平台选择（mobile/desktop） -->
      <div class="mb-4">
        <Select
          :value="devicePlatformMode"
          style="width: 100%"
          @change="handleDevicePlatformChange"
        >
          <Select.Option
            v-for="opt in devicePlatformOptions"
            :key="opt.value"
            :value="opt.value"
          >
            {{ opt.label }}
          </Select.Option>
        </Select>
      </div>

      <!-- 操作系统选择（Android/iOS） -->
      <div class="mb-4">
        <Select
          :value="osMode"
          style="width: 100%"
          @change="handleOsModeChange"
        >
          <Select.Option
            v-for="opt in osModeOptions"
            :key="opt.value"
            :value="opt.value"
          >
            {{ opt.label }}
          </Select.Option>
        </Select>
      </div>

      <!-- 仅当选择特定操作系统时显示详细配置 -->
      <template v-if="osMode !== 'all'">
        <!-- 包含的设备 -->
        <div class="mb-4">
          <div class="mb-2 text-sm font-medium text-gray-700">包含的设备</div>
          <div class="space-y-2">
            <!-- 已选择的设备标签 -->
            <div
              v-for="device in selectedDevices"
              :key="device"
              class="flex items-center justify-between rounded bg-gray-50 p-2"
            >
              <span>{{ getDeviceLabel(device) }}</span>
              <span
                class="icon-[ant-design--close-outlined] cursor-pointer text-gray-400 hover:text-gray-600"
                @click="removeDevice(device)"
              ></span>
            </div>
          </div>
        </div>

        <!-- 操作系统版本 -->
        <div class="mb-4">
          <div class="mb-2 text-sm font-medium text-gray-700">操作系统版本</div>
          <div class="flex items-center gap-4">
            <div class="flex items-center gap-2">
              <span class="text-sm text-gray-600">最低</span>
              <Select
                v-model:value="osVersionMin"
                style="width: 180px"
                allow-clear
                placeholder="无"
                @change="handleOsVersionChange"
              >
                <Select.Option
                  v-for="ver in currentOsVersionOptions"
                  :key="ver.value"
                  :value="ver.value"
                >
                  {{ ver.label }}
                </Select.Option>
              </Select>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-sm text-gray-600">最高</span>
              <Select
                v-model:value="osVersionMax"
                style="width: 180px"
                allow-clear
                placeholder="无"
                @change="handleOsVersionChange"
              >
                <Select.Option
                  v-for="ver in currentOsVersionOptions"
                  :key="ver.value"
                  :value="ver.value"
                >
                  {{ ver.label }}
                </Select.Option>
              </Select>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.device-os-panel {
  width: 530px;
  margin-top: 8px;
  margin-bottom: 8px;
}
</style>

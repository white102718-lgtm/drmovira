<script lang="ts" setup>
import { computed, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Input,
  message,
  Modal,
  Popover,
  Select,
  Switch,
  Textarea,
  Tooltip,
} from 'ant-design-vue';

import 'emoji-picker-element';

const STORAGE_KEY = 'chat_tool_templates';

interface Props {
  modelValue: boolean;
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void;
  (e: 'confirm', data: ChatToolData): void;
}

interface ChatQuestion {
  autoReply: string;
  question: string;
}

interface ChatToolData {
  greeting: string;
  greetingType: string;
  questions: ChatQuestion[];
  reengagementEnabled: boolean;
  reengagementText: string;
  templateName: string;
}

interface ChatToolTemplate {
  data: ChatToolData;
  id: string;
  name: string;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const modalOpen = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});

const greetingType = ref('TEXT');
const greeting = ref('你好!请问有什么可以帮助你的?');
const customerActionType = ref('FAQ');
const questions = ref<ChatQuestion[]>([
  { question: '你们提供哪些服务？', autoReply: '' },
  { question: '你们的营业时间是什么时候？', autoReply: '' },
  { question: '如何联系你们？', autoReply: '' },
]);
const reengagementEnabled = ref(true);
const reengagementText = ref('您好！我们想了解一下，您有什么疑问吗？');

const greetingEmojiOpen = ref(false);
const questionEmojiOpenMap = ref<Record<number, boolean>>({});
const reengagementEmojiOpen = ref(false);

const greetingTypeOptions = [{ label: '纯文字', value: 'TEXT' }];
const customerActionTypeOptions = [{ label: '常见问题', value: 'FAQ' }];

const showSaveTemplateModal = ref(false);
const newTemplateName = ref('');
const showTemplateListModal = ref(false);
const templates = ref<ChatToolTemplate[]>([]);

function loadTemplates() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    templates.value = raw ? JSON.parse(raw) : [];
  } catch {
    templates.value = [];
  }
}

function saveTemplatesToStorage() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(templates.value));
}

function openSaveTemplateModal() {
  newTemplateName.value = '';
  showSaveTemplateModal.value = true;
}

function confirmSaveTemplate() {
  const name = newTemplateName.value.trim();
  if (!name) {
    message.warning('请输入模板名称');
    return;
  }
  loadTemplates();
  const id = Date.now().toString();
  const tpl: ChatToolTemplate = {
    id,
    name,
    data: {
      greetingType: greetingType.value,
      greeting: greeting.value,
      questions: JSON.parse(JSON.stringify(questions.value)),
      reengagementEnabled: reengagementEnabled.value,
      reengagementText: reengagementText.value,
      templateName: name,
    },
  };
  templates.value.push(tpl);
  saveTemplatesToStorage();
  message.success(`模板"${name}"已保存`);
  showSaveTemplateModal.value = false;
}

function openTemplateListModal() {
  loadTemplates();
  showTemplateListModal.value = true;
}

function applyTemplate(tpl: ChatToolTemplate) {
  greetingType.value = tpl.data.greetingType;
  greeting.value = tpl.data.greeting;
  questions.value = JSON.parse(JSON.stringify(tpl.data.questions));
  reengagementEnabled.value = tpl.data.reengagementEnabled;
  reengagementText.value = tpl.data.reengagementText;
  confirmTemplateName.value = tpl.name;
  showTemplateListModal.value = false;
  message.success(`已应用模板"${tpl.name}"`);
}

function deleteTemplate(id: string) {
  templates.value = templates.value.filter((t) => t.id !== id);
  saveTemplatesToStorage();
}

function onGreetingEmojiClick(event: Event) {
  const unicode = (event as CustomEvent<{ unicode: string }>).detail?.unicode;
  if (unicode) greeting.value += unicode;
  greetingEmojiOpen.value = false;
}

function onQuestionEmojiClick(event: Event, index: number) {
  const unicode = (event as CustomEvent<{ unicode: string }>).detail?.unicode;
  if (unicode) questions.value[index]!.autoReply += unicode;
  questionEmojiOpenMap.value = {
    ...questionEmojiOpenMap.value,
    [index]: false,
  };
}

function onReengagementEmojiClick(event: Event) {
  const unicode = (event as CustomEvent<{ unicode: string }>).detail?.unicode;
  if (unicode) reengagementText.value += unicode;
  reengagementEmojiOpen.value = false;
}

function addQuestion() {
  if (questions.value.length >= 5) return;
  questions.value.push({ question: '', autoReply: '' });
}

function removeQuestion(index: number) {
  if (questions.value.length <= 1) return;
  questions.value.splice(index, 1);
}

function getDefaultTemplateName() {
  const d = new Date();
  return `开始对话 ${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

const confirmTemplateName = ref(getDefaultTemplateName());

function handleConfirm() {
  const name = confirmTemplateName.value.trim();
  if (!name) {
    message.warning('请输入模板名称');
    return;
  }
  loadTemplates();
  const id = Date.now().toString();
  const tpl: ChatToolTemplate = {
    id,
    name,
    data: {
      greetingType: greetingType.value,
      greeting: greeting.value,
      questions: JSON.parse(JSON.stringify(questions.value)),
      reengagementEnabled: reengagementEnabled.value,
      reengagementText: reengagementText.value,
      templateName: name,
    },
  };
  templates.value.push(tpl);
  saveTemplatesToStorage();
  message.success(`模板"${name}"已保存`);
  emit('confirm', {
    greetingType: greetingType.value,
    greeting: greeting.value,
    questions: questions.value,
    reengagementEnabled: reengagementEnabled.value,
    reengagementText: reengagementText.value,
    templateName: name,
  });
  handleCancel();
}

function handleCancel() {
  confirmTemplateName.value = getDefaultTemplateName();
  modalOpen.value = false;
}
</script>

<template>
  <div>
    <Modal v-model:open="modalOpen" title="聊天工具" width="900px">
      <template #title>
        <div class="flex items-center justify-between pr-8">
          <span>聊天工具</span>
          <div class="flex gap-2">
            <Button @click="openTemplateListModal">应用模板</Button>
            <Button type="primary" @click="openSaveTemplateModal"
              >存为模板</Button
            >
          </div>
        </div>
      </template>

      <div class="max-h-[70vh] space-y-6 overflow-y-auto py-4 pr-1">
        <div>
          <div class="font-semibold text-gray-800">问候语</div>
          <div class="my-2 flex items-center gap-2">
            <p class="text-sm text-gray-500">欢迎轻触广告的用户加入对话。</p>
            <Select v-model:value="greetingType" style="width: 90px">
              <Select.Option
                v-for="opt in greetingTypeOptions"
                :key="opt.value"
                :value="opt.value"
              >
                {{ opt.label }}
              </Select.Option>
            </Select>
          </div>
          <div class="relative">
            <Textarea
              v-model:value="greeting"
              :rows="2"
              placeholder="请输入问候语"
              :maxlength="200"
              style="padding-bottom: 28px"
            />
            <Popover
              v-model:open="greetingEmojiOpen"
              trigger="click"
              placement="bottomRight"
            >
              <template #content>
                <div @click.stop>
                  <component
                    :is="'emoji-picker'"
                    @emoji-click="onGreetingEmojiClick"
                  />
                </div>
              </template>
              <span
                class="absolute bottom-2 right-2 cursor-pointer select-none text-base"
                @click.stop="greetingEmojiOpen = !greetingEmojiOpen"
              >
                <IconifyIcon aria-hidden="true" icon="lucide:smile" />
              </span>
            </Popover>
          </div>
        </div>

        <div>
          <div class="mb-1 flex items-center gap-1 font-semibold text-gray-800">
            顾客操作
            <Tooltip
              title="建议不超过5条顾客能够轻触的问题或回复，或使用按钮把用户送往你的网站。"
            >
              <span
                class="icon-[ant-design--info-circle-outlined] cursor-pointer text-gray-400"
              ></span>
            </Tooltip>
          </div>
          <Select
            v-model:value="customerActionType"
            style="width: 140px"
            class="mb-4"
          >
            <Select.Option
              v-for="opt in customerActionTypeOptions"
              :key="opt.value"
              :value="opt.value"
            >
              {{ opt.label }}
            </Select.Option>
          </Select>

          <div class="grid grid-cols-2 gap-3">
            <div
              v-for="(q, index) in questions"
              :key="index"
              class="relative rounded border border-gray-200 p-3"
            >
              <div class="mb-2 flex items-center justify-between">
                <span class="text-sm font-medium text-gray-700"
                  >问题 #{{ index + 1 }}</span
                >
                <span
                  v-if="questions.length > 1"
                  class="icon-[ant-design--close-outlined] cursor-pointer text-gray-400 hover:text-gray-600"
                  @click="removeQuestion(index)"
                ></span>
              </div>
              <div class="mb-3">
                <div
                  class="ant-input-affix-wrapper flex items-center rounded border border-gray-300 px-3 py-1 focus-within:border-blue-500"
                >
                  <input
                    v-model="q.question"
                    maxlength="80"
                    placeholder="请输入问题"
                    class="flex-1 border-none outline-none"
                  />
                  <span class="ml-1 shrink-0 text-xs text-gray-400">
                    {{ q.question.length }}/80
                  </span>
                </div>
              </div>
              <div class="mb-1 text-xs text-gray-500">自动回复 · 选填</div>
              <div class="relative">
                <Textarea
                  v-model:value="q.autoReply"
                  :rows="2"
                  placeholder="请输入"
                  style="padding-bottom: 28px"
                />
                <Popover
                  v-model:open="questionEmojiOpenMap[index]"
                  trigger="click"
                  placement="bottomRight"
                >
                  <template #content>
                    <div @click.stop>
                      <component
                        :is="'emoji-picker'"
                        @emoji-click="
                          (e: Event) => onQuestionEmojiClick(e, index)
                        "
                      />
                    </div>
                  </template>
                  <span
                    class="absolute bottom-2 right-2 cursor-pointer select-none text-base"
                    @click.stop="
                      questionEmojiOpenMap[index] = !questionEmojiOpenMap[index]
                    "
                  >
                    <IconifyIcon aria-hidden="true" icon="lucide:smile" />
                  </span>
                </Popover>
              </div>
            </div>
          </div>

          <Button v-if="questions.length < 5" class="mt-3" @click="addQuestion">
            + 添加问题
          </Button>
        </div>

        <div class="rounded border border-gray-200 p-4">
          <div class="mb-1 flex items-center justify-between">
            <div>
              <div class="font-semibold text-gray-800">后续跟进消息</div>
              <div class="mt-1 text-sm text-gray-500">
                跟进轻触了你的广告，但在大约 1 天后没有发消息的高意向潜在客户。
              </div>
            </div>
            <Switch
              :checked="reengagementEnabled"
              @change="(val: boolean) => (reengagementEnabled = val)"
            />
          </div>
          <div v-if="reengagementEnabled" class="mt-3">
            <div class="relative">
              <Textarea
                v-model:value="reengagementText"
                :rows="2"
                placeholder="请输入后续跟进消息"
                :maxlength="200"
                style="padding-bottom: 28px"
              />
              <Popover
                v-model:open="reengagementEmojiOpen"
                trigger="click"
                placement="bottomRight"
              >
                <template #content>
                  <div @click.stop>
                    <component
                      :is="'emoji-picker'"
                      @emoji-click="onReengagementEmojiClick"
                    />
                  </div>
                </template>
                <span
                  class="absolute bottom-2 right-2 cursor-pointer select-none text-base"
                  @click.stop="reengagementEmojiOpen = !reengagementEmojiOpen"
                >
                  <IconifyIcon aria-hidden="true" icon="lucide:smile" />
                </span>
              </Popover>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-between gap-3">
          <div class="flex flex-1 items-center gap-2">
            <span class="shrink-0 text-sm text-gray-600">模板名称</span>
            <Input
              v-model:value="confirmTemplateName"
              placeholder="请输入"
              style="max-width: 200px"
            />
          </div>
          <div class="flex gap-3">
            <Button class="rounded-md" @click="handleCancel">取消</Button>
            <Button type="primary" class="rounded-md" @click="handleConfirm">
              确认
            </Button>
          </div>
        </div>
      </template>
    </Modal>

    <Modal
      v-model="showSaveTemplateModal"
      title="存为模板"
      width="400px"
      @ok="confirmSaveTemplate"
      ok-text="保存"
      cancel-text="取消"
    >
      <div class="py-2">
        <div class="mb-1 text-sm text-gray-600">模板名称</div>
        <Input
          v-model:value="newTemplateName"
          placeholder="请输入模板名称"
          @pressEnter="confirmSaveTemplate"
        />
      </div>
    </Modal>

    <Modal
      v-model="showTemplateListModal"
      title="选择聊天模板"
      width="500px"
      :footer="null"
    >
      <div class="py-2">
        <div
          v-if="templates.length === 0"
          class="py-8 text-center text-gray-400"
        >
          暂无模板，请先存为模板
        </div>
        <div
          v-else
          class="max-h-[var(--adpulse-popup-table-height)] space-y-2 overflow-y-auto"
        >
          <div
            v-for="tpl in templates"
            :key="tpl.id"
            class="flex items-center justify-between rounded border border-gray-200 px-3 py-2 hover:border-blue-400 hover:bg-blue-50"
          >
            <span class="flex-1 truncate text-sm text-gray-700">{{
              tpl.name
            }}</span>
            <div class="flex items-center gap-2">
              <Button type="primary" @click="applyTemplate(tpl)">应用</Button>
              <Button danger @click="deleteTemplate(tpl.id)">删除</Button>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  </div>
</template>

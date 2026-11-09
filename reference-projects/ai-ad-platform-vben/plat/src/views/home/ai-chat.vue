<script lang="ts" setup>
import type {
  AgentBlock,
  AgentConversation,
  AgentProgress,
  AgentUpload,
  StreamHandlers,
} from '#/api/agent';
import type { ThinkingStep } from '#/components/agent/AgentThinking.vue';

import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { preferences } from '@vben/preferences';

import { message } from 'ant-design-vue';
import Modal from 'ant-design-vue/es/modal';

import {
  deleteConversation,
  fetchMessages,
  fetchRun,
  listConversations,
  streamChat,
  streamChoice,
  streamConfirm,
  streamFollow,
  uploadAgentFile,
} from '#/api/agent';
import AgentBlocks from '#/components/agent/AgentBlocks.vue';
import AgentThinking from '#/components/agent/AgentThinking.vue';
import Button from 'ant-design-vue/es/button';
import Tooltip from 'ant-design-vue/es/tooltip';
import FeishuQrLogin from '#/views/_core/authentication/feishu-qr-login.vue';

interface ChatMessage {
  blocks: AgentBlock[];
  id: string;
  role: 'assistant' | 'user';
}

// 网页先只做查询。订时报代码已接好，后台上线 bind 接口后把开关改为 true。
const WEB_SCHEDULE_ENABLED =
  import.meta.env.VITE_GLOB_AGENT_WEB_SCHEDULE === 'true';

const ALL_QUICK_PROMPTS = [
  {
    description: '按项目汇总昨天的消耗、注册和首充',
    icon: 'lucide:chart-column',
    prompt: 'EE666 昨天消耗总结',
    title: '项目昨天消耗',
  },
  {
    description: '把定时时报发到你的飞书私聊',
    icon: 'lucide:bell',
    prompt: '帮我订 EE666 时报',
    title: '订时报',
  },
  {
    description: '看某个调度点的定版时报看板',
    icon: 'lucide:clock',
    prompt: 'F9 昨天 21 点时报',
    title: '定点时报',
  },
  {
    description: '后台已经算好归因，比自己翻数字准',
    icon: 'lucide:triangle-alert',
    prompt: 'F9 昨天消耗为什么掉了',
    title: '掉量归因',
  },
  {
    description: '列出项目下面在跑的代理线',
    icon: 'lucide:git-branch',
    prompt: 'EE666 有哪些代理线',
    title: '代理线清单',
  },
];

const quickPrompts = WEB_SCHEDULE_ENABLED
  ? ALL_QUICK_PROMPTS
  : ALL_QUICK_PROMPTS.filter((item) => item.title !== '订时报');

const ACTIVE_KEY = 'adpulse-agent-active-conv';
const PENDING_PROMPT_KEY = 'adpulse-agent-pending-prompt';
const BIND_RETURN_KEY = 'adpulse-agent-bind-return';

const logo = preferences.logo.source;

const prompt = ref('');
const sending = ref(false);
const steps = ref<ThinkingStep[]>([]);
const startedAt = ref(0);
// 正在生成的那条助手消息。思考链画在它内部的最上面，块接在链下面。
const streamingIndex = ref(-1);
const loadingHistory = ref(false);
const messages = ref<ChatMessage[]>([]);
const conversations = ref<AgentConversation[]>([]);
const activeId = ref('');
const bindOpen = ref(false);
const scroller = ref<HTMLElement | null>(null);
const content = ref<HTMLElement | null>(null);
let controller: AbortController | null = null;

const activeTitle = computed(
  () =>
    conversations.value.find((item) => item.id === activeId.value)?.title ??
    '新对话',
);
const pendingFile = ref<AgentUpload | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const uploading = ref(false);
const ACCEPT =
  '.xlsx,.xlsm,.csv,.txt,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,text/plain';

const canSend = computed(
  () =>
    (prompt.value.trim().length > 0 || pendingFile.value !== null) &&
    !sending.value &&
    !uploading.value,
);
const isEmpty = computed(() => messages.value.length === 0);

// 往上翻着看历史时不要把人拽回底部；回到底部附近就重新跟随
let pinned = true;

function stick() {
  const el = scroller.value;
  if (el) el.scrollTop = el.scrollHeight;
}

function onScroll() {
  const el = scroller.value;
  if (el) pinned = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
}

function scrollToBottom() {
  pinned = true;
  void nextTick(stick);
}

function lastUserText() {
  for (let index = messages.value.length - 1; index >= 0; index -= 1) {
    const item = messages.value[index];
    if (item?.role !== 'user') continue;
    const text = item.blocks.find((block) => block.type === 'text')?.content;
    if (typeof text === 'string' && text.trim()) return text.trim();
  }
  return '';
}

function rememberBindPending() {
  const text = lastUserText();
  if (!text) return;
  sessionStorage.setItem(
    PENDING_PROMPT_KEY,
    JSON.stringify({ conversationId: activeId.value, text }),
  );
  sessionStorage.setItem(BIND_RETURN_KEY, '/home/ai-chat');
}

function takePendingPrompt(): null | { conversationId?: string; text: string } {
  const raw = sessionStorage.getItem(PENDING_PROMPT_KEY);
  sessionStorage.removeItem(PENDING_PROMPT_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as {
      conversationId?: string;
      text?: string;
    };
    return parsed?.text
      ? { conversationId: parsed.conversationId, text: parsed.text }
      : null;
  } catch {
    return null;
  }
}

function openBindModal() {
  rememberBindPending();
  bindOpen.value = true;
}

function remember(id: string) {
  activeId.value = id;
  if (id) sessionStorage.setItem(ACTIVE_KEY, id);
  else sessionStorage.removeItem(ACTIVE_KEY);
}

function toMessages(
  items: { blocks?: AgentBlock[]; id: string; role: 'assistant' | 'user' }[],
) {
  return items.map((item) => ({
    blocks: item.blocks ?? [],
    id: item.id,
    role: item.role,
  }));
}

async function refreshConversations() {
  try {
    conversations.value = await listConversations();
  } catch (error: any) {
    message.error({
      content: error?.message || '会话列表加载失败',
      key: 'agent-conversations',
    });
  }
}

function createConversation() {
  controller?.abort();
  remember('');
  messages.value = [];
  prompt.value = '';
  pendingFile.value = null;
  sending.value = false;
  steps.value = [];
  streamingIndex.value = -1;
}

async function selectConversation(conversation: AgentConversation) {
  if (conversation.id === activeId.value) return;
  controller?.abort();
  await hydrate(conversation.id);
}

async function hydrate(conversationId: string) {
  remember(conversationId);
  prompt.value = '';
  messages.value = [];
  loadingHistory.value = true;
  try {
    const items = await fetchMessages(conversationId);
    messages.value = toMessages(items);
    scrollToBottom();
    const run = await fetchRun(conversationId);
    if (run.running) {
      await followIfRunning(conversationId, run);
    } else {
      // 答案可能刚好在两次请求中间写入
      messages.value = toMessages(await fetchMessages(conversationId));
    }
  } catch (error: any) {
    message.error(error?.message || '历史消息加载失败');
  } finally {
    loadingHistory.value = false;
  }
}

async function followIfRunning(
  conversationId: string,
  known?: { started_at?: number },
) {
  sending.value = true;
  steps.value = [];
  startedAt.value = known?.started_at || Date.now();
  controller = new AbortController();
  const last = messages.value[messages.value.length - 1];
  const index =
    last?.role === 'assistant'
      ? messages.value.length - 1
      : pushMessage('assistant', []);
  streamingIndex.value = index;
  const append = (blocks: AgentBlock[]) => {
    messages.value[index]!.blocks.push(...blocks);
    scrollToBottom();
  };
  try {
    await streamFollow(
      conversationId,
      {
        onBlocks: append,
        onDone: remember,
        onProgress: foldProgress,
      },
      controller.signal,
    );
    const items = await fetchMessages(conversationId);
    messages.value = toMessages(items);
    await refreshConversations();
  } catch (error: any) {
    if (error?.name !== 'AbortError') {
      append([{ content: error?.message || '请求失败', type: 'error' }]);
    }
  } finally {
    sending.value = false;
    steps.value = [];
    streamingIndex.value = -1;
    controller = null;
  }
}

async function removeConversation(conversation: AgentConversation) {
  try {
    await deleteConversation(conversation.id);
    if (conversation.id === activeId.value) createConversation();
    await refreshConversations();
  } catch (error: any) {
    message.error(error?.message || '删除失败');
  }
}

function pushMessage(role: 'assistant' | 'user', blocks: AgentBlock[]) {
  messages.value.push({
    blocks,
    id: `${role}-${Date.now()}-${Math.random()}`,
    role,
  });
  scrollToBottom();
  return messages.value.length - 1;
}

/** 阶段挂到最近那行还在跑的同名工具下面。 */
function runningTool(name: string) {
  return [...steps.value]
    .reverse()
    .find(
      (step) =>
        step.kind === 'tool' && step.name === name && step.state === 'running',
    )?.id;
}

/**
 * 把 SSE 的 progress 事件折成一条链。
 *
 * start 落一行，update 回填条数，done/error 回填状态和耗时——所以要从后往前找
 * 那行还在 running 的：同一个工具一轮里可能被调用多次。
 */
function foldProgress(event: AgentProgress) {
  if (event.state === 'start') {
    const label = event.label ?? (event.kind === 'llm' ? '思考' : '处理数据');
    steps.value.push({
      doing: event.doing ?? `正在${label}`,
      id: `${event.kind}-${event.name ?? ''}-${steps.value.length}`,
      kind: event.kind,
      label,
      name: event.name,
      parentId: event.parent ? runningTool(event.parent) : undefined,
      startedAt: Date.now(),
      state: 'running',
      total: event.total,
    });
    scrollToBottom();
    return;
  }
  const hit = [...steps.value]
    .reverse()
    .find(
      (step) =>
        step.state === 'running' &&
        step.kind === event.kind &&
        step.name === event.name,
    );
  if (!hit) return;
  if (event.state === 'update') {
    hit.done = event.done;
    if (event.total) hit.total = event.total;
    return;
  }
  hit.state = event.state === 'error' ? 'error' : 'done';
  hit.elapsedMs = event.elapsed_ms;
  if (event.error) hit.error = event.error;
}

async function run(
  start: (handlers: StreamHandlers, signal: AbortSignal) => Promise<void>,
) {
  sending.value = true;
  steps.value = [];
  startedAt.value = Date.now();
  controller = new AbortController();
  // 先占位。中途出的图也属于这一轮，必须落在思考链下面，
  // 所以这条消息要在开跑时就存在，不能等第一个块到了才建。
  const index = pushMessage('assistant', []);
  streamingIndex.value = index;

  const append = (blocks: AgentBlock[]) => {
    // 通过响应式数组取回代理对象再改，否则视图不会更新
    messages.value[index]!.blocks.push(...blocks);
    scrollToBottom();
    if (blocks.some((block) => block.type === 'feishu_bind')) {
      openBindModal();
    }
  };

  try {
    await start(
      {
        onBlocks: append,
        onDone: (conversationId) => {
          if (conversationId) remember(conversationId);
        },
        onProgress: foldProgress,
      },
      controller.signal,
    );
    await refreshConversations();
  } catch (error: any) {
    if (error?.status === 409) throw error;
    if (error?.name !== 'AbortError') {
      append([{ content: error?.message || '请求失败', type: 'error' }]);
    }
  } finally {
    sending.value = false;
    steps.value = [];
    streamingIndex.value = -1;
    // 一个块都没来（被中止、或者切了会话），别留一个空气泡
    if (messages.value[index]?.blocks.length === 0) {
      messages.value.splice(index, 1);
    }
    controller = null;
  }
}

function sendMessage() {
  const content = prompt.value.trim();
  const file = pendingFile.value;
  if ((!content && !file) || sending.value || uploading.value) return;
  prompt.value = '';
  pendingFile.value = null;
  const userBlocks: AgentBlock[] = [];
  if (content) userBlocks.push({ content, type: 'text' });
  if (file) {
    userBlocks.push({
      filename: file.filename,
      size: file.size,
      type: 'file',
      url: file.url,
    });
  }
  const userIndex = pushMessage('user', userBlocks);
  void run((handlers, signal) =>
    streamChat(
      {
        conversationId: activeId.value,
        fileIds: file ? [file.file_id] : [],
        text: content,
      },
      handlers,
      signal,
    ),
  ).catch(async (error: any) => {
    if (error?.status !== 409) return;
    messages.value.splice(userIndex, 1);
    if (activeId.value) {
      const run = await fetchRun(activeId.value);
      if (run.running) await followIfRunning(activeId.value, run);
      else messages.value = toMessages(await fetchMessages(activeId.value));
    }
  });
}

function chooseOption(optionId: string, label: string) {
  if (sending.value || !activeId.value) return;
  pushMessage('user', [{ content: label, type: 'text' }]);
  void run((handlers, signal) =>
    streamChoice(
      { conversationId: activeId.value, optionId },
      handlers,
      signal,
    ),
  );
}

function onChoose(messageIndex: number, optionId: string) {
  const blocks = messages.value[messageIndex]?.blocks ?? [];
  let label = optionId;
  for (const block of blocks) {
    if (block.type !== 'choice') continue;
    const hit = block.options?.find((option: any) => option.id === optionId);
    if (hit) {
      label = hit.label;
      break;
    }
  }
  chooseOption(optionId, label);
}

function onConfirm(_messageIndex: number, previewId: string, accept: boolean) {
  if (sending.value || !activeId.value || !previewId) return;
  pushMessage('user', [{ content: accept ? '确认' : '取消', type: 'text' }]);
  void run((handlers, signal) =>
    streamConfirm(
      { accept, conversationId: activeId.value, previewId },
      handlers,
      signal,
    ),
  );
}

function onBind() {
  openBindModal();
}

function useQuickPrompt(value: string) {
  prompt.value = value;
}

function handleEnter(event: KeyboardEvent) {
  if (!event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

function openFilePicker() {
  if (sending.value || uploading.value) return;
  fileInput.value?.click();
}

async function onPickFile(event: Event) {
  const input = event.target instanceof HTMLInputElement ? event.target : null;
  const file = input?.files?.[0];
  if (input) input.value = '';
  if (!file) return;
  if (file.size > 8 * 1024 * 1024) {
    message.error('文件超过 8MB，请删减后再传。');
    return;
  }
  uploading.value = true;
  try {
    pendingFile.value = await uploadAgentFile(file);
  } catch (error: any) {
    pendingFile.value = null;
    message.error(error?.message || '表格上传失败');
  } finally {
    uploading.value = false;
  }
}

function clearPendingFile() {
  pendingFile.value = null;
}

function resizeComposer(event?: Event) {
  const el =
    event?.target instanceof HTMLTextAreaElement
      ? event.target
      : (document.querySelector(
          '#ai-chat-input',
        ) as HTMLTextAreaElement | null);
  if (!el) return;
  const styles = getComputedStyle(el);
  const lineHeight = Number.parseFloat(styles.lineHeight) || 20;
  const padding =
    Number.parseFloat(styles.paddingTop) +
    Number.parseFloat(styles.paddingBottom);
  const maxHeight = lineHeight * 3 + padding;
  el.style.height = 'auto';
  el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
}

watch(prompt, () => {
  void nextTick(() => resizeComposer());
});

// 成效图是异步取回来的，图片落地时高度才变，那已经在 nextTick 之后了；
// 思考链每加一步也会变高。所以靠观察内容高度来跟随，而不是只在推消息时滚一次。
let heightWatcher: ResizeObserver | undefined;

onMounted(() => {
  heightWatcher = new ResizeObserver(() => {
    if (pinned) stick();
  });
  if (content.value) heightWatcher.observe(content.value);
  void (async () => {
    await refreshConversations();
    const pending = takePendingPrompt();
    const saved = pending?.conversationId || sessionStorage.getItem(ACTIVE_KEY);
    const hit =
      conversations.value.find((item) => item.id === saved) ??
      conversations.value.find((item) => item.running);
    if (hit) await hydrate(hit.id);
    if (pending?.text) {
      prompt.value = pending.text;
      sendMessage();
    }
  })();
});

// 空状态和消息列表是两个分支，列表要等第一条消息才挂上来
watch(content, (el) => {
  heightWatcher?.disconnect();
  if (el) heightWatcher?.observe(el);
});

onBeforeUnmount(() => {
  heightWatcher?.disconnect();
  controller?.abort();
});
</script>

<template>
  <Page auto-content-height class="ai-chat-page">
    <!-- auto-content-height 已经把可用高度算准（扣掉了顶栏和标签页），
         这里必须跟着它铺满。用 100dvh 自己减一个猜的数会多撑出一截空白。 -->
    <div
      class="border-border bg-card flex h-full w-full overflow-hidden rounded-xl border"
    >
      <aside
        class="border-border bg-muted/40 hidden w-64 shrink-0 flex-col border-r p-3 lg:flex"
      >
        <Button class="w-full justify-start" @click="createConversation">
          <IconifyIcon aria-hidden="true" class="mr-1.5" icon="lucide:plus" />
          新建对话
        </Button>

        <nav class="mt-6 min-h-0 flex-1 overflow-y-auto" aria-label="对话历史">
          <p class="text-muted-foreground mb-2 px-2 text-xs font-medium">
            最近
          </p>
          <p
            v-if="conversations.length === 0"
            class="text-muted-foreground px-2 text-xs leading-5"
          >
            还没有对话记录
          </p>
          <div class="space-y-1">
            <div
              v-for="conversation in conversations"
              :key="conversation.id"
              class="group flex min-h-10 w-full items-center gap-1 rounded-lg px-1 transition"
              :class="
                activeId === conversation.id ? 'bg-muted' : 'hover:bg-muted/70'
              "
            >
              <button
                type="button"
                class="flex min-w-0 flex-1 items-center gap-2 px-1.5 py-2 text-left text-sm"
                :class="
                  activeId === conversation.id
                    ? 'text-foreground font-medium'
                    : 'text-muted-foreground group-hover:text-foreground'
                "
                @click="selectConversation(conversation)"
              >
                <IconifyIcon
                  v-if="conversation.running"
                  icon="lucide:loader-circle"
                  class="text-muted-foreground shrink-0 animate-spin"
                />
                <IconifyIcon
                  v-else
                  icon="lucide:message-square"
                  class="shrink-0"
                />
                <span class="truncate">{{ conversation.title }}</span>
              </button>
              <button
                type="button"
                aria-label="删除对话"
                class="text-muted-foreground hover:bg-muted hover:text-destructive shrink-0 rounded p-1 opacity-0 transition focus-visible:opacity-100 group-hover:opacity-100"
                @click="removeConversation(conversation)"
              >
                <IconifyIcon icon="lucide:trash-2" class="text-sm" />
              </button>
            </div>
          </div>
        </nav>

        <div
          class="border-border text-muted-foreground mt-4 border-t px-2 pt-3 text-xs leading-5"
        >
          网页版只做查询。订时报、推群、建广告请在飞书里找机器人。
        </div>
      </aside>

      <section class="bg-card relative flex min-w-0 flex-1 flex-col">
        <header
          class="border-border flex h-14 shrink-0 items-center justify-between border-b px-4 sm:px-6"
        >
          <div
            class="text-foreground flex min-w-0 items-center gap-2 text-sm font-medium"
          >
            <img
              :src="logo"
              alt=""
              aria-hidden="true"
              class="h-7 w-7 rounded-md"
            />
            <span class="truncate">{{ activeTitle }}</span>
          </div>
          <Tooltip title="新建对话">
            <Button
              class="!flex lg:!hidden"
              type="text"
              aria-label="新建对话"
              @click="createConversation"
            >
              <IconifyIcon icon="lucide:square-pen" />
            </Button>
          </Tooltip>
        </header>

        <div
          v-if="isEmpty && !loadingHistory"
          class="flex flex-1 items-center justify-center px-5 pb-48 pt-10"
        >
          <div class="w-full max-w-3xl">
            <div class="text-center">
              <img
                :src="logo"
                alt=""
                aria-hidden="true"
                class="mx-auto h-12 w-12 rounded-xl"
              />
              <h1
                class="text-foreground mb-2 mt-5 text-2xl font-semibold tracking-tight sm:text-3xl"
              >
                今天想查什么？
              </h1>
              <p class="text-muted-foreground m-0 text-sm leading-6">
                消耗、时报、掉量归因、代理线和投手名单，用大白话问就行。
              </p>
            </div>

            <div class="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <button
                v-for="item in quickPrompts"
                :key="item.title"
                type="button"
                class="border-border bg-card hover:border-foreground/30 hover:bg-muted group min-h-24 rounded-xl border p-4 text-left transition-colors"
                @click="useQuickPrompt(item.prompt)"
              >
                <span class="flex items-start gap-3">
                  <span
                    class="text-muted-foreground group-hover:text-foreground mt-0.5"
                  >
                    <IconifyIcon :icon="item.icon" class="text-lg" />
                  </span>
                  <span>
                    <span class="text-foreground block text-sm font-medium">
                      {{ item.title }}
                    </span>
                    <span
                      class="text-muted-foreground mt-1 block text-xs leading-5"
                    >
                      {{ item.description }}
                    </span>
                  </span>
                </span>
              </button>
            </div>
          </div>
        </div>

        <div
          v-else
          ref="scroller"
          class="min-h-0 flex-1 overflow-y-auto"
          @scroll.passive="onScroll"
        >
          <div
            ref="content"
            class="mx-auto w-full max-w-3xl space-y-7 px-5 pb-48 pt-7 sm:px-8"
          >
            <div
              v-if="loadingHistory"
              class="text-muted-foreground flex items-center gap-2 text-sm"
            >
              <IconifyIcon icon="lucide:loader-circle" class="animate-spin" />
              正在加载历史消息…
            </div>
            <article
              v-for="(item, index) in messages"
              :key="item.id"
              class="flex gap-3"
              :class="item.role === 'user' ? 'justify-end' : 'justify-start'"
            >
              <img
                v-if="item.role === 'assistant'"
                :src="logo"
                alt=""
                aria-hidden="true"
                class="h-8 w-8 shrink-0 rounded-md"
              />
              <div
                class="min-w-0 max-w-[85%] rounded-2xl"
                :class="
                  item.role === 'user'
                    ? 'bg-muted text-foreground px-4 py-3'
                    : // 助手气泡没有底色，铺满不影响文字观感，但思考链和图表
                      // 才不会被按内容挤窄
                      'text-foreground w-full'
                "
              >
                <AgentThinking
                  v-if="sending && index === streamingIndex"
                  class="mb-3"
                  :started-at="startedAt"
                  :steps="steps"
                />
                <AgentBlocks
                  :blocks="item.blocks"
                  :disabled="sending || index !== messages.length - 1"
                  @bind="onBind"
                  @choose="(optionId) => onChoose(index, optionId)"
                  @confirm="
                    (previewId, accept) => onConfirm(index, previewId, accept)
                  "
                />
              </div>
            </article>
          </div>
        </div>

        <form
          class="border-border bg-card/95 pointer-events-none absolute inset-x-0 bottom-0 z-10 border-t px-4 pb-4 pt-4 sm:px-6 sm:pb-5"
          @submit.prevent="sendMessage"
        >
          <div class="pointer-events-auto mx-auto w-full max-w-3xl">
            <input
              ref="fileInput"
              type="file"
              class="hidden"
              :accept="ACCEPT"
              @change="onPickFile"
            />
            <div
              v-if="pendingFile || uploading"
              class="border-border bg-muted mb-2 flex items-center gap-2 rounded-2xl border px-3 py-2"
            >
              <IconifyIcon
                :icon="
                  uploading
                    ? 'lucide:loader-circle'
                    : 'lucide:file-spreadsheet'
                "
                :class="
                  uploading
                    ? 'text-muted-foreground animate-spin'
                    : 'text-foreground'
                "
              />
              <span class="text-foreground min-w-0 flex-1 truncate text-sm">
                {{ uploading ? '正在上传表格…' : pendingFile?.filename }}
              </span>
              <button
                v-if="pendingFile && !uploading"
                type="button"
                class="text-muted-foreground hover:bg-accent hover:text-foreground rounded p-1"
                aria-label="移除附件"
                @click="clearPendingFile"
              >
                <IconifyIcon icon="lucide:x" />
              </button>
            </div>
            <div
              class="border-border bg-card flex items-center gap-1 rounded-[28px] border py-1.5 pl-1.5 pr-1.5"
            >
              <Tooltip title="上传表格，回填消耗">
                <span class="inline-flex">
                  <button
                    type="button"
                    :disabled="sending || uploading"
                    aria-label="添加表格"
                    class="text-muted-foreground hover:bg-muted hover:text-foreground flex h-10 w-10 shrink-0 items-center justify-center rounded-full disabled:opacity-40"
                    @click="openFilePicker"
                  >
                    <IconifyIcon icon="lucide:plus" class="text-xl" />
                  </button>
                </span>
              </Tooltip>
              <label class="sr-only" for="ai-chat-input"
                >输入要咨询的问题</label
              >
              <textarea
                id="ai-chat-input"
                v-model="prompt"
                class="text-foreground placeholder:text-muted-foreground max-h-[4.75rem] min-h-10 flex-1 resize-none overflow-hidden border-0 bg-transparent px-1 py-2 text-sm leading-5 outline-none ring-0 focus:border-0 focus:outline-none focus:ring-0 disabled:cursor-not-allowed"
                :maxlength="500"
                :disabled="sending"
                placeholder="例如：EE666 昨天消耗，或上传表格让我回填"
                rows="1"
                @input="resizeComposer"
                @keydown.enter="handleEnter"
              ></textarea>
              <button
                type="submit"
                class="disabled:bg-muted disabled:text-muted-foreground flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors"
                :class="
                  canSend
                    ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                    : 'bg-muted text-muted-foreground'
                "
                :aria-label="sending ? '正在发送' : '发送消息'"
                :disabled="!canSend"
              >
                <IconifyIcon
                  v-if="sending"
                  icon="lucide:loader-circle"
                  class="animate-spin"
                />
                <IconifyIcon v-else icon="lucide:arrow-up" />
              </button>
            </div>
            <p
              class="text-muted-foreground mb-0 mt-2.5 text-center text-xs leading-5"
            >
              数字以卡片和图为准。结论仅供参考，请核对重要业务信息。
            </p>
          </div>
        </form>
      </section>
    </div>
    <Modal
      v-model:open="bindOpen"
      title="绑定飞书"
      :footer="null"
      destroy-on-close
    >
      <p class="text-muted-foreground mb-4 mt-0 text-sm leading-6">
        订时报会发到你的飞书私聊。请先在飞书打开 AdPulse
        机器人，否则第一次可能发不过去。
      </p>
      <FeishuQrLogin purpose="bind" />
    </Modal>
  </Page>
</template>

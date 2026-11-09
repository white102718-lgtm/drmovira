<script lang="ts" setup>
import type {
  ApplicationComment,
  ResourceApplication,
} from '#/store/resource-applications';

import { computed, ref, useId } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Button, Input, message } from 'ant-design-vue';

import { useResourceApplicationStore } from '#/store/resource-applications';

const props = defineProps<{
  actorName: string;
  actorRole: string;
  allowComment?: boolean;
  application: ResourceApplication;
  submitCommentRequest?: (content: string) => Promise<ApplicationComment>;
}>();

const emit = defineEmits<{
  commentAdded: [comment: ApplicationComment];
}>();

const COMMENT_MAX_LENGTH = 500;

const applicationStore = useResourceApplicationStore();
const instanceId = useId().replaceAll(':', '');
const commentsHeadingId = `application-comments-heading-${instanceId}`;
const publisherHeadingId = `application-comment-publisher-heading-${instanceId}`;
const commentInputId = `application-comment-${instanceId}`;
const commentCountId = `application-comment-count-${instanceId}`;
const commentText = ref('');
const submitting = ref(false);

const canComment = computed(
  () =>
    props.allowComment ??
    applicationStore.isParticipant(props.application.id, props.actorName),
);

const unreadCommentCount = computed(() =>
  applicationStore.unreadCommentCount(props.application.id, props.actorName),
);

async function submitComment() {
  const content = commentText.value.trim();
  if (!content) {
    message.warning('请输入评论内容');
    return;
  }
  submitting.value = true;
  try {
    if (props.submitCommentRequest) {
      emit('commentAdded', await props.submitCommentRequest(content));
      commentText.value = '';
      message.success('评论已发布');
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 180));
    const success = applicationStore.addComment(
      props.application.id,
      props.actorName,
      props.actorRole,
      content,
    );
    if (!success && !props.allowComment) {
      message.warning('只有申请人、审批人、抄送人和节点参与人可以评论');
      return;
    }
    if (!success) {
      // 正式后端申请尚未进入本地 Store，由页面读模型接收新评论并立即回显。
      emit('commentAdded', {
        actor: props.actorName,
        actorRole: props.actorRole,
        at: new Date().toLocaleString('zh-CN', { hour12: false }),
        content,
        id: `COMMENT-${props.application.id}-${Date.now()}`,
        readBy: [props.actorName],
      });
    }
    commentText.value = '';
    message.success('评论已发布');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '评论发布失败');
  } finally {
    submitting.value = false;
  }
}

function markCommentsRead() {
  applicationStore.markCommentsRead(props.application.id, props.actorName);
}
</script>

<template>
  <section :aria-labelledby="commentsHeadingId">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3
        :id="commentsHeadingId"
        class="m-0 text-sm font-semibold text-slate-900"
      >
        流程评论
      </h3>
      <div class="flex items-center gap-2 text-xs text-slate-500">
        <span>{{ application.comments.length }} 条讨论</span>
        <Button
          v-if="unreadCommentCount > 0"
          size="small"
          type="link"
          @click="markCommentsRead"
        >
          {{ unreadCommentCount }} 条未读，标记已读
        </Button>
      </div>
    </div>

    <div
      v-if="application.comments.length > 0"
      class="mt-3 max-h-72 space-y-3 overflow-y-auto pr-1"
    >
      <article
        v-for="comment in application.comments"
        :key="comment.id"
        class="rounded-xl border border-slate-200 bg-white p-3"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex min-w-0 items-center gap-2">
            <span
              class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-600"
            >
              <IconifyIcon icon="lucide:message-circle" />
            </span>
            <div class="min-w-0">
              <p class="m-0 truncate text-sm font-medium text-slate-800">
                {{ comment.actor }}
              </p>
              <p class="mb-0 mt-0.5 text-xs text-slate-500">
                {{ comment.actorRole }}
              </p>
            </div>
          </div>
          <time class="text-xs text-slate-400">{{ comment.at }}</time>
        </div>
        <p
          class="mb-0 mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700"
        >
          {{ comment.content }}
        </p>
      </article>
    </div>
    <div
      v-else
      class="mt-3 rounded-xl border border-dashed border-slate-200 p-5 text-center text-sm text-slate-500"
    >
      暂无评论，流程参与人可在此补充信息。
    </div>
  </section>

  <section :aria-labelledby="publisherHeadingId">
    <h3
      :id="publisherHeadingId"
      class="m-0 text-sm font-semibold text-slate-900"
    >
      发布评论
    </h3>
    <div v-if="canComment" class="mt-3 rounded-xl bg-slate-50 p-3">
      <label
        :for="commentInputId"
        class="mb-2 block text-sm font-medium text-slate-700"
      >
        以 {{ actorName }} · {{ actorRole }} 发表评论
      </label>
      <div class="comment-publisher-row">
        <div class="comment-input-wrap min-w-0">
          <Input.TextArea
            :id="commentInputId"
            v-model:value="commentText"
            :aria-describedby="commentCountId"
            :maxlength="COMMENT_MAX_LENGTH"
            :rows="3"
            placeholder="补充问题、说明或节点协作信息"
          />
          <span
            :id="commentCountId"
            class="comment-count text-xs text-slate-400"
          >
            <span class="sr-only">已输入</span>
            {{ commentText.length }}/{{ COMMENT_MAX_LENGTH }}
            <span class="sr-only">字</span>
          </span>
        </div>
        <Button
          aria-label="发布评论"
          class="comment-submit"
          type="primary"
          :loading="submitting"
          @click="submitComment"
        >
          <IconifyIcon aria-hidden="true" icon="lucide:send" />
          发布
        </Button>
      </div>
    </div>
    <p v-else class="mb-0 mt-3 text-sm text-slate-500">
      当前身份不是该流程参与人，仅可查看流程评论。
    </p>
  </section>
</template>

<style scoped>
.comment-publisher-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: end;
}

.comment-input-wrap {
  position: relative;
  display: flex;
}

.comment-count {
  position: absolute;
  right: 12px;
  bottom: 6px;
  line-height: 18px;
  font-variant-numeric: tabular-nums;
  pointer-events: none;
}

.comment-submit {
  justify-self: end;
}
</style>

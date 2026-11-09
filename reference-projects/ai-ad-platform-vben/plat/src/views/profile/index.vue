<script lang="ts" setup>
import type {
  AuthUserInfo,
  UserProfile,
  UserProfileUpdateRequest,
} from '#/api';
import type { UploadProps } from 'ant-design-vue';

import { onBeforeUnmount, onMounted, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';
import {
  Avatar,
  Button,
  Form,
  FormItem,
  Input,
  InputPassword,
  Modal,
  Spin,
  Upload,
  message,
} from 'ant-design-vue';

import {
  changeMyPassword,
  getMyProfile,
  updateMyProfile,
  uploadProfileAvatar,
} from '#/api';
import { useAuthStore } from '#/store';

const authStore = useAuthStore();
const loading = ref(false);
const fetching = ref(true);
const avatarPreview = ref('');
const uploadingAvatar = ref(false);
const passwordModalOpen = ref(false);
const passwordLoading = ref(false);
const hasPassword = ref(true);
let localAvatarObjectUrl = '';

const readonlyInfo = reactive({
  username: '',
  phone: '',
  department: '',
  roles: [] as string[],
});
const form = reactive<UserProfileUpdateRequest>({
  displayName: '',
  englishNickname: '',
  realName: '',
  email: '',
  avatarUrl: '',
});
const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
});

// 标签列按最长可见标签计算，并预留必填标识、中文字体字宽差异和标签与控件的间距，避免窄列裁切文字。
const profileFormLabels = [
  '当前头像',
  '登录账号',
  '手机号',
  '主部门',
  '角色',
  '显示名称',
  '真实姓名',
  '英文昵称',
  '邮箱',
] as const;
const profileFormLabelWidth = `${
  Math.max(...profileFormLabels.map((label) => [...label].length)) * 16 + 32
}px`;

function fillForm(info: UserProfile, resolvedAvatar = '') {
  // 兼容旧接口：只有后端明确返回未设置密码时才隐藏旧密码。
  hasPassword.value = info.hasPassword !== false;
  readonlyInfo.username = info.username ?? '';
  readonlyInfo.phone = info.phone ?? '';
  readonlyInfo.department = info.department ?? '';
  readonlyInfo.roles = info.roles ?? [];
  form.displayName = info.displayName ?? '';
  form.englishNickname = info.englishNickname ?? '';
  form.realName = info.realName ?? '';
  // 个人资料必须使用 /users/me 返回的 email，不能从会话展示字段推断。
  form.email = info.email ?? '';
  form.avatarUrl = info.avatarUrl ?? '';
  avatarPreview.value = resolvedAvatar;
}

async function loadProfile() {
  const [profile, authInfo] = await Promise.all([
    getMyProfile(),
    authStore.fetchUserInfo(),
  ]);
  fillForm(profile, (authInfo as AuthUserInfo).avatar ?? '');
}

const beforeAvatarUpload: UploadProps['beforeUpload'] = async (file) => {
  uploadingAvatar.value = true;
  try {
    if (
      !['image/gif', 'image/jpeg', 'image/png', 'image/webp'].includes(
        file.type,
      )
    ) {
      throw new Error('仅支持 JPG、PNG、WebP 或 GIF 图片');
    }
    if (file.size > 5 * 1024 * 1024) {
      throw new Error('头像图片不能超过 5MB');
    }
    form.avatarUrl = await uploadProfileAvatar(file as File);
    if (localAvatarObjectUrl) URL.revokeObjectURL(localAvatarObjectUrl);
    localAvatarObjectUrl = URL.createObjectURL(file as File);
    avatarPreview.value = localAvatarObjectUrl;
    message.success('头像上传成功，请保存修改');
  } catch (error) {
    message.error(
      error instanceof Error && error.message
        ? `头像上传失败：${error.message}`
        : '头像上传失败，请稍后重试',
    );
  } finally {
    uploadingAvatar.value = false;
  }
  return Upload.LIST_IGNORE;
};

function removeAvatar() {
  form.avatarUrl = '';
  avatarPreview.value = '';
}

onBeforeUnmount(() => {
  if (localAvatarObjectUrl) URL.revokeObjectURL(localAvatarObjectUrl);
});

onMounted(async () => {
  try {
    await loadProfile();
  } finally {
    fetching.value = false;
  }
});

async function handleSave() {
  if (!form.displayName.trim()) {
    message.error('请输入显示名称');
    return;
  }
  loading.value = true;
  try {
    const profile = await updateMyProfile({
      ...form,
      displayName: form.displayName.trim(),
      email: form.email?.trim() || undefined,
      englishNickname: form.englishNickname?.trim() || undefined,
      realName: form.realName?.trim() || undefined,
    });
    const authInfo = (await authStore.fetchUserInfo()) as AuthUserInfo;
    fillForm(profile, authInfo.avatar ?? '');
    message.success('个人资料已保存');
  } finally {
    loading.value = false;
  }
}

function openPasswordModal() {
  passwordForm.oldPassword = '';
  passwordForm.newPassword = '';
  passwordForm.confirmPassword = '';
  passwordModalOpen.value = true;
}

async function handleChangePassword() {
  if (passwordLoading.value) return;
  if (hasPassword.value && !passwordForm.oldPassword) {
    message.error('请输入旧密码');
    return;
  }
  if (
    passwordForm.newPassword.length < 8 ||
    passwordForm.newPassword.length > 72
  ) {
    message.error('新密码长度必须为 8–72 位');
    return;
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    message.error('新密码与确认密码不一致');
    return;
  }

  passwordLoading.value = true;
  try {
    await changeMyPassword({
      newPassword: passwordForm.newPassword,
      oldPassword: hasPassword.value ? passwordForm.oldPassword : undefined,
    });
    passwordModalOpen.value = false;
    message.success('密码已修改，请重新登录');
    await authStore.logout(true);
  } finally {
    passwordLoading.value = false;
  }
}
</script>

<template>
  <Page
    description="查看账号归属信息，维护个人资料与登录密码。"
    title="个人信息"
  >
    <template #extra>
      <Button :disabled="fetching" @click="openPasswordModal">修改密码</Button>
    </template>
    <div class="mx-auto max-w-3xl px-4 py-8">
      <Spin :spinning="fetching" class="rounded-lg">
        <div class="bg-card rounded-lg border p-6 shadow-sm">
          <Form
            class="profile-form"
            layout="horizontal"
            :wrapper-col="{ flex: '1' }"
            :colon="false"
            :style="{ '--adpulse-form-label-width': profileFormLabelWidth }"
          >
            <div class="text-muted-foreground mb-1 text-xs font-semibold">
              头像
            </div>
            <div class="mb-5 border-b" />
            <FormItem label="当前头像">
              <div class="flex items-center gap-4">
                <Avatar :src="avatarPreview || undefined" :size="88">
                  {{ form.displayName.slice(0, 1) || '用' }}
                </Avatar>
                <div class="flex flex-col items-start gap-2">
                  <Upload
                    accept="image/jpeg,image/png,image/webp,image/gif"
                    :before-upload="beforeAvatarUpload"
                    :show-upload-list="false"
                  >
                    <Button :loading="uploadingAvatar">选择并上传头像</Button>
                  </Upload>
                  <Button
                    v-if="form.avatarUrl"
                    type="link"
                    danger
                    class="p-0"
                    @click="removeAvatar"
                  >
                    移除头像
                  </Button>
                  <span class="text-xs text-gray-400">
                    支持 JPG、PNG、WebP、GIF，最大 5MB
                  </span>
                </div>
              </div>
            </FormItem>

            <div class="text-muted-foreground mb-1 mt-6 text-xs font-semibold">
              账号信息
            </div>
            <div class="mb-5 border-b" />
            <FormItem label="登录账号"
              ><Input
                :value="readonlyInfo.username || '-'"
                disabled
                class="max-w-md"
            /></FormItem>
            <FormItem label="手机号"
              ><Input
                :value="readonlyInfo.phone || '-'"
                disabled
                class="max-w-md"
            /></FormItem>
            <FormItem label="主部门"
              ><Input
                :value="readonlyInfo.department || '-'"
                disabled
                class="max-w-md"
            /></FormItem>
            <FormItem label="角色"
              ><Input
                :value="readonlyInfo.roles.join('、') || '-'"
                disabled
                class="max-w-md"
            /></FormItem>

            <div class="text-muted-foreground mb-1 mt-6 text-xs font-semibold">
              基本资料
            </div>
            <div class="mb-5 border-b" />
            <FormItem label="显示名称" required
              ><Input
                v-model:value="form.displayName"
                :maxlength="100"
                class="max-w-md"
            /></FormItem>
            <FormItem label="真实姓名"
              ><Input
                v-model:value="form.realName"
                :maxlength="100"
                class="max-w-md"
            /></FormItem>
            <FormItem label="英文昵称"
              ><Input
                v-model:value="form.englishNickname"
                :maxlength="64"
                class="max-w-md"
            /></FormItem>
            <FormItem label="邮箱"
              ><Input
                v-model:value="form.email"
                type="email"
                :maxlength="128"
                class="max-w-md"
            /></FormItem>
            <div class="mt-6 flex justify-end">
              <Button
                type="primary"
                :loading="loading"
                :disabled="uploadingAvatar"
                @click="handleSave"
                >保存修改</Button
              >
            </div>
          </Form>
        </div>
      </Spin>
    </div>

    <Modal
      v-model:open="passwordModalOpen"
      title="修改密码"
      ok-text="确认修改"
      cancel-text="取消"
      :confirm-loading="passwordLoading"
      @ok="handleChangePassword"
    >
      <Form layout="vertical" :colon="false">
        <FormItem v-if="hasPassword" label="旧密码" required>
          <InputPassword
            v-model:value="passwordForm.oldPassword"
            autocomplete="current-password"
            placeholder="请输入旧密码"
          />
        </FormItem>
        <FormItem label="新密码" required>
          <InputPassword
            v-model:value="passwordForm.newPassword"
            autocomplete="new-password"
            placeholder="请输入 8–72 位新密码"
          />
        </FormItem>
        <FormItem label="确认新密码" required>
          <InputPassword
            v-model:value="passwordForm.confirmPassword"
            autocomplete="new-password"
            placeholder="请再次输入新密码"
            @press-enter="handleChangePassword"
          />
        </FormItem>
      </Form>
    </Modal>
  </Page>
</template>

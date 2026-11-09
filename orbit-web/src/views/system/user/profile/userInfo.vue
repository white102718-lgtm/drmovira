<template>
  <el-form
    ref="userRef"
    class="profile-user-form"
    :model="form"
    :rules="rules"
    label-width="80px"
    :disabled="saving"
  >
    <el-form-item label="用户昵称" prop="nickName">
      <el-input v-model="form.nickName" />
    </el-form-item>
    <el-form-item label="手机号码" prop="phonenumber">
      <el-input v-model="form.phonenumber" placeholder="支持国际区号及分隔符" />
    </el-form-item>
    <el-form-item label="邮箱" prop="email">
      <el-input v-model="form.email" />
    </el-form-item>
    <el-form-item label="性别">
      <el-radio-group v-model="form.sex">
        <el-radio value="0">男</el-radio>
        <el-radio value="1">女</el-radio>
      </el-radio-group>
    </el-form-item>
    <el-form-item>
      <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      <el-button type="danger" @click="close">关闭</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup>
import { updateUserProfile } from '@/api/system/user'

const props = defineProps({
  user: {
    type: Object,
  },
})

const { proxy } = getCurrentInstance()

const form = ref({})
const saving = ref(false)

/** 与人员字段统一按NFC后的Unicode码点计数；不能由HTML maxlength把50个表情截成25个。 */
function lengthRule(maximum, label) {
  return (_rule, value, callback) => {
    const text = String(value ?? '')
      .normalize('NFC')
      .trim()
    if (Array.from(text).length > maximum || /[\p{Cc}\p{Cf}\p{Cs}]/u.test(text)) {
      callback(new Error(`${label}最多${maximum}个字符，不能包含控制字符`))
    } else callback()
  }
}
const rules = ref({
  nickName: [{ validator: lengthRule(50, '昵称'), trigger: ['blur', 'change'] }],
  email: [
    { required: true, message: '邮箱地址不能为空', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱地址', trigger: ['blur', 'change'] },
    { validator: lengthRule(254, '邮箱'), trigger: ['blur', 'change'] },
  ],
  phonenumber: [{ validator: lengthRule(32, '联系方式'), trigger: ['blur', 'change'] }],
})

/** 提交按钮 */
function submit() {
  if (saving.value) return
  for (const field of ['nickName', 'email', 'phonenumber']) {
    form.value[field] = String(form.value[field] ?? '')
      .normalize('NFC')
      .trim()
  }
  proxy.$refs.userRef.validate((valid) => {
    if (valid) {
      saving.value = true
      updateUserProfile(form.value)
        .then(() => {
          proxy.$modal.msgSuccess('修改成功')
          props.user.phonenumber = form.value.phonenumber
          props.user.email = form.value.email
          props.user.nickName = form.value.nickName
          proxy.$refs.userRef.clearValidate()
        })
        .catch(() => {
          // 统一请求层已经展示错误；保留当前输入供用户核对重试。
        })
        .finally(() => {
          saving.value = false
        })
    }
  })
}

/** 关闭按钮 */
function close() {
  proxy.$tab.closePage()
}

// 回显当前登录用户信息
watch(
  () => props.user,
  (user) => {
    if (user) {
      form.value = {
        nickName: user.nickName,
        phonenumber: user.phonenumber,
        email: user.email,
        sex: user.sex,
      }
    }
  },
  { immediate: true },
)
</script>

<style scoped>
/* 长字段错误随表单内容换行，避免手机上覆盖下一个输入框或扩宽页面。 */
.profile-user-form :deep(.el-form-item__error) {
  position: static;
  max-width: 100%;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
</style>

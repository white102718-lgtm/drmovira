<template>
  <div class="app-container tree-sidebar-manage-wrap">
    <tree-panel
      title="组织机构"
      :tree-data="deptOptions"
      search-placeholder="请输入部门名称"
      storage-key="dept-sidebar-width"
      :defaultExpandAll="true"
      @node-click="handleNodeClick"
      @refresh="getDeptTree"
      ref="deptTreeRef"
    />
    <div class="tree-sidebar-content">
      <div class="content-inner">
        <el-form
          :model="queryParams"
          ref="queryRef"
          :inline="true"
          v-show="showSearch"
          label-width="68px"
        >
          <el-form-item label="用户名称" prop="userName">
            <el-input
              v-model="queryParams.userName"
              placeholder="请输入用户名称"
              clearable
              style="width: 240px"
              @keyup.enter="handleQuery"
            />
          </el-form-item>
          <el-form-item label="手机号码" prop="phonenumber">
            <el-input
              v-model="queryParams.phonenumber"
              placeholder="请输入手机号码"
              clearable
              style="width: 240px"
              @keyup.enter="handleQuery"
            />
          </el-form-item>
          <el-form-item label="状态" prop="status">
            <el-select
              v-model="queryParams.status"
              placeholder="用户状态"
              clearable
              style="width: 240px"
            >
              <el-option
                v-for="dict in sys_normal_disable"
                :key="dict.value"
                :label="dict.label"
                :value="dict.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="创建时间" style="width: 308px">
            <el-date-picker
              v-model="dateRange"
              value-format="YYYY-MM-DD"
              type="daterange"
              range-separator="-"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
            ></el-date-picker>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
            <el-button icon="Refresh" @click="resetQuery">重置</el-button>
          </el-form-item>
        </el-form>

        <el-row :gutter="10" class="mb8">
          <el-col :span="1.5">
            <el-button
              type="primary"
              plain
              icon="Plus"
              @click="handleAdd"
              v-hasPermi="['system:user:add']"
              >新增</el-button
            >
          </el-col>
          <el-col :span="1.5">
            <el-button
              type="success"
              plain
              icon="Edit"
              :disabled="single"
              @click="handleUpdate"
              v-hasPermi="['system:user:edit']"
              >修改</el-button
            >
          </el-col>
          <el-col :span="1.5">
            <el-button
              type="danger"
              plain
              icon="Delete"
              :disabled="multiple"
              @click="handleDelete"
              v-hasPermi="['system:user:remove']"
              >删除</el-button
            >
          </el-col>
          <el-col :span="1.5">
            <el-button
              type="info"
              plain
              icon="Upload"
              @click="handleImport"
              v-hasPermi="['system:user:import']"
              >导入</el-button
            >
          </el-col>
          <el-col :span="1.5">
            <el-button
              type="warning"
              plain
              icon="Download"
              @click="handleExport"
              v-hasPermi="['system:user:export']"
              >导出</el-button
            >
          </el-col>
          <right-toolbar
            v-model:showSearch="showSearch"
            @queryTable="getList"
            :columns="columns"
            storageKey="xxxxxxxx"
          ></right-toolbar>
        </el-row>

        <el-table v-loading="loading" :data="userList" @selection-change="handleSelectionChange">
          <el-table-column type="selection" width="50" align="center" />
          <el-table-column
            label="用户编号"
            align="center"
            key="userId"
            prop="userId"
            v-if="columns.userId.visible"
          />
          <el-table-column
            label="用户名称"
            align="center"
            key="userName"
            v-if="columns.userName.visible"
            :show-overflow-tooltip="true"
          >
            <template #default="scope">
              <el-button link type="primary" @click="handleViewData(scope.row)">{{
                scope.row.userName
              }}</el-button>
            </template>
          </el-table-column>
          <el-table-column
            label="用户昵称"
            align="center"
            key="nickName"
            prop="nickName"
            v-if="columns.nickName.visible"
            :show-overflow-tooltip="true"
          />
          <el-table-column
            label="部门"
            align="center"
            key="deptName"
            prop="dept.deptName"
            v-if="columns.deptName.visible"
            :show-overflow-tooltip="true"
          />
          <el-table-column
            label="手机号码"
            align="center"
            key="phonenumber"
            prop="phonenumber"
            v-if="columns.phonenumber.visible"
            width="120"
          />
          <el-table-column label="状态" align="center" key="status" v-if="columns.status.visible">
            <template #default="scope">
              <el-switch
                v-model="scope.row.status"
                active-value="0"
                inactive-value="1"
                @change="handleStatusChange(scope.row)"
              ></el-switch>
            </template>
          </el-table-column>
          <el-table-column
            label="创建时间"
            align="center"
            prop="createTime"
            v-if="columns.createTime.visible"
            width="160"
          >
            <template #default="scope">
              <span>{{ parseTime(scope.row.createTime) }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="操作"
            align="center"
            width="150"
            class-name="small-padding fixed-width"
          >
            <template #default="scope">
              <el-tooltip content="修改" placement="top" v-if="scope.row.userId !== 1">
                <el-button
                  aria-label="修改用户"
                  link
                  type="primary"
                  icon="Edit"
                  @click="handleUpdate(scope.row)"
                  v-hasPermi="['system:user:edit']"
                ></el-button>
              </el-tooltip>
              <el-tooltip content="删除" placement="top" v-if="scope.row.userId !== 1">
                <el-button
                  aria-label="删除用户"
                  link
                  type="primary"
                  icon="Delete"
                  @click="handleDelete(scope.row)"
                  v-hasPermi="['system:user:remove']"
                ></el-button>
              </el-tooltip>
              <el-tooltip content="重置密码" placement="top" v-if="scope.row.userId !== 1">
                <el-button
                  aria-label="重置密码"
                  link
                  type="primary"
                  icon="Key"
                  @click="handleResetPwd(scope.row)"
                  v-hasPermi="['system:user:resetPwd']"
                ></el-button>
              </el-tooltip>
              <el-tooltip content="分配角色" placement="top" v-if="scope.row.userId !== 1">
                <el-button
                  aria-label="分配角色"
                  link
                  type="primary"
                  icon="CircleCheck"
                  @click="handleAuthRole(scope.row)"
                  v-hasPermi="['system:user:edit']"
                ></el-button>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>
        <pagination
          v-show="total > 0"
          :total="total"
          v-model:page="queryParams.pageNum"
          v-model:limit="queryParams.pageSize"
          @pagination="getList"
        />
      </div>
    </div>

    <!-- 添加或修改用户配置对话框 -->
    <el-dialog
      class="native-directory-dialog native-user-editor-dialog"
      :title="title"
      v-model="open"
      width="600px"
      append-to-body
    >
      <el-form :model="form" :rules="rules" ref="userRef" label-width="80px">
        <el-row>
          <el-col :span="12">
            <el-form-item label="用户昵称" prop="nickName">
              <el-input v-model="form.nickName" placeholder="请输入用户昵称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="归属部门" prop="deptId">
              <el-tree-select
                v-model="form.deptId"
                :data="enabledDeptOptions"
                :props="{ value: 'id', label: 'label', children: 'children' }"
                value-key="id"
                placeholder="请选择归属部门"
                clearable
                check-strictly
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row>
          <el-col :span="12">
            <el-form-item label="手机号码" prop="phonenumber">
              <el-input v-model="form.phonenumber" placeholder="支持国际区号及分隔符" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="form.email" placeholder="请输入邮箱" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row>
          <el-col :span="12">
            <el-form-item v-if="form.userId == undefined" label="用户名称" prop="userName">
              <el-input v-model="form.userName" placeholder="请输入用户名称" maxlength="30" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              v-if="form.userId == undefined"
              label="用户密码"
              prop="password"
              :rules="pwdValidator"
            >
              <el-input
                v-model="form.password"
                placeholder="请输入用户密码"
                type="password"
                maxlength="20"
                show-password
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row>
          <el-col :span="12">
            <el-form-item label="用户性别">
              <el-select v-model="form.sex" placeholder="请选择">
                <el-option
                  v-for="dict in sys_user_sex"
                  :key="dict.value"
                  :label="dict.label"
                  :value="dict.value"
                ></el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-radio-group v-model="form.status">
                <el-radio
                  v-for="dict in sys_normal_disable"
                  :key="dict.value"
                  :value="dict.value"
                  >{{ dict.label }}</el-radio
                >
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row>
          <el-col :span="12">
            <el-form-item label="岗位">
              <el-select v-model="form.postIds" multiple placeholder="请选择">
                <el-option
                  v-for="item in postOptions"
                  :key="item.postId"
                  :label="item.postName"
                  :value="item.postId"
                  :disabled="item.status == 1"
                ></el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="角色">
              <el-select v-model="form.roleIds" multiple placeholder="请选择">
                <el-option
                  v-for="item in roleOptions"
                  :key="item.roleId"
                  :label="item.roleName"
                  :value="item.roleId"
                  :disabled="item.status == 1"
                ></el-option>
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" placeholder="请输入内容"></el-input>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitForm">确 定</el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 用户详情抽屉 -->
    <user-view-drawer ref="userViewRef" />
    <!-- 用户导入对话框 -->
    <excel-import-dialog
      dialog-class="native-directory-dialog native-user-import-dialog"
      ref="importUserRef"
      title="用户导入"
      action="/system/user/importData"
      template-action="/system/user/importTemplate"
      template-file-name="user_template"
      update-support-label="是否更新已经存在的用户数据"
      @success="getList"
    />
  </div>
</template>

<script setup name="User">
import TreePanel from '@/components/TreePanel'
import ExcelImportDialog from '@/components/ExcelImportDialog'
import UserViewDrawer from './view'
import { usePasswordRule } from '@/utils/passwordRule'
import {
  changeUserStatus,
  listUser,
  resetUserPwd,
  delUser,
  getUser,
  updateUser,
  addUser,
  deptTreeSelect,
} from '@/api/system/user'

/** 与Python/ORBIT及原个人资料保持一致：NFC后的Unicode码点，联系方式不是国内手机专用。 */
function contactLengthRule(maximum, label) {
  return (_rule, value, callback) => {
    const text = String(value ?? '')
      .normalize('NFC')
      .trim()
    if (Array.from(text).length > maximum || /[\p{Cc}\p{Cf}\p{Cs}]/u.test(text)) {
      callback(new Error(`${label}最多${maximum}个字符，不能包含控制字符`))
    } else callback()
  }
}

const router = useRouter()
const { proxy } = getCurrentInstance()
const { pwdValidator, pwdPromptValidator } = usePasswordRule()
const { sys_normal_disable, sys_user_sex } = useDict('sys_normal_disable', 'sys_user_sex')

const userList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref('')
const dateRange = ref([])
const deptOptions = ref(undefined)
const enabledDeptOptions = ref(undefined)
const initPassword = ref(undefined)
const postOptions = ref([])
const roleOptions = ref([])
// 列显隐信息
const columns = ref({
  userId: { label: '用户编号', visible: true },
  userName: { label: '用户名称', visible: true },
  nickName: { label: '用户昵称', visible: true },
  deptName: { label: '部门', visible: true },
  phonenumber: { label: '手机号码', visible: true },
  status: { label: '状态', visible: true },
  createTime: { label: '创建时间', visible: true },
})

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    userName: undefined,
    phonenumber: undefined,
    status: undefined,
    deptId: undefined,
  },
  rules: {
    userName: [
      { required: true, message: '用户名称不能为空', trigger: 'blur' },
      { min: 2, max: 20, message: '用户名称长度必须介于 2 和 20 之间', trigger: 'blur' },
    ],
    nickName: [
      { required: true, message: '用户昵称不能为空', trigger: 'blur' },
      { validator: contactLengthRule(50, '昵称'), trigger: ['blur', 'change'] },
    ],
    email: [
      { required: false, message: '业务人员邮箱不能为空', trigger: ['blur', 'change'] },
      { type: 'email', message: '请输入正确的邮箱地址', trigger: ['blur', 'change'] },
      { validator: contactLengthRule(254, '邮箱'), trigger: ['blur', 'change'] },
    ],
    phonenumber: [{ validator: contactLengthRule(32, '联系方式'), trigger: ['blur', 'change'] }],
  },
})

const { queryParams, form, rules } = toRefs(data)

/** 查询用户列表 */
function getList() {
  loading.value = true
  listUser(proxy.addDateRange(queryParams.value, dateRange.value)).then((res) => {
    loading.value = false
    userList.value = res.rows
    total.value = res.total
  })
}

/** 查询部门下拉树结构 */
function getDeptTree() {
  deptTreeSelect().then((response) => {
    deptOptions.value = response.data
    enabledDeptOptions.value = filterDisabledDept(JSON.parse(JSON.stringify(response.data)))
  })
}

/** 过滤禁用的部门 */
function filterDisabledDept(deptList) {
  return deptList.filter((dept) => {
    if (dept.disabled) {
      return false
    }
    if (dept.children && dept.children.length) {
      dept.children = filterDisabledDept(dept.children)
    }
    return true
  })
}

/** 节点单击事件 */
function handleNodeClick(data) {
  queryParams.value.deptId = data.id
  handleQuery()
}

/** 搜索按钮操作 */
function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

/** 重置按钮操作 */
function resetQuery() {
  dateRange.value = []
  proxy.resetForm('queryRef')
  queryParams.value.deptId = undefined
  proxy.$refs.deptTreeRef.setCurrentKey(null)
  handleQuery()
}

/** 删除按钮操作 */
function handleDelete(row) {
  const userIds = row.userId || ids.value
  proxy.$modal
    .confirm('是否确认删除用户编号为"' + userIds + '"的数据项？')
    .then(function () {
      return delUser(userIds)
    })
    .then(() => {
      getList()
      proxy.$modal.msgSuccess('删除成功')
    })
    .catch(() => {})
}

/** 导出按钮操作 */
function handleExport() {
  proxy.download(
    'system/user/export',
    {
      ...queryParams.value,
    },
    `user_${new Date().getTime()}.xlsx`,
  )
}

/** 用户状态修改  */
function handleStatusChange(row) {
  let text = row.status === '0' ? '启用' : '停用'
  proxy.$modal
    .confirm('确认要"' + text + '""' + row.userName + '"用户吗?')
    .then(function () {
      return changeUserStatus(row.userId, row.status)
    })
    .then(() => {
      proxy.$modal.msgSuccess(text + '成功')
    })
    .catch(function () {
      row.status = row.status === '0' ? '1' : '0'
    })
}

/** 更多操作 */
function handleCommand(command, row) {
  switch (command) {
    case 'handleResetPwd':
      handleResetPwd(row)
      break
    case 'handleAuthRole':
      handleAuthRole(row)
      break
    default:
      break
  }
}

/** 跳转角色分配 */
function handleAuthRole(row) {
  const userId = row.userId
  router.push('/system/user-auth/role/' + userId)
}

/** 重置密码按钮操作 */
function handleResetPwd(row) {
  proxy
    .$prompt(`请输入「${row.userName}」的新密码`, '重置密码', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      closeOnClickModal: false,
      inputValidator: pwdPromptValidator,
    })
    .then(({ value }) => {
      resetUserPwd(row.userId, value).then(() => {
        proxy.$modal.msgSuccess('修改成功，新密码是：' + value)
      })
    })
    .catch(() => {})
}

/** 选择条数  */
function handleSelectionChange(selection) {
  ids.value = selection.map((item) => item.userId)
  single.value = selection.length != 1
  multiple.value = !selection.length
}

/** 详情按钮操作 */
function handleViewData(row) {
  proxy.$refs['userViewRef'].open(row.userId)
}

/** 导入按钮操作 */
function handleImport() {
  proxy.$refs['importUserRef'].open()
}

/** 重置操作表单 */
function reset() {
  rules.value.nickName[0].required = true
  rules.value.email[0].required = false
  form.value = {
    userId: undefined,
    deptId: undefined,
    userName: undefined,
    nickName: undefined,
    password: undefined,
    phonenumber: undefined,
    email: undefined,
    sex: undefined,
    status: '0',
    remark: undefined,
    postIds: [],
    roleIds: [],
  }
  proxy.resetForm('userRef')
}

/** 取消按钮 */
function cancel() {
  open.value = false
  reset()
}

/** 新增按钮操作 */
function handleAdd() {
  reset()
  getUser().then((response) => {
    postOptions.value = response.posts
    roleOptions.value = response.roles
    open.value = true
    title.value = '添加用户'
    form.value.password = initPassword.value
  })
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset()
  const userId = row.userId || ids.value
  getUser(userId).then((response) => {
    // 服务端只读提示区分业务人员与原技术账户；后端独立校验，不能信任客户端标记。
    rules.value.nickName[0].required = !response.businessManaged
    rules.value.email[0].required = Boolean(response.businessManaged)
    form.value = response.data
    postOptions.value = response.posts
    roleOptions.value = response.roles
    form.value.postIds = response.postIds
    form.value.roleIds = response.roleIds
    open.value = true
    title.value = '修改用户'
    // 编辑资料不提交密码；Python原密码校验也不能被空串触发，改密走专用入口。
    form.value.password = undefined
  })
}

/** 提交按钮 */
function submitForm() {
  // 原人员入口与ORBIT/个人资料统一码点和国际联系方式规则，不能被旧HTML长度截断。
  for (const field of ['nickName', 'email', 'phonenumber']) {
    form.value[field] = String(form.value[field] ?? '')
      .normalize('NFC')
      .trim()
  }
  proxy.$refs['userRef'].validate((valid) => {
    if (valid) {
      if (form.value.userId != undefined) {
        updateUser(form.value).then(() => {
          proxy.$modal.msgSuccess('修改成功')
          open.value = false
          getList()
        })
      } else {
        addUser(form.value).then(() => {
          proxy.$modal.msgSuccess('新增成功')
          open.value = false
          getList()
        })
      }
    }
  })
}

onMounted(() => {
  getDeptTree()
  getList()
  proxy.getConfigKey('sys.user.initPassword').then((response) => {
    initPassword.value = response.msg
  })
})
</script>

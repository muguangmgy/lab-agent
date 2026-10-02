<template>
  <div>
    <el-card>
      <template #header>
        <div style="font-size: 16px; font-weight: bold">
          <span>用户管理</span>
        </div>
      </template>
      <div style="margin-bottom: 10px">
        <el-input
          placeholder="请输入账号或名称查询"
          v-model="params.keywords"
          style="width: 240px; margin-right: 8px"
          clearable
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
        <el-button type="success" :icon="Plus" @click="handleCreate">新增</el-button>
      </div>

      <el-table
        :header-cell-style="{ backgroundColor: '#f5f7fa', color: '#333' }"
        :data="tableData"
        style="width: 100%"
        v-loading="loading"
      >
        <el-table-column align="center" prop="username" label="账号" />
        <el-table-column align="center" prop="name" label="名称" />
        <el-table-column align="center" prop="avatar" label="头像">
          <template #default="{ row }">
            <div style="min-height: 50px">
              <img
                v-if="row.avatar"
                style="display: block; width: 50px; height: 50px; border-radius: 50%"
                :src="row.avatar"
                alt=""
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column align="center" prop="email" label="邮箱" />
        <el-table-column align="center" prop="phone" label="手机号" />
        <el-table-column align="center" label="角色" min-width="160">
          <template #default="{ row }">
            <el-tag
              v-for="r in row.roles || []"
              :key="r.id"
              style="margin-right: 4px; margin-bottom: 2px"
              size="small"
            >
              {{ r.name }}
            </el-tag>
            <span v-if="!(row.roles && row.roles.length)">-</span>
          </template>
        </el-table-column>
        <el-table-column align="center" prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'danger'">
              {{ row.status === 1 ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column align="center" label="操作" width="160">
          <template #default="{ row }">
            <el-button type="primary" text bg @click="handleEdit(row)">编辑</el-button>
            <el-button type="danger" text bg @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 10px; display: flex; justify-content: flex-end">
        <el-pagination
          v-model:current-page="params.page"
          v-model:page-size="params.pageSize"
          :total="total"
          background
          layout="total, prev, pager, next"
          @current-change="load"
        />
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑' : '新增'" width="450" align-center
      @open="formRef?.clearValidate()">
      <el-form
        ref="formRef"
        :rules="rules"
        :model="form"
        label-width="80px"
        style="width: 100%; padding-right: 30px; padding-top: 16px"
        v-loading="loading"
      >
        <el-form-item label="账号" prop="username">
          <el-input :disabled="!!form.id" v-model="form.username" placeholder="请输入账号" />
        </el-form-item>
        <el-form-item label="密码" prop="password" v-if="!form.id">
          <el-input
            type="password"
            show-password
            v-model="form.password"
            placeholder="请输入密码"
          />
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入名称" />
        </el-form-item>
        <el-form-item label="角色" prop="role_ids">
          <el-select v-model="form.role_ids" multiple placeholder="请选择角色" style="width: 100%">
            <el-option
              v-for="r in roleOptions"
              :key="r.id"
              :label="r.name"
              :value="r.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="form.phone" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio :value="1">正常</el-radio>
            <el-radio :value="0">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="formLoading" @click="handleSave">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { Search, Plus } from '@element-plus/icons-vue'
import { createUserApi, deleteUserApi, getUserPageList, updateUserApi } from '@/api/user'
import { getRoleListApi } from '@/api/role'
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const params = reactive({
  page: 1,
  pageSize: 10,
  keywords: ''
})
const loading = ref(false)
const tableData = ref([])
const total = ref(0)
const dialogVisible = ref(false)
const formRef = ref()
const roleOptions = ref([])
const form = reactive({
  id: null,
  username: '',
  password: '123456',
  name: '',
  role_ids: [],
  email: '',
  phone: '',
  avatar: '',
  status: 1
})
const formLoading = ref(false)

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码至少 6 位', trigger: 'blur' }
  ],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  role_ids: [{ required: true, type: 'array', min: 1, message: '请选择至少一个角色', trigger: 'change' }],
  email: [{ type: 'email', message: '邮箱格式错误', trigger: 'blur' }],
  phone: [{ pattern: /^1[3-9]\d{9}$/, message: '手机号格式错误', trigger: 'blur' }]
}

/** 重置用户表单为默认值（含默认密码） */
const resetForm = () => {
  Object.assign(form, {
    id: null,
    username: '',
    password: '123456',
    name: '',
    role_ids: [],
    email: '',
    phone: '',
    avatar: '',
    status: 1
  })
}

/** 加载角色下拉全量列表 */
const loadRoles = async () => {
  const res = await getRoleListApi()
  if (res.code === 200) {
    roleOptions.value = res.data || []
  }
}

/** 打开新增用户弹窗（默认勾选学生角色） */
const handleCreate = () => {
  resetForm()
  const student = roleOptions.value.find((r) => r.code === 'student')
  if (student) form.role_ids = [student.id]
  dialogVisible.value = true
}

/** 回填行数据并打开编辑弹窗 */
const handleEdit = (row) => {
  resetForm()
  Object.assign(form, {
    id: row.id,
    username: row.username,
    name: row.name,
    role_ids: (row.roles || []).map((r) => r.id),
    email: row.email,
    phone: row.phone,
    avatar: row.avatar,
    status: row.status
  })
  dialogVisible.value = true
}

/** 确认后删除用户并刷新列表 */
const handleDelete = (row) => {
  ElMessageBox.confirm(`确认删除用户 [${row.username}] ？`, '确认删除', { type: 'warning' }).then(
    async () => {
      const res = await deleteUserApi(row.id)
      if (res.code === 200) {
        ElMessage.success('删除用户成功')
        load()
      }
    }
  )
}

/** 校验通过后：有 id 则更新，否则新增（新增才带密码） */
const handleSave = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  formLoading.value = true
  try {
    const payload = {
      username: form.username,
      name: form.name,
      role_ids: form.role_ids,
      email: form.email,
      phone: form.phone,
      avatar: form.avatar,
      status: form.status
    }
    if (!form.id) {
      payload.password = form.password
    }
    const res = form.id
      ? await updateUserApi(form.id, payload)
      : await createUserApi(payload)
    if (res.code === 200) {
      dialogVisible.value = false
      ElMessage.success('操作成功')
      load()
    }
  } finally {
    formLoading.value = false
  }
}

/** 拉取用户分页列表并刷新表格 */
const load = async () => {
  loading.value = true
  try {
    const res = await getUserPageList({
      page: params.page,
      page_size: params.pageSize,
      keywords: params.keywords
    })
    if (res.code === 200) {
      tableData.value = res.data?.list
      total.value = res.data?.total
    }
  } finally {
    loading.value = false
  }
}

/** 重置到第一页并按关键词查询 */
const handleSearch = async () => {
  params.page = 1
  load()
}

onMounted(async () => {
  await loadRoles()
  load()
})
</script>

<template>
  <div>
    <el-card>
      <template #header>
        <div style="font-size: 16px; font-weight: bold">
          <span>角色管理</span>
        </div>
      </template>
      <div style="margin-bottom: 10px">
        <el-input
          placeholder="请输入编码或名称查询"
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
        <el-table-column align="center" prop="code" label="编码" width="140" />
        <el-table-column align="center" prop="name" label="名称" width="140" />
        <el-table-column align="center" prop="remark" label="备注" />
        <el-table-column align="center" prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'danger'">
              {{ row.status === 1 ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column align="center" label="操作" width="240">
          <template #default="{ row }">
            <el-button type="primary" text bg @click="handleEdit(row)">编辑</el-button>
            <el-button type="warning" text bg @click="handleMenus(row)">分配菜单</el-button>
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

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑角色' : '新增角色'" width="450" align-center
      @open="formRef?.clearValidate()">
      <el-form
        ref="formRef"
        :rules="rules"
        :model="form"
        label-width="80px"
        style="width: 100%; padding-right: 30px; padding-top: 16px"
      >
        <el-form-item label="编码" prop="code">
          <el-input v-model="form.code" :disabled="!!form.id" placeholder="如 admin" />
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入名称" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" placeholder="备注" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio :value="1">启用</el-radio>
            <el-radio :value="0">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="formLoading" @click="handleSave">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="menuDialogVisible" title="分配菜单" width="480" align-center>
      <el-tree
        ref="treeRef"
        :data="menuTree"
        show-checkbox
        node-key="id"
        default-expand-all
        :props="{ label: 'name', children: 'children' }"
      />
      <template #footer>
        <el-button @click="menuDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="menuSaving" @click="handleSaveMenus">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { Search, Plus } from '@element-plus/icons-vue'
import {
  createRoleApi,
  deleteRoleApi,
  getRolePageApi,
  updateRoleApi,
  updateRoleMenusApi
} from '@/api/role'
import { getMenuTreeApi } from '@/api/menu'
import { ref, reactive, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const params = reactive({ page: 1, pageSize: 10, keywords: '' })
const loading = ref(false)
const tableData = ref([])
const total = ref(0)
const dialogVisible = ref(false)
const formRef = ref()
const formLoading = ref(false)
const form = reactive({
  id: null,
  code: '',
  name: '',
  remark: '',
  status: 1
})
const rules = {
  code: [{ required: true, message: '请输入编码', trigger: 'blur' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }]
}

const menuDialogVisible = ref(false)
const menuTree = ref([])
const treeRef = ref()
const menuSaving = ref(false)
const currentRole = ref(null)

/** 重置角色表单为默认值 */
const resetForm = () => {
  Object.assign(form, { id: null, code: '', name: '', remark: '', status: 1 })
}

/** 打开新增角色弹窗 */
const handleCreate = () => {
  resetForm()
  dialogVisible.value = true
}

/** 回填行数据并打开编辑弹窗 */
const handleEdit = (row) => {
  resetForm()
  Object.assign(form, {
    id: row.id,
    code: row.code,
    name: row.name,
    remark: row.remark,
    status: row.status
  })
  dialogVisible.value = true
}

/** 确认后删除角色并刷新列表 */
const handleDelete = (row) => {
  ElMessageBox.confirm(`确认删除角色 [${row.name}] ？`, '确认删除', { type: 'warning' }).then(
    async () => {
      const res = await deleteRoleApi(row.id)
      if (res.code === 200) {
        ElMessage.success('删除成功')
        load()
      }
    }
  )
}

/** 校验通过后：有 id 则更新，否则新增 */
const handleSave = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  formLoading.value = true
  try {
    const payload = {
      code: form.code,
      name: form.name,
      remark: form.remark,
      status: form.status
    }
    const res = form.id
      ? await updateRoleApi(form.id, payload)
      : await createRoleApi(payload)
    if (res.code === 200) {
      dialogVisible.value = false
      ElMessage.success('操作成功')
      load()
    }
  } finally {
    formLoading.value = false
  }
}

/** 打开菜单分配弹窗并回显已绑定节点 */
const handleMenus = async (row) => {
  currentRole.value = row
  const res = await getMenuTreeApi()
  if (res.code === 200) {
    menuTree.value = res.data || []
  }
  menuDialogVisible.value = true
  await nextTick()
  treeRef.value?.setCheckedKeys(row.menu_ids || [])
}

/** 提交角色菜单绑定（含半选父节点） */
const handleSaveMenus = async () => {
  if (!currentRole.value) return
  menuSaving.value = true
  try {
    const checked = treeRef.value.getCheckedKeys(false)
    const half = treeRef.value.getHalfCheckedKeys()
    const menuIds = [...checked, ...half]
    const res = await updateRoleMenusApi(currentRole.value.id, menuIds)
    if (res.code === 200) {
      ElMessage.success('菜单分配成功')
      menuDialogVisible.value = false
      load()
    }
  } finally {
    menuSaving.value = false
  }
}

/** 拉取角色分页列表并刷新表格 */
const load = async () => {
  loading.value = true
  try {
    const res = await getRolePageApi({
      page: params.page,
      page_size: params.pageSize,
      keywords: params.keywords
    })
    if (res.code === 200) {
      tableData.value = res.data?.list || []
      total.value = res.data?.total || 0
    }
  } finally {
    loading.value = false
  }
}

/** 重置到第一页并按关键词查询 */
const handleSearch = () => {
  params.page = 1
  load()
}

onMounted(() => {
  load()
})
</script>

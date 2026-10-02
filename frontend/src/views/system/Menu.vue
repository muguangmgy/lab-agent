<template>
  <div>
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <div style="font-size: 16px; font-weight: bold">菜单管理</div>
          <el-button type="success" :icon="Plus" @click="handleCreate(null)">新增根菜单</el-button>
        </div>
      </template>

      <el-table
        :header-cell-style="{ backgroundColor: '#f5f7fa', color: '#333' }"
        :data="tableData"
        style="width: 100%"
        row-key="id"
        default-expand-all
        v-loading="loading"
        :tree-props="{ children: 'children' }"
      >
        <el-table-column align="center" prop="name" label="名称" min-width="160" />
        <el-table-column align="center" prop="type" label="类型" width="90" />
        <el-table-column align="center" prop="path" label="路由" min-width="180" />
        <el-table-column align="center" prop="icon" label="图标" width="120" />
        <el-table-column align="center" prop="permission" label="权限码" width="140" />
        <el-table-column align="center" prop="sort" label="排序" width="80" />
        <el-table-column align="center" prop="visible" label="侧栏" width="80">
          <template #default="{ row }">
            {{ row.visible === 1 ? '显示' : '隐藏' }}
          </template>
        </el-table-column>
        <el-table-column align="center" prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'danger'">
              {{ row.status === 1 ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column align="center" label="操作" width="220">
          <template #default="{ row }">
            <el-button type="success" text bg @click="handleCreate(row)">子菜单</el-button>
            <el-button type="primary" text bg @click="handleEdit(row)">编辑</el-button>
            <el-button type="danger" text bg @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑菜单' : '新增菜单'" width="520" align-center
      @open="formRef?.clearValidate()">
      <el-form
        ref="formRef"
        :rules="rules"
        :model="form"
        label-width="90px"
        style="width: 100%; padding-right: 30px; padding-top: 16px"
      >
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="菜单名称" />
        </el-form-item>
        <el-form-item label="类型" prop="type">
          <el-select v-model="form.type" style="width: 100%">
            <el-option label="目录" value="dir" />
            <el-option label="菜单" value="menu" />
            <el-option label="按钮" value="button" />
          </el-select>
        </el-form-item>
        <el-form-item label="路由">
          <el-input v-model="form.path" placeholder="/manager/xxx" />
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="form.icon" placeholder="如 House / User" />
        </el-form-item>
        <el-form-item label="权限码">
          <el-input v-model="form.permission" placeholder="可选，如 lab:write" />
        </el-form-item>
        <el-form-item label="组件">
          <el-input v-model="form.component" placeholder="可选" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort" :min="0" :max="9999" />
        </el-form-item>
        <el-form-item label="侧栏显示">
          <el-radio-group v-model="form.visible">
            <el-radio :value="1">显示</el-radio>
            <el-radio :value="0">隐藏</el-radio>
          </el-radio-group>
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
  </div>
</template>

<script setup>
import { Plus } from '@element-plus/icons-vue'
import { createMenuApi, deleteMenuApi, getMenuTreeApi, updateMenuApi } from '@/api/menu'
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const loading = ref(false)
const tableData = ref([])
const dialogVisible = ref(false)
const formRef = ref()
const formLoading = ref(false)
const form = reactive({
  id: null,
  parent_id: null,
  name: '',
  type: 'menu',
  path: '',
  component: '',
  icon: '',
  permission: '',
  sort: 0,
  visible: 1,
  status: 1
})
const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择类型', trigger: 'change' }]
}

/** 重置菜单表单为默认值 */
const resetForm = () => {
  Object.assign(form, {
    id: null,
    parent_id: null,
    name: '',
    type: 'menu',
    path: '',
    component: '',
    icon: '',
    permission: '',
    sort: 0,
    visible: 1,
    status: 1
  })
}

/** 打开新增菜单弹窗（可指定父级） */
const handleCreate = (parent) => {
  resetForm()
  form.parent_id = parent?.id ?? null
  dialogVisible.value = true
}

/** 回填行数据并打开编辑弹窗 */
const handleEdit = (row) => {
  resetForm()
  Object.assign(form, {
    id: row.id,
    parent_id: row.parent_id,
    name: row.name,
    type: row.type,
    path: row.path || '',
    component: row.component || '',
    icon: row.icon || '',
    permission: row.permission || '',
    sort: row.sort ?? 0,
    visible: row.visible,
    status: row.status
  })
  dialogVisible.value = true
}

/** 确认后删除菜单并刷新树 */
const handleDelete = (row) => {
  ElMessageBox.confirm(`确认删除菜单 [${row.name}] ？`, '确认删除', { type: 'warning' }).then(
    async () => {
      const res = await deleteMenuApi(row.id)
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
      parent_id: form.parent_id,
      name: form.name,
      type: form.type,
      path: form.path || null,
      component: form.component || null,
      icon: form.icon || null,
      permission: form.permission || null,
      sort: form.sort,
      visible: form.visible,
      status: form.status
    }
    const res = form.id
      ? await updateMenuApi(form.id, payload)
      : await createMenuApi(payload)
    if (res.code === 200) {
      dialogVisible.value = false
      ElMessage.success('操作成功')
      load()
    }
  } finally {
    formLoading.value = false
  }
}

/** 拉取菜单树并刷新表格 */
const load = async () => {
  loading.value = true
  try {
    const res = await getMenuTreeApi()
    if (res.code === 200) {
      tableData.value = res.data || []
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
})
</script>

<template>
  <div class="app-shell" :class="{ 'is-collapsed': collapsed }">
    <el-container style="min-height: 100vh">
      <el-header>
        <div class="brand" style="flex: 1">
          <img src="@/assets/imgs/logo.png" alt="" />
          <div>智能实验室预约系统</div>
        </div>
        <el-dropdown @command="handleCommand">
          <div class="user-chip" style="cursor: pointer">
            <img :src="userInfo?.avatar" alt="" />
            <!-- <div>{{ userInfo?.name }}</div> -->
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">个人信息</el-dropdown-item>
              <el-dropdown-item command="password">修改密码</el-dropdown-item>
              <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-container>
        <el-aside :width="asideWidth">
          <div class="aside-inner">
            <el-menu
              router
              :collapse="collapsed"
              :collapse-transition="false"
              :default-active="router.currentRoute.value.path"
              class="aside-menu"
            >
              <template v-for="item in sidebarMenus" :key="item.id">
                <el-sub-menu v-if="item.children?.length" :index="item.path || String(item.id)">
                  <template #title>
                    <el-icon>
                      <component :is="resolveIcon(item.icon) || IconMenu" />
                    </el-icon>
                    <span>{{ item.name }}</span>
                  </template>
                  <el-menu-item v-for="child in item.children" :key="child.id" :index="child.path">
                    <el-icon>
                      <component :is="resolveIcon(child.icon) || IconMenu" />
                    </el-icon>
                    <span>{{ child.name }}</span>
                  </el-menu-item>
                </el-sub-menu>
                <el-menu-item v-else-if="item.path" :index="item.path">
                  <el-icon>
                    <component :is="resolveIcon(item.icon) || IconMenu" />
                  </el-icon>
                  <span>{{ item.name }}</span>
                </el-menu-item>
              </template>
            </el-menu>
            <button
              class="collapse-btn"
              type="button"
              :title="collapsed ? '展开菜单' : '收起菜单'"
              @click="toggleCollapse"
            >
              <el-icon :size="16">
                <DArrowRight v-if="collapsed" />
                <DArrowLeft v-else />
              </el-icon>
              <span v-if="!collapsed">收起菜单</span>
            </button>
          </div>
        </el-aside>
        <el-main>
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import router from '@/router'
import { logout } from '@/utils/auth'
import {
  Menu as IconMenu,
  House,
  Setting,
  User,
  OfficeBuilding,
  Tickets,
  DocumentChecked,
  ChatDotRound,
  Avatar,
  Grid,
  Cpu,
  DArrowLeft,
  DArrowRight
} from '@element-plus/icons-vue'
import { useUser } from '@/utils/user'

const COLLAPSE_KEY = 'lab-sidebar-collapsed'
const ASIDE_EXPANDED = '220px'
const ASIDE_COLLAPSED = '64px'

const { userInfo, menus, loadMenus } = useUser()

const collapsed = ref(localStorage.getItem(COLLAPSE_KEY) === '1')
const asideWidth = computed(() => (collapsed.value ? ASIDE_COLLAPSED : ASIDE_EXPANDED))

/** 切换侧栏折叠并持久化到 localStorage */
function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0')
}

const iconMap = {
  Menu: IconMenu,
  House,
  Setting,
  User,
  OfficeBuilding,
  Tickets,
  DocumentChecked,
  ChatDotRound,
  Avatar,
  Grid,
  Cpu
}

/** 按菜单 icon 名解析为 Element Plus 图标组件 */
function resolveIcon(name) {
  if (!name) return null
  return iconMap[name] || null
}

/** 侧栏只展示 visible=1 的菜单 */
function filterVisible(list) {
  return (list || [])
    .filter((m) => m.visible !== 0)
    .map((m) => ({
      ...m,
      children: filterVisible(m.children)
    }))
}

const sidebarMenus = computed(() => filterVisible(menus.value))

/** 处理顶栏下拉：个人资料 / 改密 / 退出 */
const handleCommand = (command) => {
  if (command === 'profile') {
    router.push('/manager/profile')
  } else if (command === 'password') {
    router.push('/manager/password')
  } else if (command === 'logout') {
    logout()
    router.push('/login')
  }
}

onMounted(async () => {
  try {
    await loadMenus()
  } catch {
    // 拉取失败时侧栏可能为空，守卫会处理
  }
})
</script>

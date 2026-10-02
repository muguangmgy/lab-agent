import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/utils/auth'
import { useUser } from '@/utils/user'
import { ElMessage } from 'element-plus'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/manager/home' },
    {
      path: '/manager',
      name: 'Layout',
      component: () => import('@/layouts/Layout.vue'),
      children: [
        { path: 'home', name: 'Home', component: () => import('@/views/Home.vue') },
        { path: 'lab', name: 'Lab', component: () => import('@/views/lab/Lab.vue') },
        { path: 'profile', name: 'Profile', component: () => import('@/views/auth/Profile.vue') },
        {
          path: 'password',
          name: 'Password',
          component: () => import('@/views/auth/Password.vue')
        },
        { path: 'user', name: 'User', component: () => import('@/views/system/User.vue') },
        {
          path: 'equipment',
          name: 'Equipment',
          component: () => import('@/views/lab/Equipment.vue')
        },
        {
          path: 'lab-equipment',
          name: 'labEquipment',
          component: () => import('@/views/lab/LabEquipment.vue')
        },
        { path: 'lablist', name: 'LabList', component: () => import('@/views/lab/LabList.vue') },
        {
          path: 'my-reservation',
          name: 'MyReservation',
          component: () => import('@/views/reservation/MyReservation.vue')
        },
        {
          path: 'audit-reservation',
          name: 'AuditReservation',
          component: () => import('@/views/reservation/AuditReservation.vue')
        },
        {
          path: 'ai-chat',
          name: 'AIChat',
          component: () => import('@/views/ai/AIChat.vue')
        },
        { path: 'role', name: 'Role', component: () => import('@/views/system/Role.vue') },
        { path: 'menu', name: 'Menu', component: () => import('@/views/system/Menu.vue') }
      ]
    },
    { path: '/login', name: 'Login', component: () => import('@/views/auth/Login.vue') },
    { path: '/register', name: 'Register', component: () => import('@/views/auth/Register.vue') }
  ]
})

/** 白名单：不依赖菜单绑定即可访问 */
const WHITE_LIST = ['/manager/home', '/manager/profile', '/manager/password']

// 路由守卫：token + 菜单 path
router.beforeEach(async (to) => {
  const token = getToken()

  if (to.path === '/login' || to.path === '/register') {
    if (token) {
      return '/manager/home'
    }
    return true
  }

  if (!token) {
    return '/login'
  }

  // 非 manager 子路由直接放行
  if (!to.path.startsWith('/manager')) {
    return true
  }

  if (WHITE_LIST.includes(to.path)) {
    return true
  }

  const { menus, loadMenus, getMenuPaths } = useUser()
  if (!menus.value?.length) {
    try {
      await loadMenus()
    } catch {
      return '/manager/home'
    }
  }

  const allowed = getMenuPaths()
  if (allowed.includes(to.path)) {
    return true
  }

  ElMessage.warning('无权限访问该页面')
  return '/manager/home'
})

export default router

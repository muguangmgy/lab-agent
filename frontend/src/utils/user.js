// 仅供页面 setup 函数使用
import { ref } from 'vue'
import { getUserInfo, setToken, setUserInfo, onLogout } from './auth'
import { getMyMenusApi } from '@/api/menu'

const MENUS_KEY = 'menus'
const PERMS_KEY = 'permissions'

const userInfo = ref(getUserInfo())
const menus = ref(_loadJson(MENUS_KEY) || [])
const permissions = ref(_loadJson(PERMS_KEY) || [])

/** 安全解析 localStorage 中的 JSON */
function _loadJson(key) {
  try {
    const str = localStorage.getItem(key)
    return str ? JSON.parse(str) : null
  } catch {
    return null
  }
}

/** 将值序列化写入 localStorage */
function _saveJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value))
}

/** 递归收集菜单树中所有 path */
function collectPaths(menuList, out = []) {
  for (const m of menuList || []) {
    if (m.path) out.push(m.path)
    if (m.children?.length) collectPaths(m.children, out)
  }
  return out
}

/** 清空菜单/权限内存态与本地缓存 */
function clearAuthExtra() {
  menus.value = []
  permissions.value = []
  localStorage.removeItem(MENUS_KEY)
  localStorage.removeItem(PERMS_KEY)
}

// 登出时同步清内存态（auth 不反向 import 本文件，避免循环依赖）
onLogout(clearAuthExtra)

/** 提供用户/菜单/权限状态与鉴权辅助方法 */
export function useUser() {
  /** 登录成功后写入 token、用户信息与权限 */
  function saveLoginData(data) {
    setToken(data.token)
    setUserInfo(data.user)
    userInfo.value = data.user
    if (data.user?.permissions) {
      permissions.value = data.user.permissions
      _saveJson(PERMS_KEY, data.user.permissions)
    }
  }

  /** 更新本地与内存中的用户信息（含权限） */
  function updateUser(user) {
    setUserInfo(user)
    userInfo.value = user
    if (user?.permissions) {
      permissions.value = user.permissions
      _saveJson(PERMS_KEY, user.permissions)
    }
  }

  /** 从 localStorage 重新加载用户信息到内存 */
  function reloadUser() {
    userInfo.value = getUserInfo()
  }

  /** 设置菜单树并持久化到本地 */
  function setMenus(menuList) {
    menus.value = menuList || []
    _saveJson(MENUS_KEY, menus.value)
  }

  /** 拉取当前用户菜单并集并同步权限缓存 */
  async function loadMenus() {
    const res = await getMyMenusApi()
    if (res.code === 200) {
      setMenus(res.data || [])
      if (userInfo.value?.permissions) {
        permissions.value = userInfo.value.permissions
        _saveJson(PERMS_KEY, permissions.value)
      }
    }
    return menus.value
  }

  /** 判断当前用户是否拥有指定角色 code */
  function hasRole(code) {
    const roles = userInfo.value?.roles || []
    if (roles.length) return roles.some((r) => r.code === code)
    return userInfo.value?.role === code
  }

  /** 判断当前用户是否拥有任一指定角色 */
  function hasAnyRole(codes) {
    return (codes || []).some((c) => hasRole(c))
  }

  /** 判断当前用户是否拥有指定权限码 */
  function hasPermission(code) {
    return (permissions.value || []).includes(code)
  }

  /** 返回当前菜单树中全部可访问 path */
  function getMenuPaths() {
    return collectPaths(menus.value)
  }

  return {
    userInfo,
    menus,
    permissions,
    saveLoginData,
    updateUser,
    reloadUser,
    setMenus,
    loadMenus,
    clearAuthExtra,
    hasRole,
    hasAnyRole,
    hasPermission,
    getMenuPaths
  }
}

/** 对外暴露：清空菜单/权限缓存（同 clearAuthExtra） */
export function clearMenusCache() {
  clearAuthExtra()
}

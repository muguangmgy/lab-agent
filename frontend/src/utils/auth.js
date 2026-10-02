// 存储 token / 用户信息；登出钩子供 user.js 清理内存态（避免循环依赖）
const TOKEN_KEY = 'token'
const USER_KEY = 'userInfo'
const MENUS_KEY = 'menus'
const PERMS_KEY = 'permissions'

let _onLogout = null

/** 由 user.js 注册，用于清菜单/权限内存 ref */
export function onLogout(fn) {
  _onLogout = fn
}

/** 读取本地 token */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

/** 写入本地 token */
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

/** 清除本地 token */
export function removeToken() {
  localStorage.removeItem(TOKEN_KEY)
}

/** 读取本地用户信息（JSON） */
export function getUserInfo() {
  const str = localStorage.getItem(USER_KEY)
  return str ? JSON.parse(str) : null
}

/** 写入本地用户信息 */
export function setUserInfo(userInfo) {
  localStorage.setItem(USER_KEY, JSON.stringify(userInfo))
}

/** 清除本地用户信息 */
export function removeUserInfo() {
  localStorage.removeItem(USER_KEY)
}

/** 登出：清 token/用户/菜单/权限，并触发 onLogout 钩子 */
export function logout() {
  removeToken()
  removeUserInfo()
  localStorage.removeItem(MENUS_KEY)
  localStorage.removeItem(PERMS_KEY)
  _onLogout?.()
}

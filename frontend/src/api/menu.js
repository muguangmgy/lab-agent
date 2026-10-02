import request from '@/utils/request'

/** 当前用户菜单并集 */
export function getMyMenusApi() {
  return request({
    url: '/api/menu/my',
    method: 'get'
  })
}

/** 菜单树（管理） */
export function getMenuTreeApi() {
  return request({
    url: '/api/menu/tree',
    method: 'get'
  })
}

/** 新增菜单 */
export function createMenuApi(data) {
  return request({
    url: '/api/menu',
    method: 'post',
    data
  })
}

/** 更新菜单 */
export function updateMenuApi(menuId, data) {
  return request({
    url: `/api/menu/${menuId}`,
    method: 'put',
    data
  })
}

/** 删除菜单 */
export function deleteMenuApi(menuId) {
  return request({
    url: `/api/menu/${menuId}`,
    method: 'delete'
  })
}

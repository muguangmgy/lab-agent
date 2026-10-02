import request from '@/utils/request'

/** 角色列表（全量，供下拉） */
export function getRoleListApi(params) {
  return request({
    url: '/api/role/list',
    method: 'get',
    params
  })
}

/** 角色分页 */
export function getRolePageApi(params) {
  return request({
    url: '/api/role/page',
    method: 'get',
    params
  })
}

/** 新增角色 */
export function createRoleApi(data) {
  return request({
    url: '/api/role',
    method: 'post',
    data
  })
}

/** 更新角色 */
export function updateRoleApi(roleId, data) {
  return request({
    url: `/api/role/${roleId}`,
    method: 'put',
    data
  })
}

/** 删除角色 */
export function deleteRoleApi(roleId) {
  return request({
    url: `/api/role/${roleId}`,
    method: 'delete'
  })
}

/** 更新角色菜单绑定 */
export function updateRoleMenusApi(roleId, menuIds) {
  return request({
    url: `/api/role/${roleId}/menus`,
    method: 'put',
    data: { menu_ids: menuIds }
  })
}

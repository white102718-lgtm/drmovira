package com.adpulse.system.role.service;

import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.role.dto.RoleDetail;
import com.adpulse.system.role.dto.RoleSaveRequest;
import com.adpulse.system.role.mapper.RoleMapper;
import com.adpulse.system.role.model.Role;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 角色与菜单权限分配服务。 */
@Service
public class RoleService {

    private final RoleMapper mapper;

    public RoleService(RoleMapper mapper) {
        this.mapper = mapper;
    }

    /** 分页查询角色。 */
    public PageResult<Role> page(String keyword, Integer status, int page, int pageSize) {
        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(pageSize, 1), 200);
        return new PageResult<>(
                mapper.findPage(keyword, status, (safePage - 1) * safeSize, safeSize),
                mapper.count(keyword, status),
                safePage,
                safeSize);
    }

    /** 查询角色详情。 */
    public RoleDetail detail(Long id) {
        Role role = requireRole(id);
        Set<String> menuIds =
                mapper.findMenuIds(id).stream().map(String::valueOf).collect(Collectors.toSet());
        return new RoleDetail(role, menuIds);
    }

    /** 新增角色并配置菜单权限。 */
    @Transactional
    public RoleDetail create(RoleSaveRequest request) {
        Long operatorId = SecurityContextHelper.currentUserId();
        Role role = new Role();
        apply(role, request);
        role.setCreatedBy(operatorId);
        role.setUpdatedBy(operatorId);
        try {
            mapper.insert(role);
        } catch (DuplicateKeyException exception) {
            throw BusinessException.conflict("角色编码已存在");
        }
        replaceMenus(role.getId(), request.menuIds(), operatorId);
        return detail(role.getId());
    }

    /** 修改角色并原子替换菜单权限。 */
    @Transactional
    public RoleDetail update(Long id, RoleSaveRequest request) {
        Role role = requireRole(id);
        apply(role, request);
        Long operatorId = SecurityContextHelper.currentUserId();
        role.setUpdatedBy(operatorId);
        try {
            mapper.update(role);
        } catch (DuplicateKeyException exception) {
            throw BusinessException.conflict("角色编码已存在");
        }
        replaceMenus(id, request.menuIds(), operatorId);
        return detail(id);
    }

    /** 没有用户引用时软删除角色。 */
    @Transactional
    public void delete(Long id) {
        requireRole(id);
        if (mapper.countUsers(id) > 0) {
            throw BusinessException.conflict("角色仍有关联用户，不能删除");
        }
        long deletedAt = System.currentTimeMillis();
        mapper.softDeleteMenuRelations(id, deletedAt);
        mapper.softDelete(id, deletedAt, SecurityContextHelper.currentUserId());
    }

    private void replaceMenus(Long roleId, Set<Long> menuIds, Long operatorId) {
        Set<Long> ids = menuIds == null ? Set.of() : menuIds;
        if (!ids.isEmpty() && mapper.countActiveMenus(ids) != ids.size()) {
            throw BusinessException.conflict("菜单权限包含不存在或已停用的菜单");
        }
        mapper.softDeleteMenuRelations(roleId, System.currentTimeMillis());
        if (!ids.isEmpty()) {
            mapper.batchInsertMenus(roleId, ids, operatorId);
        }
    }

    private Role requireRole(Long id) {
        Role role = mapper.findById(id);
        if (role == null) {
            throw BusinessException.notFound("角色");
        }
        return role;
    }

    private void apply(Role role, RoleSaveRequest request) {
        if (request.roleCode() == null || request.roleCode().isBlank()) {
            throw BusinessException.validation("角色编码不能为空");
        }
        if (request.roleCode().length() > 64) {
            throw BusinessException.validation("角色编码不能超过64个字符");
        }
        role.setRoleCode(request.roleCode().strip());
        role.setRoleName(request.roleName());
        role.setStatus(request.status());
        role.setSortOrder(request.sortOrder() == null ? 0 : request.sortOrder());
        role.setRemark(request.remark());
    }
}

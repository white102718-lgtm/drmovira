package com.adpulse.system.role.dto;

import com.adpulse.system.role.model.Role;
import java.util.Set;

/** 角色详情及其菜单权限。 */
public record RoleDetail(Role role, Set<String> menuIds) {}

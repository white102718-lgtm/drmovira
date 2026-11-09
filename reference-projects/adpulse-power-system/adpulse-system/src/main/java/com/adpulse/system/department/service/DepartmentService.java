package com.adpulse.system.department.service;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.department.dto.DepartmentSaveRequest;
import com.adpulse.system.department.mapper.DepartmentMapper;
import com.adpulse.system.department.model.Department;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 部门树维护与引用完整性服务。 */
@Service
public class DepartmentService {

    private final DepartmentMapper mapper;

    public DepartmentService(DepartmentMapper mapper) {
        this.mapper = mapper;
    }

    /** 查询完整部门树。 */
    public List<Department> tree() {
        List<Department> departments = mapper.findAllActive();
        Map<Long, Department> index = new LinkedHashMap<>();
        departments.forEach(
                department -> {
                    department.setChildren(new ArrayList<>());
                    index.put(department.getId(), department);
                });
        List<Department> roots = new ArrayList<>();
        for (Department department : departments) {
            Department parent = index.get(department.getParentId());
            if (department.getParentId() == 0 || parent == null) {
                roots.add(department);
            } else {
                parent.getChildren().add(department);
            }
        }
        return roots;
    }

    /** 新增部门并在取得主键后写入物化路径。 */
    @Transactional
    public Department create(DepartmentSaveRequest request) {
        Long operatorId = SecurityContextHelper.currentUserId();
        Department parent = resolveParent(request.parentId());
        Department department = fromRequest(request);
        department.setLevel(parent == null ? 1 : parent.getLevel() + 1);
        department.setCreatedBy(operatorId);
        department.setUpdatedBy(operatorId);
        mapper.insert(department);
        department.setPath((parent == null ? "/" : parent.getPath()) + department.getId() + "/");
        mapper.update(department);
        return mapper.findById(department.getId());
    }

    /** 修改部门；发生移动时同步更新整个子树路径和层级。 */
    @Transactional
    public Department update(Long id, DepartmentSaveRequest request) {
        Department current = requireDepartment(id);
        rejectFeishuManaged(current);
        Department parent = resolveParent(request.parentId());
        if (parent != null && parent.getPath().startsWith(current.getPath())) {
            throw BusinessException.conflict("部门不能移动到自身或自身子部门下");
        }
        String oldPath = current.getPath();
        int oldLevel = current.getLevel();
        apply(current, request);
        current.setLevel(parent == null ? 1 : parent.getLevel() + 1);
        current.setPath((parent == null ? "/" : parent.getPath()) + id + "/");
        current.setUpdatedBy(SecurityContextHelper.currentUserId());
        mapper.update(current);
        if (!oldPath.equals(current.getPath())) {
            mapper.updateSubtreePath(
                    oldPath,
                    current.getPath(),
                    current.getLevel() - oldLevel,
                    current.getUpdatedBy());
        }
        return mapper.findById(id);
    }

    /** 在整棵子树没有有效用户或数据权限引用时软删除部门及其所有后代。 */
    @Transactional
    public void delete(Long id) {
        Department department = requireDepartment(id);
        rejectFeishuManaged(department);
        if (mapper.countSubtreeUsers(department.getPath()) > 0) {
            throw BusinessException.conflict("当前部门或下级部门仍有关联用户，不能删除");
        }
        if (mapper.countSubtreeScopes(department.getPath()) > 0) {
            throw BusinessException.conflict("当前部门或下级部门仍被数据权限引用，不能删除");
        }
        mapper.softDeleteSubtree(
                department.getPath(),
                System.currentTimeMillis(),
                SecurityContextHelper.currentUserId());
    }

    private Department requireDepartment(Long id) {
        Department department = mapper.findById(id);
        if (department == null) {
            throw BusinessException.notFound("部门");
        }
        return department;
    }

    private void rejectFeishuManaged(Department department) {
        if ("FEISHU".equals(department.getSourceType())) {
            throw BusinessException.conflict("飞书部门由组织同步维护，不能手工修改或删除");
        }
    }

    private Department resolveParent(Long parentId) {
        if (parentId == 0) {
            return null;
        }
        Department parent = requireDepartment(parentId);
        if (parent.getStatus() != 1) {
            throw BusinessException.conflict("不能在停用部门下维护子部门");
        }
        return parent;
    }

    private Department fromRequest(DepartmentSaveRequest request) {
        Department department = new Department();
        apply(department, request);
        return department;
    }

    private void apply(Department department, DepartmentSaveRequest request) {
        if (request.leaderUserId() != null && mapper.countActiveUser(request.leaderUserId()) != 1) {
            throw BusinessException.conflict("部门负责人不存在、已停用或已删除");
        }
        department.setParentId(request.parentId());
        department.setDeptCode(request.deptCode());
        department.setDeptName(request.deptName());
        department.setSortOrder(request.sortOrder() == null ? 0 : request.sortOrder());
        department.setLeaderUserId(request.leaderUserId());
        department.setStatus(request.status());
        department.setRemark(request.remark());
    }
}

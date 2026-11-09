package com.adpulse.system.department.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.department.dto.DepartmentSaveRequest;
import com.adpulse.system.department.mapper.DepartmentMapper;
import com.adpulse.system.department.model.Department;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 部门树组装测试。 */
@ExtendWith(MockitoExtension.class)
class DepartmentServiceTest {

    @Mock private DepartmentMapper mapper;
    @InjectMocks private DepartmentService service;

    @BeforeEach
    void setCurrentUser() {
        CurrentUser user = new CurrentUser(7L, "session", "测试用户", Set.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", Set.of()));
    }

    @AfterEach
    void clearCurrentUser() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldBuildDepartmentTree() {
        Department root = department(1L, 0L, "总部");
        Department child = department(2L, 1L, "增长中心");
        when(mapper.findAllActive()).thenReturn(List.of(root, child));

        List<Department> tree = service.tree();

        assertThat(tree).hasSize(1);
        assertThat(tree.getFirst().getChildren())
                .extracting(Department::getDeptName)
                .containsExactly("增长中心");
    }

    @Test
    void shouldRejectManualUpdateForFeishuDepartment() {
        Department department = department(2L, 1L, "飞书部门");
        department.setSourceType("FEISHU");
        when(mapper.findById(2L)).thenReturn(department);

        assertThatThrownBy(
                        () ->
                                service.update(
                                        2L,
                                        new DepartmentSaveRequest(
                                                0L, "CODE", "新名称", 0, null, 1, null)))
                .isInstanceOf(BusinessException.class)
                .hasMessage("飞书部门由组织同步维护，不能手工修改或删除");
    }

    @Test
    void shouldSoftDeleteWholeSubtreeWhenItHasNoReferences() {
        Department department = department(1L, 0L, "总部");
        department.setPath("/1/");
        when(mapper.findById(1L)).thenReturn(department);
        when(mapper.countSubtreeUsers("/1/")).thenReturn(0);
        when(mapper.countSubtreeScopes("/1/")).thenReturn(0);

        service.delete(1L);

        verify(mapper)
                .softDeleteSubtree(
                        org.mockito.ArgumentMatchers.eq("/1/"),
                        anyLong(),
                        org.mockito.ArgumentMatchers.eq(7L));
    }

    @Test
    void shouldRejectSubtreeDeletionWhenDescendantHasUser() {
        Department department = department(1L, 0L, "总部");
        department.setPath("/1/");
        when(mapper.findById(1L)).thenReturn(department);
        when(mapper.countSubtreeUsers("/1/")).thenReturn(1);

        assertThatThrownBy(() -> service.delete(1L))
                .isInstanceOf(BusinessException.class)
                .hasMessage("当前部门或下级部门仍有关联用户，不能删除");
        verify(mapper, never())
                .softDeleteSubtree(
                        org.mockito.ArgumentMatchers.anyString(),
                        anyLong(),
                        org.mockito.ArgumentMatchers.anyLong());
    }

    private Department department(Long id, Long parentId, String name) {
        Department department = new Department();
        department.setId(id);
        department.setParentId(parentId);
        department.setDeptName(name);
        return department;
    }
}

package com.adpulse.system.role.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.role.dto.RoleSaveRequest;
import com.adpulse.system.role.mapper.RoleMapper;
import com.adpulse.system.role.model.Role;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 手动角色编码保存和唯一性约束测试。 */
@ExtendWith(MockitoExtension.class)
class RoleServiceTest {

    @Mock private RoleMapper mapper;
    @InjectMocks private RoleService service;

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
    void shouldCreateWithUserProvidedCode() {
        doAnswer(
                        invocation -> {
                            ((Role) invocation.getArgument(0)).setId(10L);
                            return 1;
                        })
                .when(mapper)
                .insert(any(Role.class));
        Role stored = new Role();
        stored.setId(10L);
        stored.setRoleCode("OPS");
        when(mapper.findById(10L)).thenReturn(stored);
        when(mapper.findMenuIds(10L)).thenReturn(Set.of());

        assertThat(service.create(request()).role().getRoleCode()).isEqualTo("OPS");
        ArgumentCaptor<Role> roleCaptor = ArgumentCaptor.forClass(Role.class);
        verify(mapper).insert(roleCaptor.capture());
        assertThat(roleCaptor.getValue().getRoleCode()).isEqualTo("OPS");
    }

    @Test
    void shouldUpdateExistingRoleCode() {
        Role existing = new Role();
        existing.setId(10L);
        existing.setRoleCode("AUTO_MZDT8K3P_0001");
        when(mapper.findById(10L)).thenReturn(existing);
        when(mapper.findMenuIds(10L)).thenReturn(Set.of());

        service.update(10L, request());

        ArgumentCaptor<Role> roleCaptor = ArgumentCaptor.forClass(Role.class);
        verify(mapper).update(roleCaptor.capture());
        assertThat(roleCaptor.getValue().getRoleCode()).isEqualTo("OPS");
    }

    @Test
    void shouldRejectDuplicateCodeOnCreate() {
        doThrow(new DuplicateKeyException("duplicate")).when(mapper).insert(any(Role.class));
        assertThatThrownBy(() -> service.create(request()))
                .isInstanceOf(BusinessException.class)
                .hasMessage("角色编码已存在");
    }

    @Test
    void shouldRejectDuplicateCodeOnUpdate() {
        Role role = new Role();
        role.setId(10L);
        when(mapper.findById(10L)).thenReturn(role);
        doThrow(new DuplicateKeyException("duplicate")).when(mapper).update(any(Role.class));
        assertThatThrownBy(() -> service.update(10L, request()))
                .isInstanceOf(BusinessException.class)
                .hasMessage("角色编码已存在");
    }

    @Test
    void shouldRejectMissingBlankAndOverlongCodes() {
        for (String code : new String[] {null, "", "  ", "A".repeat(65)}) {
            RoleSaveRequest request = new RoleSaveRequest(code, "运营角色", 1, 0, null, Set.of());
            assertThatThrownBy(() -> service.create(request)).isInstanceOf(BusinessException.class);
        }
    }

    @Test
    void shouldAcceptMaximumLengthAndTrimCode() {
        Role role = new Role();
        role.setId(10L);
        when(mapper.findById(10L)).thenReturn(role);
        when(mapper.findMenuIds(10L)).thenReturn(Set.of());
        service.update(10L, new RoleSaveRequest("A".repeat(64), "运营角色", 1, 0, null, Set.of()));
        assertThat(role.getRoleCode()).hasSize(64);
        service.update(10L, new RoleSaveRequest(" OPS ", "运营角色", 1, 0, null, Set.of()));
        assertThat(role.getRoleCode()).isEqualTo("OPS");
    }

    @Test
    void shouldRejectIndirectChangesToAnotherSuperAdminRole() {
        when(mapper.findById(10L)).thenReturn(new Role());
        when(mapper.hasOtherSuperAdminUser(10L, 7L)).thenReturn(true);

        assertThatThrownBy(() -> service.update(10L, request()))
                .hasMessage("不能修改其他超级管理员关联的角色及菜单权限");
        assertThatThrownBy(() -> service.delete(10L)).hasMessage("不能修改其他超级管理员关联的角色及菜单权限");
        verify(mapper, org.mockito.Mockito.never()).update(any());
        verify(mapper, org.mockito.Mockito.never())
                .softDeleteMenuRelations(any(), org.mockito.ArgumentMatchers.anyLong());
    }

    private RoleSaveRequest request() {
        return new RoleSaveRequest("OPS", "运营角色", 1, 0, null, Set.of());
    }
}

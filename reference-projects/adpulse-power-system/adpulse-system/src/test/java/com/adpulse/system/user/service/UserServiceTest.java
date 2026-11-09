package com.adpulse.system.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.asset.service.AssetService;
import com.adpulse.system.auth.service.SessionStore;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.user.dto.UserPasswordChangeRequest;
import com.adpulse.system.user.dto.UserProfileUpdateRequest;
import com.adpulse.system.user.dto.UserSaveRequest;
import com.adpulse.system.user.mapper.UserMapper;
import com.adpulse.system.user.model.UserAccount;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;

/** 用户保存安全策略测试。 */
@ExtendWith(MockitoExtension.class)
class UserServiceTest {

    @Mock private UserMapper mapper;
    @Mock private PasswordEncoder passwordEncoder;
    @Mock private SessionStore sessionStore;
    @Mock private AssetService assetService;
    @Mock private UserDepartureFeishuNotifier departureFeishuNotifier;
    @InjectMocks private UserService service;

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
    void shouldRejectDuplicateEnglishNicknameBeforeCreatingUser() {
        when(mapper.existsByEnglishNickname("Alice", null)).thenReturn(true);

        assertThatThrownBy(() -> service.create(requestWithNickname(" Alice ")))
                .isInstanceOf(BusinessException.class)
                .hasMessage("英文昵称已存在");

        verify(mapper, never()).insert(any());
        verify(passwordEncoder, never()).encode(any());
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {"   ", " Alice "})
    void shouldCreateUserWithAvailableOrEmptyNickname(String nickname) {
        doAnswer(
                        invocation -> {
                            UserAccount user = invocation.getArgument(0);
                            user.setId(9L);
                            when(mapper.findById(9L)).thenReturn(user);
                            return 1;
                        })
                .when(mapper)
                .insert(any());

        service.create(requestWithNickname(nickname));

        var captor = org.mockito.ArgumentCaptor.forClass(UserAccount.class);
        verify(mapper).insert(captor.capture());
        assertThat(captor.getValue().getEnglishNickname())
                .isEqualTo(nickname == null || nickname.isBlank() ? null : "Alice");
        if (nickname == null || nickname.isBlank()) {
            verify(mapper, never()).existsByEnglishNickname(any(), any());
        } else {
            verify(mapper).existsByEnglishNickname("Alice", null);
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {"LOCAL", "FEISHU"})
    void shouldRejectDuplicateEnglishNicknameWhenEditingUser(String sourceType) {
        UserAccount user = new UserAccount();
        user.setId(9L);
        user.setSourceType(sourceType);
        when(mapper.findById(9L)).thenReturn(user);
        when(mapper.existsByEnglishNickname("Alice", 9L)).thenReturn(true);

        assertThatThrownBy(() -> service.update(9L, requestWithNickname("Alice")))
                .isInstanceOf(BusinessException.class)
                .hasMessage("英文昵称已存在");

        verify(mapper, never()).update(any());
        verify(mapper, never()).updateFeishuLocalFields(any());
    }

    @Test
    void shouldRejectDuplicateEnglishNicknameWhenUpdatingProfile() {
        when(mapper.findById(7L)).thenReturn(new UserAccount());
        when(mapper.existsByEnglishNickname("Alice", 7L)).thenReturn(true);

        assertThatThrownBy(
                        () ->
                                service.updateCurrentProfile(
                                        new UserProfileUpdateRequest(
                                                "名称", " Alice ", null, null, null)))
                .isInstanceOf(BusinessException.class)
                .hasMessage("英文昵称已存在");

        verify(mapper, never()).updateProfile(any());
    }

    @Test
    void shouldRejectGlobalOnlyModeWhenNoGlobalRuleExists() {
        when(mapper.countActiveGlobalIpRules()).thenReturn(0);

        assertThatThrownBy(() -> service.create(requestWithIpMode(1)))
                .isInstanceOf(BusinessException.class)
                .hasMessage("仅通用白名单模式至少需要一条通用IP规则");
    }

    @Test
    void shouldRejectProfilePasswordChangeWhenOldPasswordIsWrong() {
        UserAccount user = new UserAccount();
        user.setId(7L);
        user.setPasswordHash("hash");
        when(mapper.findById(7L)).thenReturn(user);
        when(passwordEncoder.matches("wrong-password", "hash")).thenReturn(false);

        assertThatThrownBy(
                        () ->
                                service.changeCurrentPassword(
                                        new UserPasswordChangeRequest(
                                                "wrong-password", "new-password")))
                .isInstanceOf(BusinessException.class)
                .hasMessage("旧密码不正确");

        verify(mapper, never()).updateProfile(user);
        verify(sessionStore, never()).revokeUser(7L);
    }

    @Test
    void shouldChangeCurrentPasswordAndRevokeSessions() {
        UserAccount user = new UserAccount();
        user.setId(7L);
        user.setPasswordHash("hash");
        when(mapper.findById(7L)).thenReturn(user);
        when(passwordEncoder.matches("old-password", "hash")).thenReturn(true);
        when(passwordEncoder.matches("new-password", "hash")).thenReturn(false);
        when(passwordEncoder.encode("new-password")).thenReturn("new-hash");

        service.changeCurrentPassword(
                new UserPasswordChangeRequest("old-password", "new-password"));

        verify(mapper).updatePassword(7L, "new-hash", 7L);
        verify(sessionStore).revokeUser(7L);
    }

    @ParameterizedTest
    @ValueSource(strings = {"legacy-feishu", "new-feishu", "empty"})
    void shouldSetFirstPasswordWithoutOldPassword(String scenario) {
        UserAccount user = new UserAccount();
        user.setId(7L);
        user.setCreatedAt(LocalDateTime.of(2026, 9, 1, 0, 0));
        if (!"empty".equals(scenario)) {
            user.setSourceType("FEISHU");
            user.setPasswordHash("random-placeholder-hash");
        }
        if ("legacy-feishu".equals(scenario)) {
            user.setPasswordChangedAt(user.getCreatedAt());
        }
        when(mapper.findById(7L)).thenReturn(user);
        when(passwordEncoder.encode("new-password")).thenReturn("new-hash");

        assertThat(service.currentProfile().hasPassword()).isFalse();
        service.changeCurrentPassword(new UserPasswordChangeRequest(null, "new-password"));

        verify(passwordEncoder, never()).matches(any(), any());
        verify(mapper).updatePassword(7L, "new-hash", 7L);
        verify(sessionStore).revokeUser(7L);
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {"   ", "wrong-password"})
    void shouldRequireOldPasswordForFeishuUserAfterPasswordWasSet(String oldPassword) {
        UserAccount user = new UserAccount();
        user.setId(7L);
        user.setSourceType("FEISHU");
        user.setPasswordHash("hash");
        user.setCreatedAt(LocalDateTime.of(2026, 9, 1, 0, 0));
        user.setPasswordChangedAt(user.getCreatedAt().plusDays(1));
        when(mapper.findById(7L)).thenReturn(user);

        assertThat(service.currentProfile().hasPassword()).isTrue();
        assertThatThrownBy(
                        () ->
                                service.changeCurrentPassword(
                                        new UserPasswordChangeRequest(oldPassword, "new-password")))
                .isInstanceOf(BusinessException.class)
                .hasMessage("旧密码不正确");
        verify(mapper, never()).updatePassword(any(), any(), any());
        verify(sessionStore, never()).revokeUser(any());
    }

    @Test
    void shouldRejectUnchangedPassword() {
        UserAccount user = new UserAccount();
        user.setPasswordHash("hash");
        when(mapper.findById(7L)).thenReturn(user);
        when(passwordEncoder.matches("password", "hash")).thenReturn(true);

        assertThatThrownBy(
                        () ->
                                service.changeCurrentPassword(
                                        new UserPasswordChangeRequest("password", "password")))
                .isInstanceOf(BusinessException.class)
                .hasMessage("新密码不能与旧密码相同");
        verify(mapper, never()).updatePassword(any(), any(), any());
        verify(sessionStore, never()).revokeUser(any());
    }

    @Test
    void shouldUpdateFeishuLocalFieldsAndPreserveOrganizationFields() {
        UserAccount user = new UserAccount();
        user.setId(9L);
        user.setSourceType("FEISHU");
        user.setPhone("+8613800000000");
        user.setPrimaryDepartmentId(20L);
        user.setStatus(1);
        user.setIpAccessMode(0);
        when(mapper.findById(9L)).thenReturn(user);
        when(mapper.countActiveRoles(Set.of(3L))).thenReturn(1);
        when(mapper.findRoleIds(9L)).thenReturn(Set.of(3L));
        when(mapper.findDepartmentScopes(9L)).thenReturn(List.of());
        when(mapper.findPersonalIpCidrs(9L)).thenReturn(Set.of());

        UserSaveRequest request =
                new UserSaveRequest(
                        "+14155552671",
                        null,
                        "修改后的名称",
                        "nickname",
                        "真实姓名",
                        99L,
                        "user@example.com",
                        null,
                        1,
                        0,
                        "备注",
                        Set.of(3L),
                        Set.of(),
                        Set.of());

        service.update(9L, request);

        verify(mapper).updateFeishuLocalFields(user);
        verify(mapper, never()).update(user);
        verify(mapper, never())
                .softDeleteScopes(
                        org.mockito.ArgumentMatchers.eq(9L),
                        org.mockito.ArgumentMatchers.anyLong());
        verify(mapper).batchInsertRoles(9L, Set.of(3L), 7L);
        org.assertj.core.api.Assertions.assertThat(user.getPhone()).isEqualTo("+8613800000000");
        org.assertj.core.api.Assertions.assertThat(user.getPrimaryDepartmentId()).isEqualTo(20L);
        org.assertj.core.api.Assertions.assertThat(user.getDisplayName()).isEqualTo("修改后的名称");
    }

    @Test
    void shouldAllowFeishuUserToUpdateCurrentProfile() {
        UserAccount user = new UserAccount();
        user.setId(7L);
        user.setSourceType("FEISHU");
        user.setStatus(1);
        when(mapper.findById(7L)).thenReturn(user);
        user.setEnglishNickname("English");
        when(mapper.updateProfile(user)).thenReturn(1);
        when(mapper.findDepartmentNames(7L)).thenReturn(List.of());
        when(mapper.findRoleNames(7L)).thenReturn(List.of());

        service.updateCurrentProfile(
                new UserProfileUpdateRequest("个人名称", "English", "真实姓名", "user@example.com", null));

        verify(mapper).updateProfile(user);
        verify(mapper).existsByEnglishNickname("English", 7L);
        org.assertj.core.api.Assertions.assertThat(user.getDisplayName()).isEqualTo("个人名称");
    }

    @Test
    void shouldPassRoleFilterToUserPageQuery() {
        service.page("名称", 1, 2L, 3L, 2, 20);

        verify(mapper).findPage("名称", 1, 2L, 3L, 20, 20);
        verify(mapper).count("名称", 1, 2L, 3L);
    }

    @ParameterizedTest
    @ValueSource(ints = {999_999, 1_000_000})
    void shouldUseFullOptionPageSizeAsUpperBound(int requestedPageSize) {
        var result = service.page(null, null, null, null, 1, requestedPageSize);

        assertThat(result.pageSize()).isEqualTo(999_999);
        verify(mapper).findPage(null, null, null, null, 0, 999_999);
    }

    @Test
    void shouldReleaseAssetsWhenDisablingUser() {
        UserAccount user = new UserAccount();
        user.setId(9L);
        user.setStatus(1);
        user.setIpAccessMode(0);
        when(mapper.findById(9L)).thenReturn(user);
        when(mapper.findRoleIds(9L)).thenReturn(Set.of());
        when(mapper.findDepartmentScopes(9L)).thenReturn(List.of());
        when(mapper.findPersonalIpCidrs(9L)).thenReturn(Set.of());

        service.update(9L, requestWithStatus(0));

        verify(assetService).releaseAssetsForDepartingUser(9L, 7L);
        verify(departureFeishuNotifier).notify(user, "停用");
        verify(sessionStore).revokeUser(9L);
    }

    @Test
    void shouldReleaseAssetsBeforeSoftDeletingUser() {
        UserAccount user = new UserAccount();
        user.setId(9L);
        user.setSourceType("LOCAL");
        when(mapper.findById(9L)).thenReturn(user);

        service.delete(9L);

        verify(assetService).releaseAssetsForDepartingUser(9L, 7L);
        verify(departureFeishuNotifier).notify(user, "删除");
        verify(mapper)
                .softDelete(
                        org.mockito.ArgumentMatchers.eq(9L),
                        org.mockito.ArgumentMatchers.anyLong(),
                        org.mockito.ArgumentMatchers.eq(7L));
        verify(sessionStore).revokeUser(9L);
    }

    @Test
    void shouldRejectAllAdministrativeWritesToAnotherSuperAdmin() {
        UserAccount user = new UserAccount();
        user.setId(9L);
        user.setSuperAdmin(true);
        when(mapper.findById(9L)).thenReturn(user);

        assertThatThrownBy(() -> service.update(9L, requestWithStatus(1)))
                .hasMessage("仅账户本人可以修改超级管理员账户");
        assertThatThrownBy(() -> service.updateAuthorization(9L, null))
                .hasMessage("仅账户本人可以修改超级管理员账户");
        assertThatThrownBy(() -> service.resetPassword(9L, "newPassword123"))
                .hasMessage("仅账户本人可以修改超级管理员账户");
        assertThatThrownBy(() -> service.resetMfa(9L)).hasMessage("仅账户本人可以修改超级管理员账户");
        assertThatThrownBy(() -> service.delete(9L)).hasMessage("超级管理员账户不能删除");
        verify(mapper, org.mockito.Mockito.times(5)).findById(9L);
        org.mockito.Mockito.verifyNoMoreInteractions(mapper);
        org.mockito.Mockito.verifyNoInteractions(passwordEncoder, sessionStore, assetService);
    }

    @Test
    void shouldRejectSuperAdminDisablingOrDeletingSelf() {
        UserAccount user = new UserAccount();
        user.setId(7L);
        user.setSuperAdmin(true);
        when(mapper.findById(7L)).thenReturn(user);

        assertThatThrownBy(() -> service.update(7L, requestWithStatus(0)))
                .hasMessage("超级管理员账户不能停用");
        assertThatThrownBy(() -> service.delete(7L)).hasMessage("超级管理员账户不能删除");
        verify(mapper, never()).update(any());
        org.mockito.Mockito.verifyNoInteractions(sessionStore, assetService);
    }

    @Test
    void shouldAllowSuperAdminToEditOwnAccountWithoutLosingIdentity() {
        UserAccount user = new UserAccount();
        user.setId(7L);
        user.setSuperAdmin(true);
        user.setStatus(1);
        user.setIpAccessMode(0);
        when(mapper.findById(7L)).thenReturn(user);

        service.update(7L, requestWithStatus(1));

        verify(mapper).update(user);
        assertThat(user.isSuperAdmin()).isTrue();
        org.mockito.Mockito.verifyNoInteractions(sessionStore, assetService);
    }

    private UserSaveRequest requestWithNickname(String nickname) {
        return new UserSaveRequest(
                "13800000000",
                "password123",
                "测试用户",
                nickname,
                null,
                null,
                null,
                null,
                1,
                0,
                null,
                Set.of(),
                Set.of(),
                Set.of());
    }

    private UserSaveRequest requestWithIpMode(int ipAccessMode) {
        return new UserSaveRequest(
                "13800000000",
                "password123",
                "测试用户",
                null,
                null,
                null,
                null,
                null,
                1,
                ipAccessMode,
                null,
                Set.of(),
                Set.of(),
                Set.of());
    }

    private UserSaveRequest requestWithStatus(int status) {
        return new UserSaveRequest(
                "13800000000",
                null,
                "测试用户",
                null,
                null,
                null,
                null,
                null,
                status,
                0,
                null,
                Set.of(),
                Set.of(),
                Set.of());
    }
}

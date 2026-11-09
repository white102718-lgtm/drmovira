package com.adpulse.system.user.service;

import com.adpulse.system.asset.service.AssetService;
import com.adpulse.system.auth.service.SessionStore;
import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.common.util.PhoneNumberNormalizer;
import com.adpulse.system.user.dto.DepartmentScopeRequest;
import com.adpulse.system.user.dto.UserAuthorizationRequest;
import com.adpulse.system.user.dto.UserDetail;
import com.adpulse.system.user.dto.UserPasswordChangeRequest;
import com.adpulse.system.user.dto.UserProfileResponse;
import com.adpulse.system.user.dto.UserProfileUpdateRequest;
import com.adpulse.system.user.dto.UserSaveRequest;
import com.adpulse.system.user.mapper.UserMapper;
import com.adpulse.system.user.model.UserAccount;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.util.matcher.IpAddressMatcher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/** 用户主数据及角色、部门范围、IP规则的聚合服务。 */
@Service
public class UserService {

    private static final int MAX_PAGE_SIZE = 999_999;

    private final UserMapper mapper;
    private final PasswordEncoder passwordEncoder;
    private final SessionStore sessionStore;
    private final AssetService assetService;
    private final UserDepartureFeishuNotifier departureFeishuNotifier;

    public UserService(
            UserMapper mapper,
            PasswordEncoder passwordEncoder,
            SessionStore sessionStore,
            AssetService assetService,
            UserDepartureFeishuNotifier departureFeishuNotifier) {
        this.mapper = mapper;
        this.passwordEncoder = passwordEncoder;
        this.sessionStore = sessionStore;
        this.assetService = assetService;
        this.departureFeishuNotifier = departureFeishuNotifier;
    }

    /** 分页查询用户。 */
    public PageResult<UserAccount> page(
            String keyword,
            Integer status,
            Long departmentId,
            Long roleId,
            int page,
            int pageSize) {
        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(pageSize, 1), MAX_PAGE_SIZE);
        return new PageResult<>(
                mapper.findPage(
                        keyword, status, departmentId, roleId, (safePage - 1) * safeSize, safeSize),
                mapper.count(keyword, status, departmentId, roleId),
                safePage,
                safeSize);
    }

    /** 查询用户及全部系统管理关系。 */
    public UserDetail detail(Long id) {
        UserAccount user = requireUser(id);
        Set<String> roleIds =
                mapper.findRoleIds(id).stream().map(String::valueOf).collect(Collectors.toSet());
        return new UserDetail(
                user, roleIds, mapper.findDepartmentScopes(id), mapper.findPersonalIpCidrs(id));
    }

    /** 查询当前登录用户可展示的个人资料。 */
    public UserProfileResponse currentProfile() {
        Long userId = SecurityContextHelper.currentUserId();
        UserAccount user = requireUser(userId);
        String department = null;
        if (user.getPrimaryDepartmentId() != null) {
            department = mapper.findDepartmentName(user.getPrimaryDepartmentId());
        }
        return new UserProfileResponse(
                userId.toString(),
                user.getUsername(),
                user.getPhone(),
                user.getDisplayName(),
                user.getEnglishNickname(),
                user.getRealName(),
                user.getEmail(),
                user.getAvatarUrl(),
                department,
                mapper.findDepartmentNames(userId),
                mapper.findRoleNames(userId),
                hasPassword(user));
    }

    /** 修改当前登录用户资料。 */
    @Transactional
    public UserProfileResponse updateCurrentProfile(UserProfileUpdateRequest request) {
        Long userId = SecurityContextHelper.currentUserId();
        UserAccount user = requireUser(userId);
        validateEnglishNickname(request.englishNickname(), userId);
        user.setDisplayName(request.displayName().trim());
        user.setEnglishNickname(blankToNull(request.englishNickname()));
        user.setRealName(blankToNull(request.realName()));
        user.setEmail(blankToNull(request.email()));
        user.setAvatarUrl(blankToNull(request.avatarUrl()));
        user.setUpdatedBy(userId);
        if (mapper.updateProfile(user) != 1) {
            throw BusinessException.conflict("用户已停用或不存在");
        }
        return currentProfile();
    }

    /** 首次设置密码无需旧密码；已有密码必须校验，并撤销该用户的全部会话。 */
    @Transactional
    public void changeCurrentPassword(UserPasswordChangeRequest request) {
        Long userId = SecurityContextHelper.currentUserId();
        UserAccount user = requireUser(userId);
        if (hasPassword(user)) {
            if (!StringUtils.hasText(request.oldPassword())
                    || !passwordEncoder.matches(request.oldPassword(), user.getPasswordHash())) {
                throw BusinessException.validation("旧密码不正确");
            }
            if (passwordEncoder.matches(request.newPassword(), user.getPasswordHash())) {
                throw BusinessException.validation("新密码不能与旧密码相同");
            }
        }
        mapper.updatePassword(userId, passwordEncoder.encode(request.newPassword()), userId);
        sessionStore.revokeUser(userId);
    }

    private boolean hasPassword(UserAccount user) {
        // 历史飞书同步在同一 INSERT 中写入创建时间和密码时间，随机占位密码不算用户设置。
        boolean feishuInitialPassword =
                "REDACTED_REFERENCE_SECRET".equals(user.getSourceType())
                        && (user.getPasswordChangedAt() == null
                                || user.getPasswordChangedAt().equals(user.getCreatedAt()));
        return StringUtils.hasText(user.getPasswordHash()) && !feishuInitialPassword;
    }

    /** 新建用户并原子写入关联关系。 */
    @Transactional
    public UserDetail create(UserSaveRequest request) {
        if (!StringUtils.hasText(request.password())) {
            throw BusinessException.validation("新建用户必须设置初始密码");
        }
        validateRelations(request);
        validateEnglishNickname(request.englishNickname(), null);
        UserAccount user = new UserAccount();
        apply(user, request);
        user.setPasswordHash(passwordEncoder.encode(request.password()));
        Long operatorId = SecurityContextHelper.currentUserId();
        user.setCreatedBy(operatorId);
        user.setUpdatedBy(operatorId);
        mapper.insert(user);
        replaceRelations(user.getId(), request, operatorId);
        return detail(user.getId());
    }

    /** 修改用户与关联关系；安全状态变化后撤销全部会话。 */
    @Transactional
    public UserDetail update(Long id, UserSaveRequest request) {
        UserAccount user = requireUser(id);
        requireAccountOwnerIfSuperAdmin(user);
        if (user.isSuperAdmin() && !Integer.valueOf(1).equals(request.status())) {
            throw BusinessException.conflict("超级管理员账户不能停用");
        }
        boolean feishuManaged = "FEISHU".equals(user.getSourceType());
        validateEnglishNickname(request.englishNickname(), id);
        int oldStatus = user.getStatus();
        int oldIpMode = user.getIpAccessMode();
        validateRelations(request, !feishuManaged);
        apply(user, request, !feishuManaged);
        Long operatorId = SecurityContextHelper.currentUserId();
        user.setUpdatedBy(operatorId);
        if (feishuManaged) {
            mapper.updateFeishuLocalFields(user);
        } else {
            mapper.update(user);
        }
        if (StringUtils.hasText(request.password())) {
            mapper.updatePassword(id, passwordEncoder.encode(request.password()), operatorId);
        }
        replaceRelations(id, request, operatorId, !feishuManaged);
        if (oldStatus == 1 && request.status() == 0) {
            // 停用即视为离职处理，释放独占资产并移除该人员的共享使用关系。
            assetService.releaseAssetsForDepartingUser(id, operatorId);
            departureFeishuNotifier.notify(user, "停用");
        }
        if (oldStatus != request.status()
                || oldIpMode != request.ipAccessMode()
                || StringUtils.hasText(request.password())) {
            sessionStore.revokeUser(id);
        }
        return detail(id);
    }

    /** 仅维护飞书用户的本地权限关系，不覆盖飞书托管的组织资料。 */
    @Transactional
    public UserDetail updateAuthorization(Long id, UserAuthorizationRequest request) {
        UserAccount user = requireUser(id);
        requireAccountOwnerIfSuperAdmin(user);
        if (!"FEISHU".equals(user.getSourceType())) {
            throw BusinessException.conflict("本地用户请使用普通编辑接口维护");
        }
        UserSaveRequest validationRequest =
                new UserSaveRequest(
                        user.getPhone(),
                        null,
                        user.getDisplayName(),
                        user.getEnglishNickname(),
                        user.getRealName(),
                        user.getPrimaryDepartmentId(),
                        user.getEmail(),
                        user.getAvatarUrl(),
                        user.getStatus(),
                        request.ipAccessMode(),
                        user.getRemark(),
                        request.roleIds(),
                        request.departmentScopes(),
                        request.ipCidrs());
        validateRelations(validationRequest);
        Long operatorId = SecurityContextHelper.currentUserId();
        int oldIpMode = user.getIpAccessMode();
        user.setIpAccessMode(request.ipAccessMode());
        user.setUpdatedBy(operatorId);
        mapper.updateFeishuLocalFields(user);
        replaceRelations(id, validationRequest, operatorId);
        if (oldIpMode != request.ipAccessMode()) sessionStore.revokeUser(id);
        return detail(id);
    }

    /** 重置用户密码并撤销该用户全部会话。 */
    @Transactional
    public void resetPassword(Long id, String newPassword) {
        requireAccountOwnerIfSuperAdmin(requireUser(id));
        mapper.updatePassword(
                id, passwordEncoder.encode(newPassword), SecurityContextHelper.currentUserId());
        sessionStore.revokeUser(id);
    }

    /** 清理用户MFA绑定并撤销全部会话。 */
    @Transactional
    public void resetMfa(Long id) {
        requireAccountOwnerIfSuperAdmin(requireUser(id));
        mapper.resetMfa(id, SecurityContextHelper.currentUserId());
        sessionStore.revokeUser(id);
    }

    /** 软删除用户和全部系统管理关系。 */
    @Transactional
    public void delete(Long id) {
        UserAccount user = requireUser(id);
        if (user.isSuperAdmin()) {
            throw BusinessException.conflict("超级管理员账户不能删除");
        }
        if ("FEISHU".equals(user.getSourceType())) {
            throw BusinessException.conflict("飞书用户由组织同步维护，不能手工删除");
        }
        if (SecurityContextHelper.currentUserId().equals(id)) {
            throw BusinessException.conflict("不能删除当前登录用户");
        }
        long deletedAt = System.currentTimeMillis();
        Long operatorId = SecurityContextHelper.currentUserId();
        assetService.releaseAssetsForDepartingUser(id, operatorId);
        departureFeishuNotifier.notify(user, "删除");
        mapper.softDeleteRoles(id, deletedAt);
        mapper.softDeleteScopes(id, deletedAt);
        mapper.softDeletePersonalIps(id, deletedAt);
        mapper.softDelete(id, deletedAt, operatorId);
        sessionStore.revokeUser(id);
    }

    private void validateRelations(UserSaveRequest request) {
        validateRelations(request, true);
    }

    private void validateRelations(UserSaveRequest request, boolean validateOrganizationFields) {
        if (validateOrganizationFields
                && request.primaryDepartmentId() != null
                && mapper.countActiveDepartment(request.primaryDepartmentId()) != 1) {
            throw BusinessException.conflict("主部门不存在、已停用或已删除");
        }
        Set<Long> roleIds = request.roleIds() == null ? Set.of() : request.roleIds();
        if (!roleIds.isEmpty() && mapper.countActiveRoles(roleIds) != roleIds.size()) {
            throw BusinessException.conflict("角色包含不存在、已停用或已删除的数据");
        }
        if (validateOrganizationFields) {
            Set<DepartmentScopeRequest> scopes =
                    request.departmentScopes() == null ? Set.of() : request.departmentScopes();
            Set<Long> departmentIds =
                    scopes.stream()
                            .map(DepartmentScopeRequest::departmentId)
                            .collect(Collectors.toSet());
            if (!departmentIds.isEmpty()
                    && mapper.countActiveDepartments(departmentIds) != departmentIds.size()) {
                throw BusinessException.conflict("部门范围包含不存在、已停用或已删除的数据");
            }
        }
        Set<String> cidrs = request.ipCidrs() == null ? Set.of() : request.ipCidrs();
        for (String cidr : cidrs) {
            try {
                new IpAddressMatcher(cidr);
            } catch (IllegalArgumentException exception) {
                throw BusinessException.validation("非法IP或CIDR: " + cidr);
            }
        }
        if (request.ipAccessMode() == 1 && mapper.countActiveGlobalIpRules() == 0) {
            throw BusinessException.conflict("仅通用白名单模式至少需要一条通用IP规则");
        }
        if (request.ipAccessMode() == 2
                && cidrs.isEmpty()
                && mapper.countActiveGlobalIpRules() == 0) {
            throw BusinessException.conflict("白名单模式至少需要一条个人或通用IP规则");
        }
    }

    private void replaceRelations(Long userId, UserSaveRequest request, Long operatorId) {
        replaceRelations(userId, request, operatorId, true);
    }

    private void replaceRelations(
            Long userId,
            UserSaveRequest request,
            Long operatorId,
            boolean replaceDepartmentScopes) {
        long deletedAt = System.currentTimeMillis();
        Set<Long> roleIds = request.roleIds() == null ? Set.of() : request.roleIds();
        mapper.softDeleteRoles(userId, deletedAt);
        if (!roleIds.isEmpty()) {
            mapper.batchInsertRoles(userId, roleIds, operatorId);
        }

        if (replaceDepartmentScopes) {
            Set<DepartmentScopeRequest> scopes =
                    request.departmentScopes() == null
                            ? Set.of()
                            : new LinkedHashSet<>(request.departmentScopes());
            mapper.softDeleteScopes(userId, deletedAt);
            if (!scopes.isEmpty()) {
                mapper.batchInsertScopes(userId, scopes, operatorId);
            }
        }

        Set<String> cidrs = request.ipCidrs() == null ? Set.of() : request.ipCidrs();
        mapper.softDeletePersonalIps(userId, deletedAt);
        if (!cidrs.isEmpty()) {
            mapper.batchInsertPersonalIps(userId, cidrs, operatorId);
        }
    }

    private void requireAccountOwnerIfSuperAdmin(UserAccount user) {
        if (user.isSuperAdmin() && !user.getId().equals(SecurityContextHelper.currentUserId())) {
            throw BusinessException.conflict("仅账户本人可以修改超级管理员账户");
        }
    }

    private UserAccount requireUser(Long id) {
        UserAccount user = mapper.findById(id);
        if (user == null) {
            throw BusinessException.notFound("用户");
        }
        return user;
    }

    private void apply(UserAccount user, UserSaveRequest request) {
        apply(user, request, true);
    }

    private void apply(UserAccount user, UserSaveRequest request, boolean applyOrganizationFields) {
        if (applyOrganizationFields) {
            user.setPhone(PhoneNumberNormalizer.normalize(request.phone()));
            user.setPrimaryDepartmentId(request.primaryDepartmentId());
        }
        user.setDisplayName(request.displayName());
        user.setEnglishNickname(blankToNull(request.englishNickname()));
        user.setRealName(blankToNull(request.realName()));
        user.setEmail(blankToNull(request.email()));
        user.setAvatarUrl(blankToNull(request.avatarUrl()));
        user.setStatus(request.status());
        user.setIpAccessMode(request.ipAccessMode());
        user.setRemark(request.remark());
    }

    // 空昵称不参与唯一性约束；停用用户仍占用昵称，软删除后允许复用。
    private void validateEnglishNickname(String value, Long excludeId) {
        String nickname = blankToNull(value);
        if (nickname != null && mapper.existsByEnglishNickname(nickname, excludeId)) {
            throw BusinessException.conflict("英文昵称已存在");
        }
    }

    private String blankToNull(String value) {
        return StringUtils.hasText(value) ? value.trim() : null;
    }
}

package com.adpulse.system.auth.service;

import com.adpulse.system.auth.dto.LoginRequest;
import com.adpulse.system.auth.dto.LoginResponse;
import com.adpulse.system.auth.dto.MfaCodeRequest;
import com.adpulse.system.auth.mapper.AuthMapper;
import com.adpulse.system.auth.model.FeishuIdentity;
import com.adpulse.system.auth.model.MfaChallenge;
import com.adpulse.system.auth.model.ServerSession;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.common.util.PhoneNumberNormalizer;
import com.adpulse.system.config.SecurityProperties;
import com.adpulse.system.loginlog.model.LoginAuthStage;
import com.adpulse.system.loginlog.service.LoginLogService;
import com.adpulse.system.user.model.UserAccount;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.OptionalLong;
import java.util.Set;
import java.util.UUID;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 登录、登出与服务端会话生命周期服务。 */
@Service
public class AuthService {

    private final AuthMapper authMapper;
    private final PasswordEncoder passwordEncoder;
    private final IpAccessService ipAccessService;
    private final SessionStore sessionStore;
    private final JwtService jwtService;
    private final SecurityProperties properties;
    private final MfaChallengeStore mfaChallengeStore;
    private final MfaSecretCipher mfaSecretCipher;
    private final TotpService totpService;
    private final LoginLogService loginLogService;

    public AuthService(
            AuthMapper authMapper,
            PasswordEncoder passwordEncoder,
            IpAccessService ipAccessService,
            SessionStore sessionStore,
            JwtService jwtService,
            SecurityProperties properties,
            MfaChallengeStore mfaChallengeStore,
            MfaSecretCipher mfaSecretCipher,
            TotpService totpService,
            LoginLogService loginLogService) {
        this.authMapper = authMapper;
        this.passwordEncoder = passwordEncoder;
        this.ipAccessService = ipAccessService;
        this.sessionStore = sessionStore;
        this.jwtService = jwtService;
        this.properties = properties;
        this.mfaChallengeStore = mfaChallengeStore;
        this.mfaSecretCipher = mfaSecretCipher;
        this.totpService = totpService;
        this.loginLogService = loginLogService;
    }

    /** 校验手机号、密码、状态和IP策略，并根据MFA状态继续认证或创建会话。 */
    @Transactional
    public LoginResponse login(LoginRequest request, String clientIp, String userAgent) {
        UserAccount user = null;
        String phone = PhoneNumberNormalizer.normalize(request.phone());
        try {
            user = authMapper.findLoginUser(phone);
            if (user == null) {
                throw new BusinessException(ApiCode.AUTHENTICATION_FAILED, "手机号或密码错误");
            }
            if (!passwordEncoder.matches(request.password(), user.getPasswordHash())) {
                authMapper.incrementLoginFailure(user.getId());
                throw new BusinessException(ApiCode.AUTHENTICATION_FAILED, "手机号或密码错误");
            }
            if (user.getStatus() != 1) {
                throw new BusinessException(ApiCode.AUTHENTICATION_FAILED, "用户已停用");
            }
            if (user.getLockedUntil() != null
                    && user.getLockedUntil().isAfter(LocalDateTime.now())) {
                throw new BusinessException(ApiCode.AUTHENTICATION_FAILED, "用户暂时被锁定");
            }
            if (!ipAccessService.isAllowed(user, clientIp)) {
                throw new BusinessException(ApiCode.AUTHENTICATION_FAILED, "当前IP不在允许访问范围内");
            }

            return switch (user.getMfaStatus()) {
                case -1 -> createSession(user, phone, LoginAuthStage.PASSWORD, clientIp, userAgent);
                case 0 -> createBindChallenge(user, clientIp);
                case 1 -> createVerifyChallenge(user, clientIp);
                default -> throw new IllegalStateException("用户MFA状态非法");
            };
        } catch (BusinessException exception) {
            loginLogService.recordFailure(
                    user, phone, LoginAuthStage.PASSWORD, exception, clientIp, userAgent);
            throw exception;
        }
    }

    /** 校验已同步的飞书身份、用户状态和IP策略后直接创建系统会话。 */
    @Transactional
    public LoginResponse loginWithFeishu(
            FeishuIdentity identity, String clientIp, String userAgent) {
        UserAccount user = null;
        String loginIdentifier = "feishu:" + identity.openId();
        try {
            user =
                    authMapper.findFeishuLoginUser(
                            identity.tenantKey(), identity.openId(), identity.unionId());
            if (user == null) {
                throw new BusinessException(ApiCode.AUTHENTICATION_FAILED, "当前飞书用户尚未同步到系统");
            }
            if (user.getStatus() != 1) {
                throw new BusinessException(ApiCode.AUTHENTICATION_FAILED, "用户已停用");
            }
            if (user.getLockedUntil() != null
                    && user.getLockedUntil().isAfter(LocalDateTime.now())) {
                throw new BusinessException(ApiCode.AUTHENTICATION_FAILED, "用户暂时被锁定");
            }
            if (!ipAccessService.isAllowed(user, clientIp)) {
                throw new BusinessException(ApiCode.AUTHENTICATION_FAILED, "当前IP不在允许访问范围内");
            }
            // 飞书扫码本身是独立强认证方式，不再叠加密码登录后的本地MFA步骤。
            return createSession(
                    user, loginIdentifier, LoginAuthStage.FEISHU_QR, clientIp, userAgent);
        } catch (BusinessException exception) {
            loginLogService.recordFailure(
                    user,
                    loginIdentifier,
                    LoginAuthStage.FEISHU_QR,
                    exception,
                    clientIp,
                    userAgent);
            throw exception;
        }
    }

    /** 校验首次绑定动态码，保存加密密钥并自动完成登录。 */
    @Transactional
    public LoginResponse bindMfa(MfaCodeRequest request, String clientIp, String userAgent) {
        UserAccount user = null;
        try {
            MfaChallenge challenge = requireChallenge(request.challengeToken(), clientIp);
            if (challenge.purpose() != MfaChallenge.Purpose.BIND
                    || challenge.pendingSecretCiphertext() == null) {
                throw new BusinessException(ApiCode.MFA_CHALLENGE_MISMATCH, "MFA挑战用途不匹配");
            }
            user = requireChallengeUser(challenge.userId());
            if (user.getMfaStatus() != 0) {
                mfaChallengeStore.delete(request.challengeToken());
                throw new BusinessException(ApiCode.MFA_STATE_CHANGED, "MFA状态已变化，请重新登录");
            }
            String secret = mfaSecretCipher.decrypt(challenge.pendingSecretCiphertext());
            long counter = verifyCode(request, secret);
            if (authMapper.bindMfa(
                            user.getId(),
                            challenge.pendingSecretCiphertext(),
                            LocalDateTime.now(),
                            counter)
                    != 1) {
                throw new BusinessException(ApiCode.MFA_STATE_CHANGED, "MFA绑定状态已变化，请重新登录");
            }
            mfaChallengeStore.delete(request.challengeToken());
            user.setMfaStatus(1);
            return createSession(
                    user, preferredIdentifier(user), LoginAuthStage.MFA_BIND, clientIp, userAgent);
        } catch (BusinessException exception) {
            loginLogService.recordFailure(
                    user,
                    preferredIdentifier(user),
                    LoginAuthStage.MFA_BIND,
                    exception,
                    clientIp,
                    userAgent);
            throw exception;
        }
    }

    /** 校验已绑定用户的动态码并完成登录。 */
    @Transactional
    public LoginResponse verifyMfa(MfaCodeRequest request, String clientIp, String userAgent) {
        UserAccount user = null;
        try {
            MfaChallenge challenge = requireChallenge(request.challengeToken(), clientIp);
            if (challenge.purpose() != MfaChallenge.Purpose.VERIFY) {
                throw new BusinessException(ApiCode.MFA_CHALLENGE_MISMATCH, "MFA挑战用途不匹配");
            }
            user = requireChallengeUser(challenge.userId());
            if (user.getMfaStatus() != 1 || user.getMfaSecretCiphertext() == null) {
                mfaChallengeStore.delete(request.challengeToken());
                throw new BusinessException(ApiCode.MFA_STATE_CHANGED, "MFA绑定状态已变化，请重新登录");
            }
            String secret = mfaSecretCipher.decrypt(user.getMfaSecretCiphertext());
            long counter = verifyCode(request, secret);
            if (authMapper.recordMfaCounter(user.getId(), counter) != 1) {
                recordMfaFailure(request.challengeToken());
                throw new BusinessException(ApiCode.MFA_CODE_INVALID, "MFA动态码已使用或已过期");
            }
            mfaChallengeStore.delete(request.challengeToken());
            return createSession(
                    user,
                    preferredIdentifier(user),
                    LoginAuthStage.MFA_VERIFY,
                    clientIp,
                    userAgent);
        } catch (BusinessException exception) {
            loginLogService.recordFailure(
                    user,
                    preferredIdentifier(user),
                    LoginAuthStage.MFA_VERIFY,
                    exception,
                    clientIp,
                    userAgent);
            throw exception;
        }
    }

    private LoginResponse createBindChallenge(UserAccount user, String clientIp) {
        String secret = totpService.generateSecret();
        String token =
                mfaChallengeStore.create(
                        new MfaChallenge(
                                user.getId(),
                                clientIp,
                                MfaChallenge.Purpose.BIND,
                                mfaSecretCipher.encrypt(secret)));
        return LoginResponse.bindRequired(
                token,
                mfaChallengeStore.ttlSeconds(),
                secret,
                totpService.buildOtpAuthUri(user.getPhone(), secret));
    }

    private LoginResponse createVerifyChallenge(UserAccount user, String clientIp) {
        if (user.getMfaSecretCiphertext() == null) {
            throw new IllegalStateException("已启用MFA的用户缺少密钥");
        }
        String token =
                mfaChallengeStore.create(
                        new MfaChallenge(
                                user.getId(), clientIp, MfaChallenge.Purpose.VERIFY, null));
        return LoginResponse.verifyRequired(token, mfaChallengeStore.ttlSeconds());
    }

    private MfaChallenge requireChallenge(String token, String clientIp) {
        MfaChallenge challenge =
                mfaChallengeStore
                        .find(token)
                        .orElseThrow(
                                () ->
                                        new BusinessException(
                                                ApiCode.MFA_CHALLENGE_INVALID, "MFA挑战无效或已过期"));
        if (!challenge.clientIp().equals(clientIp)) {
            mfaChallengeStore.delete(token);
            throw new BusinessException(ApiCode.MFA_CHALLENGE_INVALID, "MFA挑战无效或已过期");
        }
        return challenge;
    }

    private UserAccount requireChallengeUser(Long userId) {
        UserAccount user = authMapper.findActiveUserById(userId);
        if (user == null) {
            throw new BusinessException(ApiCode.MFA_CHALLENGE_INVALID, "MFA挑战用户无效");
        }
        return user;
    }

    private long verifyCode(MfaCodeRequest request, String secret) {
        OptionalLong counter = totpService.verify(secret, request.totpCode());
        if (counter.isEmpty()) {
            recordMfaFailure(request.challengeToken());
            throw new BusinessException(ApiCode.MFA_CODE_INVALID, "MFA动态码错误或已过期");
        }
        return counter.getAsLong();
    }

    private void recordMfaFailure(String token) {
        if (!mfaChallengeStore.recordFailure(token)) {
            throw new BusinessException(ApiCode.MFA_ATTEMPTS_EXCEEDED, "MFA尝试次数过多，请重新登录");
        }
    }

    private LoginResponse createSession(
            UserAccount user,
            String loginIdentifier,
            LoginAuthStage authStage,
            String clientIp,
            String userAgent) {

        Set<String> permissions = new HashSet<>(authMapper.findPermissionCodes(user.getId()));
        Set<String> menuCodes = new LinkedHashSet<>(authMapper.findMenuCodes(user.getId()));
        List<AuthMapper.UserRoleView> roles = authMapper.findActiveRoles(user.getId());
        Set<Long> roleIds = new LinkedHashSet<>();
        Set<String> roleCodes = new LinkedHashSet<>();
        Set<String> roleNames = new LinkedHashSet<>();
        if (user.isSuperAdmin()) {
            roleCodes.add("SUPER_ADMIN");
            roleNames.add("超级管理员");
        }
        for (AuthMapper.UserRoleView role : roles) {
            roleIds.add(role.id());
            roleCodes.add(role.roleCode());
            roleNames.add(role.roleName());
        }
        String departmentName =
                user.getPrimaryDepartmentId() == null
                        ? null
                        : authMapper.findPrimaryDepartmentName(user.getPrimaryDepartmentId());
        String sessionId = UUID.randomUUID().toString();
        Instant issuedAt = Instant.now();
        ServerSession session =
                new ServerSession(
                        sessionId,
                        user.getId(),
                        user.getDisplayName(),
                        user.getEnglishNickname(),
                        user.getRealName(),
                        user.getPrimaryDepartmentId(),
                        departmentName,
                        roleIds,
                        roleCodes,
                        roleNames,
                        clientIp,
                        permissions,
                        menuCodes,
                        issuedAt);
        authMapper.recordLoginSuccess(user.getId(), LocalDateTime.now(), clientIp);
        loginLogService.recordSuccess(user, loginIdentifier, authStage, clientIp, userAgent);
        sessionStore.save(session);

        return LoginResponse.success(
                jwtService.issue(user.getId(), sessionId),
                properties.sessionTtl().toSeconds(),
                user.getId().toString(),
                user.getDisplayName(),
                permissions,
                issuedAt);
    }

    private String preferredIdentifier(UserAccount user) {
        if (user == null) {
            return null;
        }
        return user.getPhone();
    }

    /** 撤销当前 Redis 会话。 */
    public void logout(CurrentUser user) {
        sessionStore.delete(user.sessionId(), user.userId());
    }
}

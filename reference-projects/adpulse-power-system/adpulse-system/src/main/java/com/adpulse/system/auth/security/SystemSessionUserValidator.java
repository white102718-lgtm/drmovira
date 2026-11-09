package com.adpulse.system.auth.security;

import com.adpulse.system.auth.mapper.AuthMapper;
import com.adpulse.system.auth.service.IpAccessService;
import com.adpulse.system.user.model.UserAccount;
import java.util.Optional;
import org.springframework.stereotype.Component;

/** 使用系统用户状态与IP策略校验共享登录会话。 */
@Component
public class SystemSessionUserValidator implements SessionUserValidator {

    private final AuthMapper authMapper;
    private final IpAccessService ipAccessService;

    public SystemSessionUserValidator(AuthMapper authMapper, IpAccessService ipAccessService) {
        this.authMapper = authMapper;
        this.ipAccessService = ipAccessService;
    }

    /** 仅允许当前仍启用且满足IP访问策略的用户。 */
    @Override
    public Optional<ValidatedUser> validate(Long userId, String clientIp) {
        UserAccount user = authMapper.findActiveUserById(userId);
        if (user == null || !ipAccessService.isAllowed(user, clientIp)) {
            return Optional.empty();
        }
        return Optional.of(new ValidatedUser(user.getDisplayName()));
    }
}

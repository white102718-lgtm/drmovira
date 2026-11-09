package com.adpulse.main.auth;

import com.adpulse.system.auth.security.SessionUserValidator;
import java.util.Optional;
import org.springframework.security.web.util.matcher.IpAddressMatcher;
import org.springframework.stereotype.Component;

/** 在主业务服务中校验系统用户状态与IP访问策略。 */
@Component
public class MainSessionUserValidator implements SessionUserValidator {

    private final MainUserAccessMapper mapper;

    public MainSessionUserValidator(MainUserAccessMapper mapper) {
        this.mapper = mapper;
    }

    /** 使用共享数据库中的实时状态决定会话能否继续访问。 */
    @Override
    public Optional<ValidatedUser> validate(Long userId, String clientIp) {
        MainUserAccessMapper.MainUserAccess user = mapper.findActiveUser(userId);
        if (user == null) {
            return Optional.empty();
        }
        if (user.ipAccessMode() != null
                && user.ipAccessMode() == 2
                && mapper.findAllowedIpCidrs(userId).stream()
                        .noneMatch(cidr -> matches(cidr, clientIp))) {
            return Optional.empty();
        }
        return Optional.of(new ValidatedUser(user.displayName()));
    }

    private boolean matches(String cidr, String clientIp) {
        try {
            return new IpAddressMatcher(cidr).matches(clientIp);
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }
}

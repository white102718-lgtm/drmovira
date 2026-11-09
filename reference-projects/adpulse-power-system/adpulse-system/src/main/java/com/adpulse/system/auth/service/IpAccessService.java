package com.adpulse.system.auth.service;

import com.adpulse.system.auth.mapper.AuthMapper;
import com.adpulse.system.user.model.UserAccount;
import java.util.List;
import org.springframework.security.web.util.matcher.IpAddressMatcher;
import org.springframework.stereotype.Service;

/** 执行用户IP访问模式与通用/个人白名单匹配。 */
@Service
public class IpAccessService {

    private final AuthMapper authMapper;

    public IpAccessService(AuthMapper authMapper) {
        this.authMapper = authMapper;
    }

    /** 判断来源IP是否满足用户当前访问策略。 */
    public boolean isAllowed(UserAccount user, String clientIp) {
        if (user.getIpAccessMode() == null || user.getIpAccessMode() != 2) {
            return true;
        }
        List<String> cidrs = authMapper.findAllowedIpCidrs(user.getId());
        return cidrs.stream().anyMatch(cidr -> matches(cidr, clientIp));
    }

    private boolean matches(String cidr, String clientIp) {
        try {
            return new IpAddressMatcher(cidr).matches(clientIp);
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }
}

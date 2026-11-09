package com.adpulse.system.config;

import com.adpulse.system.common.util.PhoneNumberNormalizer;
import com.adpulse.system.config.BootstrapMapper.BootstrapUser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/** 在空库首次启动时按显式环境变量创建管理员。 */
@Component
@EnableConfigurationProperties(BootstrapAdminProperties.class)
public class BootstrapAdminRunner implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(BootstrapAdminRunner.class);

    private final BootstrapAdminProperties properties;
    private final BootstrapMapper mapper;
    private final PasswordEncoder passwordEncoder;

    public BootstrapAdminRunner(
            BootstrapAdminProperties properties,
            BootstrapMapper mapper,
            PasswordEncoder passwordEncoder) {
        this.properties = properties;
        this.mapper = mapper;
        this.passwordEncoder = passwordEncoder;
    }

    /** 仅在启用、密码非空且当前没有有效用户时创建管理员。 */
    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        if (!properties.enabled()) {
            return;
        }
        if (!StringUtils.hasText(properties.password()) || properties.password().length() < 8) {
            throw new IllegalStateException("BOOTSTRAP_ADMIN_PASSWORD 至少需要8位");
        }
        if (mapper.countActiveUsers() > 0) {
            log.info("Skip bootstrap administrator because active users already exist");
            return;
        }
        Long roleId = mapper.findAdminRoleId();
        if (roleId == null) {
            throw new IllegalStateException("执行数据库初始化脚本后仍缺少ADMIN角色");
        }
        BootstrapUser user = new BootstrapUser();
        user.username = properties.username();
        user.phone = PhoneNumberNormalizer.normalize(properties.phone());
        user.passwordHash = passwordEncoder.encode(properties.password());
        user.displayName = properties.displayName();
        user.englishNickname = properties.username();
        mapper.insertUser(user);
        mapper.insertUserRole(user.id, roleId);
        log.info("Bootstrap administrator created with id={}", user.id);
    }
}

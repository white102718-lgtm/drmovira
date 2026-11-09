package com.ruoyi.system.orbit.config;

import com.ruoyi.system.orbit.analysis.AnalysisJobMapper;
import com.ruoyi.system.orbit.metrics.MetricProfileMapper;
import com.ruoyi.system.orbit.rules.RuleDraftMapper;
import com.ruoyi.system.orbit.scope.AccountScopeMapper;
import java.util.LinkedHashMap;
import java.util.Map;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 主密钥仅由服务端私有配置注入，不提供网页读取或写入接口。 */
@Configuration
@MapperScan(
        basePackageClasses = {
            ConfigurationMapper.class,
            AnalysisJobMapper.class,
            RuleDraftMapper.class,
            MetricProfileMapper.class,
            AccountScopeMapper.class
        })
@ConfigurationProperties(prefix = "orbit.secrets")
public class SecretConfiguration {
    private String activeKeyId;
    private Map<String, String> keys = new LinkedHashMap<>();

    public String getActiveKeyId() {
        return activeKeyId;
    }

    public void setActiveKeyId(String value) {
        activeKeyId = value;
    }

    public Map<String, String> getKeys() {
        return keys;
    }

    public void setKeys(Map<String, String> value) {
        keys = value;
    }

    @Bean
    public SecretCipher secretCipher() {
        return new SecretCipher(activeKeyId, keys);
    }
}

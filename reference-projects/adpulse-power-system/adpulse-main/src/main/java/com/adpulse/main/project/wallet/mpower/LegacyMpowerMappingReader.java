package com.adpulse.main.project.wallet.mpower;

import com.adpulse.main.project.wallet.mpower.LegacyMpowerMappingMapper.LegacyDepartment;
import com.adpulse.main.project.wallet.mpower.LegacyMpowerMappingMapper.LegacyUser;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.annotation.PreDestroy;
import java.io.InputStream;
import java.util.List;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

/** 复用迁移数据源配置查询老MPower部门和用户，不暴露额外DataSource Bean。 */
@Component
public class LegacyMpowerMappingReader {
    private final MpowerWalletProperties properties;
    private HikariDataSource pool;
    private SqlSessionFactory factory;

    public LegacyMpowerMappingReader(MpowerWalletProperties properties) {
        this.properties = properties;
    }

    /** 在同一只读会话中查询候选部门和用户，由上层判断是否唯一匹配。 */
    public synchronized MappingCandidates read(
            Integer tenantId, String departmentName, List<String> userNames) {
        initialize();
        try (var session = factory.openSession()) {
            LegacyMpowerMappingMapper mapper =
                    session.getMapper(LegacyMpowerMappingMapper.class);
            var identity = mapper.identity();
            if (!properties.getSourceUuid().equals(identity.serverUuid())
                    || !properties.getSourceSchema().equals(identity.schemaName())) {
                throw new MpowerWalletClient.MpowerWalletClientException(
                        "旧MPower来源数据库实例或库名不匹配");
            }
            List<LegacyDepartment> departments =
                    departmentName == null || departmentName.isBlank()
                            ? List.of()
                            : mapper.findDepartments(tenantId, departmentName);
            List<LegacyUser> users =
                    userNames == null || userNames.isEmpty()
                            ? List.of()
                            : mapper.findUsers(tenantId, userNames);
            return new MappingCandidates(departments, users);
        } catch (MpowerWalletClient.MpowerWalletClientException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new MpowerWalletClient.MpowerWalletClientException(
                    "旧MPower组织映射查询失败，请稍后重试", exception);
        }
    }

    private void initialize() {
        properties.validateSource();
        if (factory != null) return;
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(properties.getSourceUrl());
        config.setUsername(properties.getSourceUsername());
        config.setPassword(properties.getSourcePassword());
        config.setReadOnly(true);
        config.setConnectionInitSql("SET SESSION TRANSACTION READ ONLY");
        config.setMaximumPoolSize(1);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(10_000);
        config.setPoolName("legacy-mpower-wallet-mapping-readonly");
        config.addDataSourceProperty("connectTimeout", "10000");
        config.addDataSourceProperty("socketTimeout", "30000");
        HikariDataSource candidate = new HikariDataSource(config);
        try (InputStream input =
                new ClassPathResource("mapper/project/LegacyMpowerMappingMapper.xml")
                        .getInputStream()) {
            Configuration configuration =
                    new Configuration(
                            new Environment(
                                    "legacy-mpower-wallet-mapping",
                                    new JdbcTransactionFactory(),
                                    candidate));
            configuration.setDefaultStatementTimeout(30);
            new XMLMapperBuilder(
                            input,
                            configuration,
                            "legacy-mpower-wallet-mapping",
                            configuration.getSqlFragments())
                    .parse();
            factory = new SqlSessionFactoryBuilder().build(configuration);
            pool = candidate;
        } catch (Exception exception) {
            candidate.close();
            throw new IllegalStateException("旧MPower组织映射读取组件初始化失败", exception);
        }
    }

    /** 关闭钱包映射专用的单连接只读池。 */
    @PreDestroy
    public synchronized void close() {
        if (pool != null) pool.close();
    }

    /** 老库中精确匹配到的候选记录。 */
    public record MappingCandidates(
            List<LegacyDepartment> departments, List<LegacyUser> users) {}
}

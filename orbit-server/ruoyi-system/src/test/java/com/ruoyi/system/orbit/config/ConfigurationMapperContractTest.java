package com.ruoyi.system.orbit.config;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.io.Resources;
import org.apache.ibatis.mapping.BoundSql;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

/** 使用真正MyBatis解析与绑定模型检查SQL契约，不连接数据库，也不声称事务已验收。 */
class ConfigurationMapperContractTest {
    private BoundSql sql(String statement, Object parameters) throws Exception {
        Configuration configuration = new Configuration();
        // 与若依生产默认保持一致，不能在测试中偷偷启用转驼峰。
        configuration.setMapUnderscoreToCamelCase(false);
        String resource = "mapper/orbit/ConfigurationMapper.xml";
        try (var input = Resources.getResourceAsStream(resource)) {
            new XMLMapperBuilder(input, configuration, resource, configuration.getSqlFragments())
                    .parse();
        }
        return configuration
                .getMappedStatement(ConfigurationMapper.class.getName() + "." + statement)
                .getBoundSql(parameters);
    }

    @Test
    void historyBindsTenantConfigurationAndVersionCursor() throws Exception {
        BoundSql statement =
                sql(
                        "history",
                        Map.of(
                                "tenantId",
                                "tenant-a",
                                "configId",
                                "config-a",
                                "beforeRevision",
                                3,
                                "limit",
                                51));
        String text = statement.getSql().replaceAll("\\s+", " ");
        assertTrue(text.contains("tenant_id = ? AND config_id = ?"));
        assertTrue(text.contains("revision < ?"));
        assertTrue(text.contains("ORDER BY revision DESC"));
        assertEquals(
                java.util.List.of("tenantId", "configId", "beforeRevision", "limit"),
                statement.getParameterMappings().stream().map(p -> p.getProperty()).toList());
        assertFalse(text.contains("secrets_json"));
        assertTrue(text.contains("before_hash, after_hash, hash_algorithm"));
    }

    @Test
    void auditInsertBindsAllSummaryFieldsWithoutSnapshotValues() throws Exception {
        var record =
                new ConfigurationModels.AuditWrite(
                        "id",
                        "tenant",
                        "config",
                        7L,
                        "UPDATE",
                        2,
                        1,
                        "a".repeat(64),
                        "b".repeat(64),
                        ConfigurationFingerprint.ALGORITHM,
                        "[]",
                        "维护配置");
        BoundSql statement = sql("audit", record);
        var parameters =
                statement.getParameterMappings().stream().map(p -> p.getProperty()).toList();
        assertEquals(
                java.util.List.of(
                        "id",
                        "tenantId",
                        "configId",
                        "actorId",
                        "action",
                        "revision",
                        "beforeRevision",
                        "beforeHash",
                        "afterHash",
                        "hashAlgorithm",
                        "changedFieldsJson",
                        "reason"),
                parameters);
        assertFalse(statement.getSql().contains("secrets_json"));
        assertFalse(statement.getSql().contains("settings_json"));
    }
}

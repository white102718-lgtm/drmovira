package com.adpulse.main.migration;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.util.List;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

class LegacyPaymentMigrationMapperTest {
    @Test
    void loadsPaymentMappersAndReadsManagementTenantAndDisabledTargetUsers() throws Exception {
        Configuration config = new Configuration();
        for (String name : List.of("LegacyAssetMapper", "LegacyPaymentMigrationMapper")) {
            String resource = "mapper/migration/" + name + ".xml";
            try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
                new XMLMapperBuilder(stream, config, resource, config.getSqlFragments()).parse();
            }
        }

        String sourceUsers =
                config.getMappedStatement(LegacyAssetMapper.class.getName() + ".payments")
                        .getBoundSql(null)
                        .getSql();
        assertThat(sourceUsers)
                .contains(
                        "requester.tenant_id AS requesterTenantId",
                        "auditor.tenant_id AS auditorTenantId");

        String targetUsers =
                config.getMappedStatement(
                                LegacyPaymentMigrationMapper.class.getName() + ".migrationUsers")
                        .getBoundSql(null)
                        .getSql();
        assertThat(targetUsers)
                .contains("system_user.display_name AS displayName", "system_user.deleted_at = 0")
                .doesNotContain("system_user.status = 1");
    }
}

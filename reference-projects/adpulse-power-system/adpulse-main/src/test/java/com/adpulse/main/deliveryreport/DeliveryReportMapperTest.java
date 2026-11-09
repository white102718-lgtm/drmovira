package com.adpulse.main.deliveryreport;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.time.LocalDate;
import java.util.Map;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

/** 校验MyBatis映射可加载且关键SQL保持用户隔离和幂等语义。 */
class DeliveryReportMapperTest {
    @Test
    void parsesMapperAndScopesRecordsToOwnerAndDate() throws Exception {
        Configuration config = new Configuration();
        String resource = "mapper/deliveryreport/DeliveryReportMapper.xml";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            new XMLMapperBuilder(stream, config, resource, config.getSqlFragments()).parse();
        }
        String prefix = DeliveryReportMapper.class.getName() + ".";
        String sql =
                config.getMappedStatement(prefix + "findRecords")
                        .getBoundSql(Map.of("userId", 7L, "date", LocalDate.of(2026, 9, 9)))
                        .getSql();
        assertThat(sql).contains("reporter_id = ?", "report_date = ?", "deleted_at = 0");
        DeliveryReportRecord row = new DeliveryReportRecord();
        String upsert = config.getMappedStatement(prefix + "upsert").getBoundSql(row).getSql();
        assertThat(upsert).contains("ON DUPLICATE KEY UPDATE", "LAST_INSERT_ID(id)");
        assertThat(upsert).doesNotContain("actual_spend");
    }
}

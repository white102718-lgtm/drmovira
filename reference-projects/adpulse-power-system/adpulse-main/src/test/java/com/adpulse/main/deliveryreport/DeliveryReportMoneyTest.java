package com.adpulse.main.deliveryreport;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.main.deliveryreport.DeliveryReportTypes.Metrics;
import com.adpulse.main.deliveryreport.DeliveryReportTypes.PlatformRow;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

/** 校验人工、历史和平台金额统一为两位，负调整额使用相同舍入规则。 */
class DeliveryReportMoneyTest {
    @Test
    void roundsEditableAmountsAndPreservesMissingValues() {
        Metrics metrics =
                new Metrics(
                        new BigDecimal("10.125"),
                        0L,
                        0L,
                        0L,
                        0L,
                        0L,
                        new BigDecimal("-1.235"),
                        new BigDecimal("0"),
                        "未设置",
                        "");
        assertThat(metrics.dailySpend()).isEqualTo(new BigDecimal("10.13"));
        assertThat(metrics.adjustmentAmount()).isEqualTo(new BigDecimal("-1.24"));
        assertThat(metrics.secondaryDeduction()).isEqualTo(new BigDecimal("0.00"));
        Metrics missing = new Metrics(null, 0L, 0L, 0L, 0L, 0L, null, null, "未设置", "");
        assertThat(missing.dailySpend()).isNull();
    }

    @Test
    void roundsPlatformAggregateToTwoDecimals() {
        PlatformRow row =
                new PlatformRow(
                        "项目",
                        "代理线",
                        "facebook",
                        new BigDecimal("12.3456"),
                        0,
                        0,
                        0,
                        0,
                        0,
                        List.of(),
                        List.of());
        assertThat(row.actualSpend()).isEqualTo(new BigDecimal("12.35"));
    }
}

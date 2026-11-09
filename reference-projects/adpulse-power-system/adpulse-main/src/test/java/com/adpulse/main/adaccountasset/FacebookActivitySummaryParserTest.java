package com.adpulse.main.adaccountasset;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.main.adaccountasset.AdAccountAssetViews.FacebookActivitySummaryItem;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** Facebook 活动动态字段的摘要解析测试。 */
class FacebookActivitySummaryParserTest {
    private FacebookActivitySummaryParser parser;

    @BeforeEach
    void setUp() {
        parser = new FacebookActivitySummaryParser(new ObjectMapper());
    }

    @Test
    void shouldSummarizeScalarStatusChange() {
        List<FacebookActivitySummaryItem> items =
                parser.parse(
                        """
                        {"old_value":"使用中","new_value":"等待支付","type":"status"}
                        """,
                        "ACCOUNT");

        assertThat(items)
                .containsExactly(
                        new FacebookActivitySummaryItem(
                                "账户状态", "使用中", "等待支付", null));
    }

    @Test
    void shouldFormatNestedPaymentAmount() {
        List<FacebookActivitySummaryItem> items =
                parser.parse(
                        """
                        {
                          "type":"payment_amount",
                          "old_value":{"amount":1250,"currency":"USD"},
                          "new_value":{"amount":2380,"currency":"USD"}
                        }
                        """,
                        "BILLING");

        assertThat(items)
                .containsExactly(
                        new FacebookActivitySummaryItem("金额", "USD 12.50", "USD 23.80", null));
    }

    @Test
    void shouldSummarizeCreationDetailsWithoutShowingNumericType() {
        List<FacebookActivitySummaryItem> items =
                parser.parse("{\"type\":4,\"name\":\"asa_auto_custom_audience\"}", "AUDIENCE");

        assertThat(items)
                .containsExactly(
                        new FacebookActivitySummaryItem(
                                "名称", null, null, "asa_auto_custom_audience"));
    }

    @Test
    void shouldKeepUnknownAndComplexFieldsReadable() {
        List<FacebookActivitySummaryItem> items =
                parser.parse(
                        "{\"delivery_mode\":\"accelerated\",\"targeting\":{\"countries\":[\"US\"]}}",
                        "AD_SET");

        assertThat(items)
                .containsExactly(
                        new FacebookActivitySummaryItem(
                                "Delivery Mode", null, null, "accelerated"),
                        new FacebookActivitySummaryItem(
                                "Targeting", null, null, "{\"countries\":[\"US\"]}"));
    }

    @Test
    void shouldReturnEmptySummaryForMalformedJson() {
        assertThat(parser.parse("not-json", "OTHER")).isEmpty();
    }

    @Test
    void shouldRedactSensitiveFieldsBeforeBuildingSummary() {
        ObjectMapper objectMapper = new ObjectMapper();
        FacebookAdActivityClient client = new FacebookAdActivityClient(objectMapper);

        String sanitized =
                client.sanitizedExtraData(
                        "{\"name\":\"audience\",\"access_token\":\"secret-token\"}");
        List<FacebookActivitySummaryItem> items = parser.parse(sanitized, "AUDIENCE");

        assertThat(sanitized).doesNotContain("secret-token").contains("***");
        assertThat(items)
                .containsExactly(
                        new FacebookActivitySummaryItem("名称", null, null, "audience"));
    }

    @Test
    void shouldClassifyCommonActivityGroups() {
        assertThat(parser.category("ad_account_add_user_to_role", "ACCOUNT"))
                .isEqualTo("ACCESS");
        assertThat(parser.category("ad_account_billing_charge", "ACCOUNT"))
                .isEqualTo("BILLING");
        assertThat(parser.category("update_ad_set_budget", "AD_SET")).isEqualTo("AD_SET");
        assertThat(parser.category("create_audience", "CAMPAIGN")).isEqualTo("AUDIENCE");
        assertThat(parser.category("unknown", "CAMPAIGN")).isEqualTo("CAMPAIGN");
    }
}

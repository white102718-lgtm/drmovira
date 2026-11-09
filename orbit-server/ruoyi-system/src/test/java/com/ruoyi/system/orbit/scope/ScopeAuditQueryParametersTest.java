package com.ruoyi.system.orbit.scope;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.*;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;

/** 合同参数形状及逐字段边界；无HTTP/数据库替身成功声明，公开控制器仍待接入。 */
class ScopeAuditQueryParametersTest {
    private Map<String, List<String>> one(String key, String value) {
        return Map.of(key, List.of(value));
    }

    private void rejects(int status, String code, Map<String, List<String>> query) {
        var error =
                assertThrows(
                        AccountScopeService.Failure.class,
                        () -> ScopeAuditQueryParameters.parse(query));
        assertEquals(status, error.status());
        assertEquals(code, error.code());
        assertFalse(error.getMessage().contains("fixture-sensitive"));
    }

    @Test
    void defaultsNormalizeAllSupportedFieldsWithoutAcceptingIdentityContext() {
        var empty = ScopeAuditQueryParameters.parse(Map.of());
        assertEquals(50, empty.size());
        assertNull(empty.cursor());
        assertEquals("", empty.filter().q());
        String uuid = "abcdef01-abcd-4abc-8abc-abcdef012345";
        var input =
                ScopeAuditQueryParameters.parse(
                        Map.of(
                                "q",
                                List.of("  e\u0301  "),
                                "cursor",
                                List.of("fixture-sensitive-cursor"),
                                "page_size",
                                List.of("20"),
                                "operator_user_id",
                                List.of(uuid.toUpperCase(Locale.ROOT)),
                                "date_from",
                                List.of("2026-11-05"),
                                "date_to",
                                List.of("2026-11-06")));
        assertEquals("é", input.filter().q());
        assertEquals(uuid, input.filter().operator());
        assertEquals("2026-11-05", input.filter().dateFrom());
        assertEquals("2026-11-06", input.filter().dateTo());
        assertEquals(20, input.size());
        assertEquals("fixture-sensitive-cursor", input.cursor());
        assertEquals("AuditQueryInput[REDACTED]", input.toString());
        assertEquals("AuditQueryFilter[REDACTED]", input.filter().toString());
    }

    @Test
    void everyUnknownIdentityOrRetiredParameterIs400() {
        for (String key :
                List.of(
                        "tenant_id",
                        "actor_id",
                        "target",
                        "X-Target-Tenant",
                        "page",
                        "pageNo",
                        "sort",
                        "fixture-sensitive"))
            rejects(400, "UNKNOWN_FIELD", one(key, "fixture-sensitive"));
    }

    @Test
    void everyKnownParameterRejectsDuplicateAndMissingValuesBeforeUnsupportedHandling() {
        for (String key :
                List.of(
                        "q",
                        "cursor",
                        "page_size",
                        "status",
                        "date_from",
                        "date_to",
                        "operator_user_id",
                        "channel_id",
                        "metric_profile_id",
                        "entity_type")) {
            rejects(400, "INVALID_REQUEST", Map.of(key, List.of("a", "b")));
            rejects(400, "INVALID_REQUEST", Map.of(key, List.of()));
            rejects(400, "INVALID_REQUEST", Map.of(key, Arrays.asList((String) null)));
            Map<String, List<String>> nullValue = new HashMap<>();
            nullValue.put(key, null);
            rejects(400, "INVALID_REQUEST", nullValue);
        }
        rejects(400, "INVALID_REQUEST", null);
        Map<String, List<String>> nullKey = new HashMap<>();
        nullKey.put(null, List.of("x"));
        rejects(400, "INVALID_REQUEST", nullKey);
    }

    @Test
    void unsupportedKnownFiltersNeverDisappearOrPretendToHaveAnAuditStatusEnum() {
        for (String key : List.of("status", "channel_id", "metric_profile_id", "entity_type"))
            for (String value : List.of("ACTIVE", "CAMPAIGN", "", "fixture-sensitive"))
                rejects(422, "UNSUPPORTED_FILTER", one(key, value));
    }

    @Test
    void pageSizesAndCursorLengthFollowCanonicalContract() {
        for (String value : List.of("20", "50", "100", "200"))
            assertEquals(
                    Integer.parseInt(value),
                    ScopeAuditQueryParameters.parse(one("page_size", value)).size());
        for (String value :
                List.of("", "0", "1", "21", "201", "020", " 20", "20.0", "99999999999999999999999"))
            rejects(422, "BUSINESS_VALIDATION_FAILED", one("page_size", value));
        for (int length : List.of(1, 2048))
            assertEquals(
                    length,
                    ScopeAuditQueryParameters.parse(one("cursor", "x".repeat(length)))
                            .cursor()
                            .length());
        for (int length : List.of(0, 2049))
            rejects(422, "BUSINESS_VALIDATION_FAILED", one("cursor", "x".repeat(length)));
    }

    @Test
    void unicodeUuidCalendarAndUtcEndpointsRejectInvalidValuesWithoutEchoingInput() {
        assertEquals(
                100,
                ScopeAuditQueryParameters.parse(one("q", "😀".repeat(100)))
                        .filter()
                        .q()
                        .codePointCount(0, 200));
        for (String value :
                List.of("😀".repeat(101), "fixture-sensitive\n", "\ttext", "text\u007f"))
            rejects(422, "BUSINESS_VALIDATION_FAILED", one("q", value));
        for (String value : List.of("", "1-1-1-1-1", "fixture-sensitive"))
            rejects(422, "BUSINESS_VALIDATION_FAILED", one("operator_user_id", value));
        for (String field : List.of("date_from", "date_to"))
            for (String value :
                    List.of(
                            "",
                            "2026-02-30",
                            "2026-2-01",
                            "0001-01-01",
                            "2999-01-01",
                            "fixture-sensitive"))
                rejects(422, "BUSINESS_VALIDATION_FAILED", one(field, value));
        rejects(
                422,
                "BUSINESS_VALIDATION_FAILED",
                Map.of("date_from", List.of("2026-11-06"), "date_to", List.of("2026-11-05")));
        var same =
                ScopeAuditQueryParameters.parse(
                        Map.of(
                                "date_from",
                                List.of("2026-11-06"),
                                "date_to",
                                List.of("2026-11-06")));
        assertEquals(same.filter().dateFrom(), same.filter().dateTo());
    }

    @Test
    void parameterInventoryAndBoundsRemainTheUnmodifiedProductContract() throws Exception {
        Path root = Path.of("").toAbsolutePath();
        while (!Files.exists(root.resolve("docs/orbit/baseline/contracts/openapi-current.json")))
            root = root.getParent();
        JsonNode api =
                new ObjectMapper()
                        .readTree(
                                Files.readString(
                                        root.resolve(
                                                "docs/orbit/baseline/contracts/openapi-current.json")));
        Set<String> names = new HashSet<>();
        Map<String, JsonNode> schemas = new HashMap<>();
        for (JsonNode p :
                api.path("paths").path("/api/v1/audit-events").path("get").path("parameters")) {
            names.add(p.path("name").asText());
            schemas.put(p.path("name").asText(), p.path("schema"));
        }
        assertEquals(
                Set.of(
                        "q",
                        "cursor",
                        "page_size",
                        "status",
                        "date_from",
                        "date_to",
                        "operator_user_id",
                        "channel_id",
                        "metric_profile_id",
                        "entity_type"),
                names);
        assertEquals(100, schemas.get("q").path("maxLength").asInt());
        assertEquals(2048, schemas.get("cursor").path("maxLength").asInt());
        List<Integer> sizes = new ArrayList<>();
        schemas.get("page_size").path("enum").forEach(n -> sizes.add(n.asInt()));
        assertEquals(List.of(20, 50, 100, 200), sizes);
        assertEquals(50, schemas.get("page_size").path("default").asInt());
    }
}

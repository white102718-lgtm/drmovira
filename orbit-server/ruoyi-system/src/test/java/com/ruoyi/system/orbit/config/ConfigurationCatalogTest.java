package com.ruoyi.system.orbit.config;

import static org.junit.jupiter.api.Assertions.*;

import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** 配置字段边界、条件必填、白名单和保守风控测试。 */
class ConfigurationCatalogTest {
    @Test
    void exportedFieldChecklistMatchesActualJavaCatalog() throws Exception {
        com.fasterxml.jackson.databind.JsonNode fields =
                new com.fasterxml.jackson.databind.ObjectMapper()
                        .readTree(
                                java.nio.file.Path.of(
                                                "../docs/orbit/extensions/configuration-fields.json")
                                        .toFile());
        assertEquals(62, fields.size());
        assertEquals(
                fields.size(),
                ConfigurationCatalog.sections().stream()
                        .mapToInt(section -> section.fields().size())
                        .sum());
        for (com.fasterxml.jackson.databind.JsonNode saved : fields) {
            ConfigurationCatalog.Field field =
                    ConfigurationCatalog.section(saved.path("section").asText()).fields().stream()
                            .filter(candidate -> candidate.key().equals(saved.path("key").asText()))
                            .findFirst()
                            .orElseThrow();
            assertEquals(field.type(), saved.path("type").asText());
            assertEquals(field.required(), saved.path("required_when_enabled").asBoolean());
            assertEquals(field.label(), saved.path("label").asText());
        }
    }

    @Test
    void onlyOffersGptAndClaudeAsAiProviders() {
        assertEquals(
                2,
                ConfigurationCatalog.sections().stream()
                        .filter(
                                section ->
                                        section.key().startsWith("AI_")
                                                && !section.key().equals("AI_SUGGESTIONS"))
                        .count());
        assertThrows(
                ConfigurationException.class,
                () -> ConfigurationCatalog.section("CLAUDE_CODE_CLI"));
    }

    @Test
    void permitsIncompleteDisabledDraftButRejectsEnabledMissingModel() {
        assertEquals("", ConfigurationCatalog.validate("AI_GPT", Map.of(), false).get("model"));
        assertThrows(
                ConfigurationException.class,
                () -> ConfigurationCatalog.validate("AI_GPT", Map.of(), true));
    }

    @Test
    void rejectsSecretInPublicSettingsAndUnknownFields() {
        assertThrows(
                ConfigurationException.class,
                () -> ConfigurationCatalog.validate("AI_GPT", Map.of("apiKey", "fixture"), false));
        assertThrows(
                ConfigurationException.class,
                () ->
                        ConfigurationCatalog.validate(
                                "AI_GPT", Map.of("baseUrl", "http://127.0.0.1"), false));
    }

    @Test
    void rejectsFractionalOverflowAndStringIntegers() {
        for (Object invalid : new Object[] {2.5, -1, 3, "2", Double.NaN}) {
            assertThrows(
                    ConfigurationException.class,
                    () ->
                            ConfigurationCatalog.validate(
                                    "AI_GPT", Map.of("maxRetries", invalid), false));
        }
        assertEquals(
                2,
                ConfigurationCatalog.validate("AI_GPT", Map.of("maxRetries", 2), false)
                        .get("maxRetries"));
    }

    @Test
    void enforcesConservativeBudgetAndObservationBoundaries() {
        assertEquals(
                20,
                ConfigurationCatalog.validate("RISK", Map.of(), true).get("singleChangePercent"));
        assertThrows(
                ConfigurationException.class,
                () ->
                        ConfigurationCatalog.validate(
                                "RISK", Map.of("singleChangePercent", 21), true));
        assertThrows(
                ConfigurationException.class,
                () ->
                        ConfigurationCatalog.validate(
                                "AI_SUGGESTIONS",
                                Map.of("observationHours", 23, "providerConfigId", "fixture"),
                                true));
    }

    @Test
    void preservesLongBmIdWithoutNumericConversion() {
        String id = "12345678901234567890123456789012";
        assertEquals(
                id,
                ConfigurationCatalog.validate(
                                "META_BM", Map.of("businessId", id, "graphVersion", "v25.0"), true)
                        .get("businessId"));
        assertThrows(
                ConfigurationException.class,
                () ->
                        ConfigurationCatalog.validate(
                                "META_BM",
                                Map.of("businessId", 123L, "graphVersion", "v25.0"),
                                true));
    }

    @Test
    void rejectsCredentialBearingAndNonHttpsUrls() {
        Map<String, Object> settings =
                new HashMap<>(
                        Map.of(
                                "issuer",
                                "https://issuer.example",
                                "clientId",
                                "fixture",
                                "redirectUri",
                                "https://app.example/callback"));
        assertEquals(
                "https://issuer.example",
                ConfigurationCatalog.validate("OIDC", settings, true).get("issuer"));
        for (String url :
                new String[] {
                    "http://issuer.example",
                    "https://user:pass@issuer.example",
                    "https://issuer.example/#fragment"
                }) {
            settings.put("issuer", url);
            assertThrows(
                    ConfigurationException.class,
                    () -> ConfigurationCatalog.validate("OIDC", settings, true));
        }
    }

    @Test
    void webhookIsConditionallyRequired() {
        assertEquals(
                "IN_APP",
                ConfigurationCatalog.validate("NOTIFICATIONS", Map.of(), true).get("channel"));
        assertThrows(
                ConfigurationException.class,
                () ->
                        ConfigurationCatalog.validate(
                                "NOTIFICATIONS", Map.of("channel", "WEBHOOK"), true));
    }

    @Test
    void normalizesUnicodeAndRejectsControlsWithoutLeakingText() {
        assertEquals("é", ConfigurationCatalog.normalizeText(" e\u0301 ", 2, "名称"));
        assertThrows(
                ConfigurationException.class,
                () -> ConfigurationCatalog.normalizeText("fixture\nsecret", 50, "名称"));
        assertThrows(
                ConfigurationException.class,
                () -> ConfigurationCatalog.normalizeText("😀😀", 1, "名称"));
    }

    @Test
    void analysisLimitsUseRuleContractBoundsAndRejectInvalidNumbers() {
        var defaults = ConfigurationCatalog.validate("AI_SUGGESTIONS", Map.of(), false);
        assertEquals(60, defaults.get("minimumCooldownMinutes"));
        assertEquals(5, defaults.get("maximumDailyAnalysesPerObject"));
        for (int cooldown : new int[] {0, 10080}) {
            assertEquals(
                    cooldown,
                    ConfigurationCatalog.validate(
                                    "AI_SUGGESTIONS",
                                    Map.of("minimumCooldownMinutes", cooldown),
                                    false)
                            .get("minimumCooldownMinutes"));
        }
        for (int daily : new int[] {1, 1000}) {
            assertEquals(
                    daily,
                    ConfigurationCatalog.validate(
                                    "AI_SUGGESTIONS",
                                    Map.of("maximumDailyAnalysesPerObject", daily),
                                    false)
                            .get("maximumDailyAnalysesPerObject"));
        }
        for (Object invalid : new Object[] {-1, 10081, 1.5, "60"}) {
            assertThrows(
                    ConfigurationException.class,
                    () ->
                            ConfigurationCatalog.validate(
                                    "AI_SUGGESTIONS",
                                    Map.of("minimumCooldownMinutes", invalid),
                                    false));
        }
        for (Object invalid : new Object[] {0, 1001, 1.5, "5"}) {
            assertThrows(
                    ConfigurationException.class,
                    () ->
                            ConfigurationCatalog.validate(
                                    "AI_SUGGESTIONS",
                                    Map.of("maximumDailyAnalysesPerObject", invalid),
                                    false));
        }
    }

    @Test
    void analysisInputSizesOnlyTightenProductLimits() {
        var settings = ConfigurationCatalog.validate("AI_SUGGESTIONS", Map.of(), false);
        assertEquals(28, settings.get("maxDailyPoints"));
        assertEquals(500, settings.get("maxEvidenceItems"));
        assertThrows(
                ConfigurationException.class,
                () ->
                        ConfigurationCatalog.validate(
                                "AI_SUGGESTIONS", Map.of("maxDailyPoints", 29), false));
        assertThrows(
                ConfigurationException.class,
                () ->
                        ConfigurationCatalog.validate(
                                "AI_SUGGESTIONS", Map.of("maxEvidenceItems", 501), false));
        assertThrows(
                ConfigurationException.class,
                () ->
                        ConfigurationCatalog.validate(
                                "AI_SUGGESTIONS", Map.of("maxOutputTokens", 32769), false));
    }
}

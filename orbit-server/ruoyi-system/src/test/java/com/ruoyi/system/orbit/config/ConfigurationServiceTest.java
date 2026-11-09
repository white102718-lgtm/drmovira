package com.ruoyi.system.orbit.config;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.system.orbit.config.ConfigurationModels.*;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.PlatformTransactionManager;

/** 服务层隔离与凭据防泄露测试；Mapper为mock，不代替MySQL事务集成验收。 */
class ConfigurationServiceTest {
    private final ConfigurationMapper repository = mock(ConfigurationMapper.class);
    private final ObjectMapper json = new ObjectMapper().findAndRegisterModules();
    private final SecretCipher cipher =
            new SecretCipher(
                    "test", Map.of("test", Base64.getEncoder().encodeToString(new byte[32])));
    private ConfigurationService service;
    private final ConnectionProbe connectionProbe = mock(ConnectionProbe.class);
    private final Map<String, Row> rows = new LinkedHashMap<>();
    private final Map<String, IdempotencyRow> requests = new LinkedHashMap<>();

    @BeforeEach
    void prepareSessionAndRepository() {
        LoginUser user = new LoginUser();
        user.setUserId(7L);
        user.setPermissions(Set.of("system.read", "system.integrations.manage"));
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(user, null, java.util.List.of()));
        when(repository.findPrincipal(7L)).thenReturn(new Principal("tenant-a", "SUPER_ADMIN"));
        when(repository.find(eq("tenant-a"), anyString()))
                .thenAnswer(invocation -> rows.get(invocation.getArgument(1)));
        doAnswer(
                        invocation -> {
                            String key = invocation.getArgument(2);
                            if (!requests.containsKey(key)) {
                                IdempotencyRow row = new IdempotencyRow();
                                row.payloadHash = invocation.getArgument(3);
                                requests.put(key, row);
                            }
                            return null;
                        })
                .when(repository)
                .reserveRequest(anyString(), anyLong(), anyString(), anyString());
        when(repository.requestForUpdate(anyString(), anyLong(), anyString()))
                .thenAnswer(invocation -> requests.get(invocation.getArgument(2)));
        doAnswer(
                        invocation -> {
                            requests.get(invocation.getArgument(2)).responseJson =
                                    invocation.getArgument(3);
                            return null;
                        })
                .when(repository)
                .finishRequest(anyString(), anyLong(), anyString(), anyString());
        when(repository.insert(any()))
                .thenAnswer(
                        invocation -> {
                            Row row = invocation.getArgument(0);
                            row.verificationStatus = "UNTESTED";
                            rows.put(row.id, row);
                            return 1;
                        });
        when(repository.update(any(), anyLong())).thenReturn(1);
        service =
                new ConfigurationService(
                        repository,
                        cipher,
                        json,
                        connectionProbe,
                        mock(PlatformTransactionManager.class));
    }

    @AfterEach
    void clearSession() {
        SecurityContextHolder.clearContext();
    }

    private WriteRequest request(Map<String, SecretChange> secrets, boolean enabled) {
        return new WriteRequest(
                "AI_GPT",
                "测试GPT配置",
                enabled,
                Map.of("model", "fixture-model"),
                secrets,
                "隔离测试，不连接平台");
    }

    @Test
    void auditOnlyListsActuallyChangedPublicFields() {
        View created = service.save(null, 0, "create-fixture", request(Map.of(), false));
        service.save(created.id(), 1, "update-fixture", request(Map.of(), false));
        verify(repository)
                .audit(
                        argThat(
                                audit ->
                                        audit.tenantId().equals("tenant-a")
                                                && audit.configId().equals(created.id())
                                                && audit.actorId().equals(7L)
                                                && audit.action().equals("UPDATE")
                                                && audit.revision() == 2
                                                && audit.beforeRevision() == 1
                                                && audit.changedFieldsJson().equals("[]")));
    }

    @Test
    void historyRejectsInvisibleConfigurationBeforeReadingAudit() {
        assertThrows(ConfigurationException.class, () -> service.history("foreign", null, 50));
        verify(repository, never()).history(anyString(), anyString(), anyLong(), anyInt());
    }

    @Test
    void historyUsesTenantAndStableVersionCursorWithoutReturningStoredConfiguration()
            throws Exception {
        Row visible = new Row();
        rows.put("config-a", visible);
        AuditRow newest = new AuditRow();
        newest.id = "audit-3";
        newest.actorId = 7L;
        newest.action = "UPDATE";
        newest.revision = 3;
        newest.changedFieldsJson = "[\"secret:apiKey:replaced\"]";
        newest.reason = "轮换凭据";
        AuditRow older = new AuditRow();
        older.revision = 2;
        when(repository.history("tenant-a", "config-a", 4L, 2))
                .thenReturn(java.util.List.of(newest, older));
        AuditPage page = service.history("config-a", 4L, 1);
        assertEquals(3L, page.nextBeforeRevision());
        assertEquals(1, page.items().size());
        assertEquals(
                java.util.List.of("secret:apiKey:replaced"),
                page.items().getFirst().changedFields());
        String encoded = json.writeValueAsString(page);
        assertFalse(encoded.contains("secretsJson"));
        assertFalse(encoded.contains("settingsJson"));
        verify(repository).history("tenant-a", "config-a", 4L, 2);
    }

    @Test
    void historyBoundsPageAndRejectsInvalidCursor() {
        rows.put("config-a", new Row());
        assertThrows(ConfigurationException.class, () -> service.history("config-a", null, 101));
        assertThrows(ConfigurationException.class, () -> service.history("config-a", 0L, 50));
        when(repository.history("tenant-a", "config-a", Long.MAX_VALUE, 51))
                .thenReturn(java.util.List.of());
        assertNull(service.history("config-a", null, 50).nextBeforeRevision());
        verify(repository, times(1)).history(anyString(), anyString(), anyLong(), anyInt());
    }

    @Test
    void storesOnlyCiphertextAndReturnsOnlyConfiguredState() throws Exception {
        View view =
                service.save(
                        null,
                        0,
                        "request-0001",
                        request(
                                Map.of(
                                        "apiKey",
                                        new SecretChange("REPLACE", "fixture-secret-token")),
                                true));
        Row stored = rows.get(view.id());
        assertFalse(stored.secretsJson.contains("fixture-secret-token"));
        assertFalse(stored.settingsJson.contains("apiKey"));
        String response = json.writeValueAsString(view);
        assertFalse(response.contains("fixture-secret-token"));
        assertFalse(response.contains("v1.test."));
        assertTrue(view.secrets().get("apiKey").configured());
        verify(repository)
                .audit(
                        argThat(
                                audit ->
                                        audit.tenantId().equals("tenant-a")
                                                && audit.configId().equals(view.id())
                                                && audit.action().equals("CREATE")
                                                && audit.actorId().equals(7L)
                                                && audit.revision() == 1
                                                && audit.beforeRevision() == 0
                                                && audit.beforeHash() == null
                                                && audit.afterHash().matches("[a-f0-9]{64}")
                                                && !audit.changedFieldsJson()
                                                        .contains("fixture-secret-token")));
    }

    @Test
    void updateAuditConnectsPreviousStateAndPersistedState() {
        View first =
                service.save(
                        null,
                        0,
                        "digest-create",
                        request(
                                Map.of("apiKey", new SecretChange("REPLACE", "fixture-token")),
                                true));
        String before = ConfigurationFingerprint.of(rows.get(first.id()));
        service.save(
                first.id(),
                1,
                "digest-update",
                request(Map.of("apiKey", new SecretChange("CLEAR", null)), false));
        String after = ConfigurationFingerprint.of(rows.get(first.id()));
        verify(repository)
                .audit(
                        argThat(
                                audit ->
                                        audit.action().equals("UPDATE")
                                                && audit.beforeHash().equals(before)
                                                && audit.afterHash().equals(after)
                                                && audit.hashAlgorithm().equals("SHA256_STATE_V1")
                                                && audit.beforeRevision() == 1));
        assertNotEquals(before, after);
    }

    @Test
    void readTestAuditsActualPersistedVerificationState() {
        View first =
                service.save(
                        null,
                        0,
                        "probe-create",
                        request(
                                Map.of("apiKey", new SecretChange("REPLACE", "fixture-token")),
                                true));
        String before = ConfigurationFingerprint.of(rows.get(first.id()));
        when(connectionProbe.check(eq("AI_GPT"), anyMap(), anyMap()))
                .thenReturn(new ConnectionProbe.Result("READ_VERIFIED", "只读通过"));
        when(repository.recordVerification("tenant-a", first.id(), 1, "READ_VERIFIED"))
                .thenAnswer(
                        call -> {
                            Row row = rows.get(first.id());
                            row.revision++;
                            row.verificationStatus = "READ_VERIFIED";
                            return 1;
                        });
        service.test(first.id(), 1, "人工核对连接");
        String after = ConfigurationFingerprint.of(rows.get(first.id()));
        verify(repository)
                .audit(
                        argThat(
                                audit ->
                                        audit.action().equals("READ_TEST")
                                                && audit.reason().equals("人工核对连接")
                                                && audit.beforeHash().equals(before)
                                                && audit.afterHash().equals(after)
                                                && audit.beforeRevision() == 1
                                                && audit.revision() == 2));
    }

    @Test
    void changedTenantDuringProbeCannotWriteOldScopeAudit() {
        View first =
                service.save(
                        null,
                        0,
                        "scope-create",
                        request(
                                Map.of("apiKey", new SecretChange("REPLACE", "fixture-token")),
                                true));
        when(connectionProbe.check(eq("AI_GPT"), anyMap(), anyMap()))
                .thenAnswer(
                        call -> {
                            when(repository.findPrincipal(7L))
                                    .thenReturn(new Principal("tenant-b", "SUPER_ADMIN"));
                            return new ConnectionProbe.Result("READ_VERIFIED", "只读通过");
                        });
        ConfigurationException error =
                assertThrows(
                        ConfigurationException.class, () -> service.test(first.id(), 1, "人工核对连接"));
        assertEquals("CONFIGURATION_SCOPE_CHANGED", error.code());
        verify(repository, never())
                .recordVerification(anyString(), anyString(), anyLong(), anyString());
        verify(repository, never()).audit(argThat(audit -> audit.action().equals("READ_TEST")));
    }

    @Test
    void staleReadTestCannotAppendAudit() {
        View first =
                service.save(
                        null,
                        0,
                        "stale-create",
                        request(
                                Map.of("apiKey", new SecretChange("REPLACE", "fixture-token")),
                                true));
        when(connectionProbe.check(eq("AI_GPT"), anyMap(), anyMap()))
                .thenReturn(new ConnectionProbe.Result("FAILED", "验证失败"));
        when(repository.recordVerification(anyString(), anyString(), anyLong(), anyString()))
                .thenReturn(0);
        assertThrows(ConfigurationException.class, () -> service.test(first.id(), 1, "人工核对连接"));
        verify(repository, never()).audit(argThat(audit -> audit.action().equals("READ_TEST")));
    }

    @Test
    void sameKeySamePayloadReplaysWithoutAnotherInsert() {
        WriteRequest request = request(Map.of(), false);
        View first = service.save(null, 0, "request-0002", request);
        View second = service.save(null, 0, "request-0002", request);
        assertEquals(first.id(), second.id());
        verify(repository, times(1)).insert(any());
    }

    @Test
    void sameKeyDifferentPayloadConflicts() {
        service.save(null, 0, "request-0003", request(Map.of(), false));
        ConfigurationException error =
                assertThrows(
                        ConfigurationException.class,
                        () ->
                                service.save(
                                        null,
                                        0,
                                        "request-0003",
                                        new WriteRequest(
                                                "AI_GPT", "另一个名称", false, Map.of(), Map.of(),
                                                "测试")));
        assertEquals("IDEMPOTENCY_CONFLICT", error.code());
    }

    @Test
    void keepNeverStoresMaskAndClearRequiresExplicitAction() {
        View first =
                service.save(
                        null,
                        0,
                        "request-0004",
                        request(
                                Map.of("apiKey", new SecretChange("REPLACE", "fixture-token")),
                                true));
        String encrypted = rows.get(first.id()).secretsJson;
        View kept =
                service.save(
                        first.id(),
                        1,
                        "request-0005",
                        request(Map.of("apiKey", new SecretChange("KEEP", null)), true));
        assertEquals(encrypted, rows.get(first.id()).secretsJson);
        View cleared =
                service.save(
                        first.id(),
                        kept.revision(),
                        "request-0006",
                        request(Map.of("apiKey", new SecretChange("CLEAR", null)), false));
        assertFalse(cleared.secrets().get("apiKey").configured());
    }

    @Test
    void cannotEnableWithoutCredentialsOrSubmitDisplayMask() {
        assertEquals(
                "SECRET_REQUIRED",
                assertThrows(
                                ConfigurationException.class,
                                () ->
                                        service.save(
                                                null, 0, "request-0007", request(Map.of(), true)))
                        .code());
        assertEquals(
                "SECRET_INVALID",
                assertThrows(
                                ConfigurationException.class,
                                () ->
                                        service.save(
                                                null,
                                                0,
                                                "request-0008",
                                                request(
                                                        Map.of(
                                                                "apiKey",
                                                                new SecretChange(
                                                                        "REPLACE", "****")),
                                                        false)))
                        .code());
    }

    @Test
    void tenantAndDataRoleAreCheckedEvenWithRuoYiAdminPermission() {
        when(repository.findPrincipal(7L)).thenReturn(new Principal("tenant-a", "TEAM_ADMIN"));
        assertEquals(403, assertThrows(ConfigurationException.class, service::list).status());
        when(repository.findPrincipal(7L)).thenReturn(new Principal("tenant-a", "SUPER_ADMIN"));
        assertEquals(
                404,
                assertThrows(ConfigurationException.class, () -> service.get("other-tenant-config"))
                        .status());
    }

    @Test
    void revokedPrincipalCannotReplayPreviousResult() {
        WriteRequest request = request(Map.of(), false);
        service.save(null, 0, "request-0009", request);
        when(repository.findPrincipal(7L)).thenReturn(null);
        assertEquals(
                403,
                assertThrows(
                                ConfigurationException.class,
                                () -> service.save(null, 0, "request-0009", request))
                        .status());
    }

    @Test
    void rejectsOldRevisionAndUnknownSecretSlots() {
        View value = service.save(null, 0, "request-0010", request(Map.of(), false));
        assertEquals(
                409,
                assertThrows(
                                ConfigurationException.class,
                                () ->
                                        service.save(
                                                value.id(),
                                                99,
                                                "request-0011",
                                                request(Map.of(), false)))
                        .status());
        assertEquals(
                "UNKNOWN_SECRET",
                assertThrows(
                                ConfigurationException.class,
                                () ->
                                        service.save(
                                                null,
                                                0,
                                                "request-0012",
                                                request(
                                                        Map.of(
                                                                "accessToken",
                                                                new SecretChange(
                                                                        "REPLACE", "fixture")),
                                                        false)))
                        .code());
    }

    @Test
    void strictParserRejectsUnknownFieldsAndBooleanCoercionWithoutLeakingInput() throws Exception {
        for (String body :
                new String[] {
                    "{\"section\":\"AI_GPT\",\"enabled\":\"false\"}",
                    "{\"enabled\":false,\"unknown\":\"fixture-secret\"}"
                }) {
            ConfigurationException error =
                    assertThrows(
                            ConfigurationException.class, () -> service.parse(json.readTree(body)));
            assertEquals(400, error.status());
            assertFalse(error.getMessage().contains("fixture-secret"));
        }
    }

    @Test
    void invalidTestReasonCannotCallProviderOrWriteVerification() {
        View created = service.save(null, 0, "reason-create", request(Map.of(), false));
        for (String reason : new String[] {null, "", "   ", "x".repeat(501), "\n人工原因", "人工\t原因"}) {
            assertThrows(ConfigurationException.class, () -> service.test(created.id(), 1, reason));
        }
        verifyNoInteractions(connectionProbe);
        verify(repository, never())
                .recordVerification(anyString(), anyString(), anyLong(), anyString());
        verify(repository, never()).audit(argThat(audit -> audit.action().equals("READ_TEST")));
    }

    @Test
    void readTestBodyRejectsUnknownFieldsAndWrongReasonTypes() throws Exception {
        for (String body :
                new String[] {
                    "{}",
                    "null",
                    "[]",
                    "{\"reason\":null}",
                    "{\"reason\":7}",
                    "{\"reason\":\"人工原因\",\"token\":\"fixture-private\"}"
                }) {
            var error =
                    assertThrows(
                            ConfigurationException.class,
                            () -> service.parseTestReason(new ObjectMapper().readTree(body)));
            assertEquals("INVALID_STRUCTURE", error.code());
            assertFalse(error.getMessage().contains("fixture-private"));
        }
        assertEquals(
                "人工原因",
                service.parseTestReason(new ObjectMapper().readTree("{\"reason\":\"人工原因\"}")));
    }
}

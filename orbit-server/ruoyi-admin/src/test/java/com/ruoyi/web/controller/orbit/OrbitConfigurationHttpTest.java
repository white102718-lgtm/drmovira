package com.ruoyi.web.controller.orbit;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.framework.config.SecurityConfig;
import com.ruoyi.framework.config.properties.PermitAllUrlProperties;
import com.ruoyi.framework.security.filter.JwtAuthenticationTokenFilter;
import com.ruoyi.framework.security.handle.AuthenticationEntryPointImpl;
import com.ruoyi.framework.security.handle.LogoutSuccessHandlerImpl;
import com.ruoyi.framework.web.service.PermissionService;
import com.ruoyi.framework.web.service.TokenService;
import com.ruoyi.system.orbit.config.*;
import com.ruoyi.system.orbit.config.ConfigurationModels.*;
import com.ruoyi.web.config.orbit.OrbitConfigurationSecurity;
import jakarta.servlet.http.HttpServletRequest;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.PlatformTransactionManager;

/** 真实Servlet路由/若依JWT过滤器/方法权限/Service/异常边界；会话存储、Mapper和平台传输使用fixture。 */
@WebMvcTest(OrbitConfigurationController.class)
@AutoConfigureMockMvc(print = MockMvcPrint.NONE)
@Import({
    SecurityConfig.class,
    OrbitConfigurationSecurity.class,
    JwtAuthenticationTokenFilter.class,
    AuthenticationEntryPointImpl.class,
    LogoutSuccessHandlerImpl.class,
    PermissionService.class,
    OrbitConfigurationExceptionHandler.class,
    ConfigurationService.class,
    OrbitConfigurationHttpTest.Fixtures.class
})
@ExtendWith(OutputCaptureExtension.class)
class OrbitConfigurationHttpTest {
    private static final String API = "/api/v1/system-configurations";
    private static final String PRIVATE = "fixture-sensitive-value-not-a-real-token";
    @Autowired MockMvc mvc;
    @MockitoBean TokenService tokens;
    @MockitoBean com.ruoyi.common.core.redis.RedisCache redis;
    @MockitoBean ConfigurationMapper repository;
    @MockitoBean ConnectionProbe probe;
    @MockitoBean PlatformTransactionManager transactions;
    @MockitoBean PermitAllUrlProperties permitAll;
    private LoginUser login;
    private final Map<String, Row> rows = new HashMap<>();
    private final Map<String, IdempotencyRow> requests = new HashMap<>();

    @TestConfiguration
    static class Fixtures {
        @Bean
        SecretCipher cipher() {
            return new SecretCipher(
                    "fixture", Map.of("fixture", Base64.getEncoder().encodeToString(new byte[32])));
        }
    }

    @BeforeEach
    void sessionAndStorage() {
        rows.clear();
        requests.clear();
        login = new LoginUser();
        login.setUserId(7L);
        com.ruoyi.common.core.domain.entity.SysUser user =
                new com.ruoyi.common.core.domain.entity.SysUser();
        user.setUserId(7L);
        user.setUserName("fixture-admin");
        login.setUser(user);
        login.setPermissions(Set.of("system.read", "system.integrations.manage"));
        when(tokens.getLoginUser(any(HttpServletRequest.class)))
                .thenAnswer(
                        call ->
                                "Bearer fixture-session"
                                                .equals(
                                                        ((HttpServletRequest) call.getArgument(0))
                                                                .getHeader("Authorization"))
                                        ? login
                                        : null);
        when(repository.findPrincipal(7L)).thenReturn(new Principal("tenant-a", "SUPER_ADMIN"));
        when(repository.list("tenant-a")).thenAnswer(call -> new ArrayList<>(rows.values()));
        when(repository.find(eq("tenant-a"), anyString()))
                .thenAnswer(call -> rows.get(call.getArgument(1)));
        doAnswer(
                        call -> {
                            IdempotencyRow row = new IdempotencyRow();
                            row.payloadHash = call.getArgument(3);
                            requests.putIfAbsent(call.getArgument(2), row);
                            return null;
                        })
                .when(repository)
                .reserveRequest(anyString(), anyLong(), anyString(), anyString());
        when(repository.requestForUpdate(anyString(), anyLong(), anyString()))
                .thenAnswer(call -> requests.get(call.getArgument(2)));
        doAnswer(
                        call -> {
                            requests.get(call.getArgument(2)).responseJson = call.getArgument(3);
                            return null;
                        })
                .when(repository)
                .finishRequest(anyString(), anyLong(), anyString(), anyString());
        when(repository.insert(any()))
                .thenAnswer(
                        call -> {
                            Row row = call.getArgument(0);
                            row.verificationStatus = "UNTESTED";
                            row.updatedAt = Instant.parse("2026-11-07T00:00:00Z");
                            rows.put(row.id, row);
                            return 1;
                        });
    }

    private MockHttpServletRequestBuilder authenticated(MockHttpServletRequestBuilder request) {
        return request.header("Authorization", "Bearer fixture-session");
    }

    private String body() {
        return "{\"section\":\"AI_GPT\",\"name\":\"测试模型\",\"enabled\":true,\"settings\":{\"model\":\"fixture-model\"},\"secrets\":{\"apiKey\":{\"operation\":\"REPLACE\",\"value\":\""
                + PRIVATE
                + "\"}},\"reason\":\"接口验证\"}";
    }

    @Test
    void unauthenticatedRequestHasReal401SafeBodyAndNoCache() throws Exception {
        mvc.perform(get(API + "/" + PRIVATE))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(header().string("Pragma", "no-cache"))
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"))
                .andExpect(jsonPath("$.request_id").isNotEmpty())
                .andExpect(
                        content()
                                .string(
                                        org.hamcrest.Matchers.not(
                                                org.hamcrest.Matchers.containsString(PRIVATE))))
                .andExpect(cookie().doesNotExist("JSESSIONID"));
        verifyNoInteractions(repository);
    }

    @Test
    void originalRuoYiAuthenticationResponseIsPreserved() throws Exception {
        mvc.perform(get("/system/user/list"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(401));
    }

    @ParameterizedTest
    @ValueSource(strings = {"system.read", "system.integrations.manage", "unrelated.permission"})
    void requiresBothMenuAndIntegrationPermission(String onlyPermission) throws Exception {
        login.setPermissions(Set.of(onlyPermission));
        mvc.perform(authenticated(get(API + "/metadata")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"))
                .andExpect(header().string("Cache-Control", "no-store"));
        verifyNoInteractions(repository);
    }

    @ParameterizedTest
    @ValueSource(strings = {"USER", "TEAM_ADMIN"})
    void dataRoleCannotBeBypassedByRuoYiWildcard(String dataRole) throws Exception {
        login.setPermissions(Set.of("*:*:*"));
        when(repository.findPrincipal(7L)).thenReturn(new Principal("tenant-a", dataRole));
        mvc.perform(authenticated(get(API)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("CONFIGURATION_FORBIDDEN"));
        verify(repository, never()).list(anyString());
    }

    @Test
    void revokedTenantMappingIsDeniedBeforeMetadata() throws Exception {
        when(repository.findPrincipal(7L)).thenReturn(null);
        mvc.perform(authenticated(get(API + "/metadata"))).andExpect(status().isForbidden());
    }

    @Test
    void metadataAndListAreReadableWithoutCredentialValues() throws Exception {
        mvc.perform(authenticated(get(API + "/metadata")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.encryptionReady").value(true))
                .andExpect(jsonPath("$.sections").isArray());
        mvc.perform(authenticated(get(API)))
                .andExpect(status().isOk())
                .andExpect(content().json("[]"));
    }

    @Test
    void createReturns201AndReplayGetListNeverEchoSecret(CapturedOutput output) throws Exception {
        var response =
                mvc.perform(
                                authenticated(post(API))
                                        .header("Idempotency-Key", "http-create-1")
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(body()))
                        .andExpect(status().isCreated())
                        .andExpect(jsonPath("$.secrets.apiKey.configured").value(true))
                        .andExpect(jsonPath("$.updatedAt").value("2026-11-07T00:00:00Z"))
                        .andReturn()
                        .getResponse()
                        .getContentAsString();
        String id =
                new com.fasterxml.jackson.databind.ObjectMapper()
                        .readTree(response)
                        .path("id")
                        .asText();
        String replay =
                mvc.perform(
                                authenticated(post(API))
                                        .header("Idempotency-Key", "http-create-1")
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(body()))
                        .andExpect(status().isCreated())
                        .andReturn()
                        .getResponse()
                        .getContentAsString();
        String detail =
                mvc.perform(authenticated(get(API + "/" + id)))
                        .andExpect(status().isOk())
                        .andReturn()
                        .getResponse()
                        .getContentAsString();
        String list =
                mvc.perform(authenticated(get(API)))
                        .andExpect(status().isOk())
                        .andReturn()
                        .getResponse()
                        .getContentAsString();
        for (String value : List.of(response, replay, detail, list, output.getAll())) {
            assertFalse(value.contains(PRIVATE));
            assertFalse(value.contains("v1.fixture."));
        }
        verify(repository, times(1)).insert(any());
        verifyNoInteractions(redis);
    }

    @Test
    void malformedJsonAndUnknownFieldsFailWithoutLeakingRequest(CapturedOutput output)
            throws Exception {
        for (String value :
                List.of(
                        "{\"secret\":\"" + PRIVATE + "\",",
                        body().replace("\"reason\"", "\"" + PRIVATE + "\""))) {
            var response =
                    mvc.perform(
                                    authenticated(post(API))
                                            .header("Idempotency-Key", "http-invalid-1")
                                            .contentType(MediaType.APPLICATION_JSON)
                                            .content(value))
                            .andExpect(status().isBadRequest())
                            .andReturn()
                            .getResponse();
            assertFalse(response.getContentAsString().contains(PRIVATE));
            assertEquals("no-store", response.getHeader("Cache-Control"));
        }
        assertFalse(output.getAll().contains(PRIVATE));
    }

    @Test
    void missingHeadersAndInvalidRevisionAndQueryHaveSafe400(CapturedOutput output)
            throws Exception {
        mvc.perform(
                        authenticated(post(API))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(body()))
                .andExpect(status().isBadRequest());
        mvc.perform(
                        authenticated(put(API + "/config-a"))
                                .header("Idempotency-Key", "http-edit-1")
                                .header("If-Match", PRIVATE)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(body()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("REVISION_REQUIRED"));
        var response =
                mvc.perform(
                                authenticated(get(API + "/config-a/history"))
                                        .param("pageSize", PRIVATE))
                        .andExpect(status().isBadRequest())
                        .andReturn()
                        .getResponse();
        assertFalse(response.getContentAsString().contains(PRIVATE));
        assertFalse(output.getAll().contains(PRIVATE));
    }

    @Test
    void invisibleConfigurationReturns404AndHistoryDoesNotQueryAudit() throws Exception {
        mvc.perform(authenticated(get(API + "/foreign/history"))).andExpect(status().isNotFound());
        verify(repository, never()).history(anyString(), anyString(), anyLong(), anyInt());
    }

    @Test
    void unexpectedRepositoryErrorDoesNotEscapeToResponseOrLogs(CapturedOutput output)
            throws Exception {
        when(repository.list("tenant-a")).thenThrow(new IllegalStateException(PRIVATE));
        var response =
                mvc.perform(authenticated(get(API)))
                        .andExpect(status().isInternalServerError())
                        .andExpect(jsonPath("$.code").value("CONFIGURATION_UNAVAILABLE"))
                        .andReturn()
                        .getResponse();
        assertFalse(response.getContentAsString().contains(PRIVATE));
        assertFalse(output.getAll().contains(PRIVATE));
    }

    @Test
    void riskEditingRequiresAdditionalReleasePermission() throws Exception {
        mvc.perform(
                        authenticated(post(API))
                                .header("Idempotency-Key", "http-risk-1")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"section\":\"RISK\",\"name\":\"风控\",\"enabled\":false,\"settings\":{},\"reason\":\"fixture\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("POLICY_FORBIDDEN"));
    }

    @Test
    void staleVersionAndDuplicateNameReturnSafe409(CapturedOutput output) throws Exception {
        var creation =
                mvc.perform(
                                authenticated(post(API))
                                        .header("Idempotency-Key", "http-conflict-create")
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(body()))
                        .andExpect(status().isCreated())
                        .andReturn()
                        .getResponse()
                        .getContentAsString();
        String id =
                new com.fasterxml.jackson.databind.ObjectMapper()
                        .readTree(creation)
                        .path("id")
                        .asText();
        mvc.perform(
                        authenticated(put(API + "/" + id))
                                .header("Idempotency-Key", "http-conflict-update")
                                .header("If-Match", "\"2\"")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(body()))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("REVISION_CONFLICT"));
        doThrow(new org.springframework.dao.DuplicateKeyException(PRIVATE))
                .when(repository)
                .insert(any());
        var response =
                mvc.perform(
                                authenticated(post(API))
                                        .header("Idempotency-Key", "http-duplicate-create")
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(body()))
                        .andExpect(status().isConflict())
                        .andExpect(jsonPath("$.code").value("DUPLICATE_CONFIGURATION"))
                        .andReturn()
                        .getResponse();
        assertFalse(response.getContentAsString().contains(PRIVATE));
        assertFalse(output.getAll().contains(PRIVATE));
    }

    @Test
    void historyResponseExposesSummaryOnlyAndBindsCursor() throws Exception {
        Row row = new Row();
        rows.put("config-a", row);
        AuditRow audit = new AuditRow();
        audit.id = "audit-a";
        audit.actorId = 7L;
        audit.action = "UPDATE";
        audit.revision = 2;
        audit.beforeRevision = 1L;
        audit.beforeHash = "a".repeat(64);
        audit.afterHash = "b".repeat(64);
        audit.hashAlgorithm = "SHA256_STATE_V1";
        audit.changedFieldsJson = "[\"secret:apiKey:replaced\"]";
        when(repository.history("tenant-a", "config-a", 3, 51)).thenReturn(List.of(audit));
        mvc.perform(authenticated(get(API + "/config-a/history")).param("beforeRevision", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].beforeRevision").value(1))
                .andExpect(jsonPath("$.items[0].afterHash").value("b".repeat(64)))
                .andExpect(jsonPath("$.items[0].changedFieldsJson").doesNotExist())
                .andExpect(jsonPath("$.nextBeforeRevision").isEmpty());
        verify(repository).history("tenant-a", "config-a", 3, 51);
    }

    @Test
    void readTestRejectsMissingInvalidAndCredentialBearingReasonWithoutProbe(CapturedOutput output)
            throws Exception {
        Row row = new Row();
        row.revision = 1;
        rows.put("config-a", row);
        for (String body :
                new String[] {
                    "{}",
                    "{\"reason\":null}",
                    "{\"reason\":7}",
                    "{\"reason\":\"人工原因\",\"token\":\"" + PRIVATE + "\"}"
                }) {
            mvc.perform(
                            authenticated(post(API + "/config-a/test"))
                                    .header("If-Match", "\"1\"")
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content(body))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.code").value("INVALID_STRUCTURE"));
        }
        mvc.perform(
                        authenticated(post(API + "/config-a/test"))
                                .header("If-Match", "\"1\"")
                                .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest());
        mvc.perform(
                        authenticated(post(API + "/config-a/test"))
                                .header("If-Match", "\"1\"")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"reason\":\"   \"}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("FIELD_INVALID"));
        verifyNoInteractions(probe);
        verify(repository, never())
                .recordVerification(anyString(), anyString(), anyLong(), anyString());
        verify(repository, never()).audit(any());
        assertFalse(output.getAll().contains(PRIVATE));
    }
}

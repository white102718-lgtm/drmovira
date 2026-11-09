package com.ruoyi.system.orbit.config;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

/** 可控HTTP传输验证官方域名、只读方法与错误脱敏；不调用真实平台。 */
class ConnectionProbeTest {
    @Test
    void springCanConstructProbeWithoutUsingTestTransport() {
        try (var context =
                new org.springframework.context.annotation.AnnotationConfigApplicationContext()) {
            context.registerBean(ObjectMapper.class, () -> new ObjectMapper());
            context.register(ConnectionProbe.class);
            context.refresh();
            assertNotNull(context.getBean(ConnectionProbe.class));
        }
    }

    @SuppressWarnings("unchecked")
    private HttpResponse<InputStream> response(int status, String body) {
        HttpResponse<InputStream> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(status);
        when(response.body())
                .thenReturn(new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8)));
        return response;
    }

    @Test
    void gptOnlyCallsOfficialReadEndpointAndNeverPlacesKeyInUrl() throws Exception {
        HttpClient transport = mock(HttpClient.class);
        when(transport.send(any(), any(HttpResponse.BodyHandler.class)))
                .thenAnswer(invocation -> response(200, "{\"id\":\"fixture-model\"}"));
        ConnectionProbe.Result result =
                new ConnectionProbe(new ObjectMapper(), transport)
                        .check(
                                "AI_GPT",
                                Map.of("model", "fixture-model"),
                                Map.of("apiKey", "fixture-secret"));
        assertEquals("READ_VERIFIED", result.status());
        ArgumentCaptor<HttpRequest> capture = ArgumentCaptor.forClass(HttpRequest.class);
        verify(transport).send(capture.capture(), any(HttpResponse.BodyHandler.class));
        assertEquals("GET", capture.getValue().method());
        assertEquals("api.openai.com", capture.getValue().uri().getHost());
        assertFalse(capture.getValue().uri().toString().contains("fixture-secret"));
        assertFalse(result.message().contains("fixture-secret"));
    }

    @Test
    void claudeUsesOwnProtocolVersionAndWorkspace() throws Exception {
        HttpClient transport = mock(HttpClient.class);
        when(transport.send(any(), any(HttpResponse.BodyHandler.class)))
                .thenAnswer(invocation -> response(200, "{\"id\":\"claude-fixture\"}"));
        new ConnectionProbe(new ObjectMapper(), transport)
                .check(
                        "AI_CLAUDE",
                        Map.of(
                                "model",
                                "claude-fixture",
                                "apiVersion",
                                "2026-10-21",
                                "workspaceId",
                                "wrkspc_fixture"),
                        Map.of("apiKey", "fixture-secret"));
        ArgumentCaptor<HttpRequest> capture = ArgumentCaptor.forClass(HttpRequest.class);
        verify(transport).send(capture.capture(), any(HttpResponse.BodyHandler.class));
        assertEquals("api.anthropic.com", capture.getValue().uri().getHost());
        assertEquals(
                "2026-10-21",
                capture.getValue().headers().firstValue("anthropic-version").orElseThrow());
        assertEquals(
                "wrkspc_fixture",
                capture.getValue().headers().firstValue("anthropic-workspace-id").orElseThrow());
    }

    @Test
    void mismatchedBusinessEvidenceCannotPass() throws Exception {
        HttpClient transport = mock(HttpClient.class);
        when(transport.send(any(), any(HttpResponse.BodyHandler.class)))
                .thenAnswer(invocation -> response(200, "{\"id\":\"other-business\"}"));
        assertEquals(
                "FAILED",
                new ConnectionProbe(new ObjectMapper(), transport)
                        .check(
                                "META_BM",
                                Map.of("graphVersion", "v25.0", "businessId", "123"),
                                Map.of("accessToken", "fixture-secret"))
                        .status());
    }

    @Test
    void errorsAndMissingEvidenceNeverLeakProviderBody() throws Exception {
        for (int status : new int[] {200, 301, 401, 403, 429, 500}) {
            HttpClient transport = mock(HttpClient.class);
            when(transport.send(any(), any(HttpResponse.BodyHandler.class)))
                    .thenAnswer(invocation -> response(status, "{\"error\":\"fixture-secret\"}"));
            ConnectionProbe.Result result =
                    new ConnectionProbe(new ObjectMapper(), transport)
                            .check(
                                    "AI_GPT",
                                    Map.of("model", "fixture"),
                                    Map.of("apiKey", "fixture-secret"));
            assertEquals("FAILED", result.status());
            assertFalse(result.message().contains("fixture-secret"));
        }
    }

    @Test
    void missingCredentialsAndUnsupportedConnectorAreBlockedWithoutNetwork() {
        HttpClient transport = mock(HttpClient.class);
        ConnectionProbe probe = new ConnectionProbe(new ObjectMapper(), transport);
        assertEquals(
                "BLOCKED", probe.check("AI_GPT", Map.of("model", "fixture"), Map.of()).status());
        assertEquals("BLOCKED", probe.check("STORAGE", Map.of(), Map.of()).status());
        verifyNoInteractions(transport);
    }

    @Test
    void metaAppRequiresActualSecretBeforeAnyNetworkRequest() {
        HttpClient transport = mock(HttpClient.class);
        ConnectionProbe probe = new ConnectionProbe(new ObjectMapper(), transport);
        Map<String, Object> settings = Map.of("graphVersion", "v25.0", "appId", "123");
        for (Map<String, String> absent :
                java.util.List.of(
                        Map.<String, String>of(),
                        Map.of("appSecret", ""),
                        Map.of("appSecret", "   "))) {
            assertEquals("BLOCKED", probe.check("META_APP", settings, absent).status());
        }
        verifyNoInteractions(transport);
    }

    @Test
    void metaAppEvidenceMustMatchConfiguredIdAndUseOnlyBearerCredential() throws Exception {
        for (String returnedId : new String[] {"other-app", "123"}) {
            HttpClient transport = mock(HttpClient.class);
            when(transport.send(any(), any(HttpResponse.BodyHandler.class)))
                    .thenAnswer(invocation -> response(200, "{\"id\":\"" + returnedId + "\"}"));
            ConnectionProbe.Result result =
                    new ConnectionProbe(new ObjectMapper(), transport)
                            .check(
                                    "META_APP",
                                    Map.of("graphVersion", "v25.0", "appId", "123"),
                                    Map.of("appSecret", "fixture-app-secret"));
            assertEquals(returnedId.equals("123") ? "READ_VERIFIED" : "FAILED", result.status());
            ArgumentCaptor<HttpRequest> capture = ArgumentCaptor.forClass(HttpRequest.class);
            verify(transport).send(capture.capture(), any(HttpResponse.BodyHandler.class));
            HttpRequest sent = capture.getValue();
            assertEquals("GET", sent.method());
            assertEquals(
                    "https://graph.facebook.com/v25.0/123?fields=id,name", sent.uri().toString());
            assertEquals(
                    "Bearer 123|fixture-app-secret",
                    sent.headers().firstValue("Authorization").orElseThrow());
            assertFalse(sent.uri().toString().contains("fixture-app-secret"));
            assertFalse(result.message().contains("fixture-app-secret"));
        }
    }
}

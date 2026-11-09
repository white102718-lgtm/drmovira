package com.ruoyi.web.controller.orbit;

import static org.junit.jupiter.api.Assertions.*;

import com.ruoyi.RuoYiApplication;
import com.ruoyi.system.orbit.config.ConnectionProbe;
import io.lettuce.core.RedisClient;
import java.nio.file.*;
import java.security.SecureRandom;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.support.EncodedResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

/** 完整若依应用、实际登录页/菜单和Chromium；仅外部平台探测使用fixture，验证码另验。 */
@SpringBootTest(
        classes = RuoYiApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "server.address=127.0.0.1",
            "logging.config=classpath:logback-orbit-test.xml",
            "logging.level.com.ruoyi=INFO",
            "spring.quartz.auto-startup=false",
            "spring.data.redis.host=127.0.0.1",
            "spring.data.redis.port=16379",
            "spring.data.redis.database=14",
            "spring.data.redis.password=",
            "spring.datasource.druid.statViewServlet.enabled=false",
            "spring.datasource.druid.filter.stat.enabled=false"
        })
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrbitApplicationBrowserIT {
    private static Path root;
    private static JdbcTemplate admin;
    private static String database;
    // 仅临时测试库的公开fixture账号；与任何用户私有配置无关。
    private static final String PASSWORD = "OrbitFixture!2026";
    private static final String SIGNING = randomKey(64);
    private static final String ENCRYPTION = randomKey(32);
    @LocalServerPort int port;
    @MockitoBean ConnectionProbe externalPlatform;

    @org.springframework.beans.factory.annotation.Autowired
    com.fasterxml.jackson.databind.ObjectMapper json;

    @org.springframework.beans.factory.annotation.Autowired JdbcTemplate jdbc;

    @org.springframework.beans.factory.annotation.Autowired
    com.ruoyi.system.orbit.scope.AccountDirectoryPublisher directory;

    private java.net.http.HttpResponse<String> call(
            String method, String path, String token, String body, Map<String, String> headers)
            throws Exception {
        var request =
                java.net.http.HttpRequest.newBuilder(
                                java.net.URI.create("http://127.0.0.1:" + port + path))
                        .header("Content-Type", "application/json");
        if (token != null) request.header("Authorization", "Bearer " + token);
        headers.forEach(request::header);
        request.method(
                method,
                body == null
                        ? java.net.http.HttpRequest.BodyPublishers.noBody()
                        : java.net.http.HttpRequest.BodyPublishers.ofString(body));
        return java.net.http.HttpClient.newHttpClient()
                .send(request.build(), java.net.http.HttpResponse.BodyHandlers.ofString());
    }

    private String scopeLogin() throws Exception {
        return scopeLogin("admin");
    }

    private String scopeLogin(String username) throws Exception {
        var response =
                call(
                        "POST",
                        "/login",
                        null,
                        json.writeValueAsString(Map.of("username", username, "password", PASSWORD)),
                        Map.of());
        assertEquals(200, response.statusCode());
        String token = json.readTree(response.body()).path("token").asText();
        assertFalse(token.isBlank());
        return token;
    }

    private com.fasterxml.jackson.databind.node.ObjectNode scopeFilter() {
        var body = json.createObjectNode().put("mode", "FILTER");
        body.putArray("account_ids");
        body.putObject("filter")
                .put("q", "")
                .putNull("status")
                .putNull("auth_status")
                .putNull("operator_user_id")
                .putNull("vendor_id");
        return body;
    }

    private Map<String, String> scopeHeaders(String token) throws Exception {
        var response = call("GET", "/api/v1/scope-snapshots/csrf", token, null, Map.of());
        assertEquals(200, response.statusCode());
        return Map.of(
                "Idempotency-Key", UUID.randomUUID().toString(),
                "X-CSRF-Token", json.readTree(response.body()).path("csrf_token").asText());
    }

    /** 对HTTP真实响应和事务回滚逐项断言，不将循环断言数量当作独立测试数。 */
    private void scopeRejectedWithoutInsert(
            String token, Map<String, String> headers, String body, int status, String code)
            throws Exception {
        long before =
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orbit_account_scope_snapshot", Long.class);
        var response = call("POST", "/api/v1/scope-snapshots", token, body, headers);
        assertEquals(status, response.statusCode(), "范围字段反例状态");
        var error = json.readTree(response.body());
        assertEquals(code, error.path("code").asText());
        assertFalse(error.path("retryable").asBoolean());
        assertTrue(error.path("field_errors").isArray());
        assertEquals(
                response.headers().firstValue("X-Request-ID").orElseThrow(),
                error.path("request_id").asText());
        assertTrue(
                response.headers().firstValue("Cache-Control").orElseThrow().contains("no-store"));
        assertEquals(
                before,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orbit_account_scope_snapshot", Long.class));
    }

    @Test
    void scopeHttpEveryRequestFieldRejectsInvalidShapesWithoutPersisting() throws Exception {
        String token = scopeLogin();
        var headers = scopeHeaders(token);
        // 缺失与额外字段属于合同结构错误；每个根字段及每个筛选字段均检查。
        for (String field : List.of("mode", "account_ids", "filter")) {
            var body = scopeFilter();
            body.remove(field);
            scopeRejectedWithoutInsert(token, headers, body.toString(), 400, "INVALID_REQUEST");
        }
        for (String field :
                List.of("q", "status", "auth_status", "operator_user_id", "vendor_id")) {
            var body = scopeFilter();
            ((com.fasterxml.jackson.databind.node.ObjectNode) body.path("filter")).remove(field);
            scopeRejectedWithoutInsert(token, headers, body.toString(), 400, "INVALID_REQUEST");
        }
        for (String field : List.of("tenant_id", "actor_id", "count", "scope_version", "hash")) {
            var body = scopeFilter().put(field, "injected");
            scopeRejectedWithoutInsert(token, headers, body.toString(), 400, "UNKNOWN_FIELD");
        }
        for (String field : List.of("mode", "account_ids", "filter")) {
            var body = scopeFilter().put(field, 123);
            scopeRejectedWithoutInsert(token, headers, body.toString(), 400, "INVALID_REQUEST");
        }
        for (String field :
                List.of("q", "status", "auth_status", "operator_user_id", "vendor_id")) {
            var body = scopeFilter();
            ((com.fasterxml.jackson.databind.node.ObjectNode) body.path("filter")).put(field, true);
            scopeRejectedWithoutInsert(
                    token, headers, body.toString(), 422, "BUSINESS_VALIDATION_FAILED");
        }
        for (String raw :
                List.of(
                        "null",
                        "[]",
                        "{}",
                        "{",
                        scopeFilter() + " {}",
                        scopeFilter()
                                .toString()
                                .replace(
                                        "\"mode\":\"FILTER\"",
                                        "\"mode\":\"FILTER\",\"mode\":\"IDS\"")))
            scopeRejectedWithoutInsert(token, headers, raw, 400, "INVALID_REQUEST");
        for (String mode : List.of("filter", "ALL", "", " IDS "))
            scopeRejectedWithoutInsert(
                    token,
                    headers,
                    scopeFilter().put("mode", mode).toString(),
                    422,
                    "BUSINESS_VALIDATION_FAILED");
        for (String field : List.of("status", "auth_status", "operator_user_id", "vendor_id")) {
            var body = scopeFilter();
            ((com.fasterxml.jackson.databind.node.ObjectNode) body.path("filter"))
                    .put(field, "invalid");
            scopeRejectedWithoutInsert(
                    token, headers, body.toString(), 422, "BUSINESS_VALIDATION_FAILED");
        }
        for (String q : List.of("a".repeat(101), "😀".repeat(101), "a\u0001b")) {
            var body = scopeFilter();
            ((com.fasterxml.jackson.databind.node.ObjectNode) body.path("filter")).put("q", q);
            scopeRejectedWithoutInsert(
                    token, headers, body.toString(), 422, "BUSINESS_VALIDATION_FAILED");
        }
        var ids = scopeFilter().put("mode", "IDS");
        ids.putNull("filter");
        scopeRejectedWithoutInsert(
                token, headers, ids.toString(), 422, "BUSINESS_VALIDATION_FAILED");
        ids.withArray("account_ids").add("not-a-uuid");
        scopeRejectedWithoutInsert(
                token, headers, ids.toString(), 422, "BUSINESS_VALIDATION_FAILED");
        ids.withArray("account_ids").removeAll().add(UUID.randomUUID().toString());
        scopeRejectedWithoutInsert(token, headers, ids.toString(), 404, "NOT_FOUND");
        // FILTER与IDS不能混用；超限按原始数组长度判断，重复ID不能绕过50000限制。
        var mixed = scopeFilter();
        mixed.withArray("account_ids").add(UUID.randomUUID().toString());
        scopeRejectedWithoutInsert(
                token, headers, mixed.toString(), 422, "BUSINESS_VALIDATION_FAILED");
        ids.withArray("account_ids").removeAll();
        for (int i = 0; i < 50001; i++)
            ids.withArray("account_ids").add("00000000-0000-0000-0000-000000000001");
        scopeRejectedWithoutInsert(
                token, headers, ids.toString(), 422, "BUSINESS_VALIDATION_FAILED");
    }

    @Test
    void scopeHttpHeaderAndQueryBoundariesKeepErrorsAndRollback() throws Exception {
        String base = "/api/v1/scope-snapshots", token = scopeLogin();
        var headers = scopeHeaders(token);
        String csrf = headers.get("X-CSRF-Token");
        for (String key : List.of("a".repeat(15), "a".repeat(129)))
            scopeRejectedWithoutInsert(
                    token,
                    Map.of("Idempotency-Key", key, "X-CSRF-Token", csrf),
                    scopeFilter().toString(),
                    400,
                    "INVALID_REQUEST");
        scopeRejectedWithoutInsert(
                token,
                Map.of("X-CSRF-Token", csrf),
                scopeFilter().toString(),
                400,
                "INVALID_REQUEST");
        for (String value : List.of("x".repeat(15), "x".repeat(256)))
            scopeRejectedWithoutInsert(
                    token,
                    Map.of("Idempotency-Key", UUID.randomUUID().toString(), "X-CSRF-Token", value),
                    scopeFilter().toString(),
                    403,
                    "CSRF_INVALID");
        assertEquals(400, call("GET", base + "/csrf?q=x", token, null, Map.of()).statusCode());
        assertEquals(
                400,
                call("POST", base + "?tenant_id=x", token, scopeFilter().toString(), headers)
                        .statusCode());
        String missing = base + "/" + UUID.randomUUID() + "/members";
        assertEquals(
                400, call("GET", base + "/not-a-uuid/members", token, null, Map.of()).statusCode());
        assertEquals(404, call("GET", missing, token, null, Map.of()).statusCode());
        for (String size : List.of("0", "19", "201", "020", "-1", "1.5", "", "null"))
            assertEquals(
                    422,
                    call("GET", missing + "?page_size=" + size, token, null, Map.of())
                            .statusCode());
        for (String field :
                List.of(
                        "status",
                        "date_from",
                        "date_to",
                        "operator_user_id",
                        "channel_id",
                        "metric_profile_id",
                        "entity_type")) {
            var rejected = call("GET", missing + "?" + field + "=x", token, null, Map.of());
            assertEquals(422, rejected.statusCode());
            assertEquals(
                    "UNSUPPORTED_FILTER", json.readTree(rejected.body()).path("code").asText());
        }
        for (String query :
                List.of("q=x&q=y", "cursor=x&cursor=y", "page_size=20&page_size=50", "tenant_id=x"))
            assertEquals(
                    400, call("GET", missing + "?" + query, token, null, Map.of()).statusCode());
        for (String query :
                List.of("cursor=", "cursor=" + "x".repeat(2049), "q=" + "x".repeat(101), "q=a%01b"))
            assertEquals(
                    422, call("GET", missing + "?" + query, token, null, Map.of()).statusCode());
    }

    @Test
    void scopeHttpRealSessionCsrfCreateReplayPagingRevocationAndErrors() throws Exception {
        String base = "/api/v1/scope-snapshots", tenant = "00000000-0000-0000-0000-000000000001";
        var unauth = call("GET", base + "/csrf", null, null, Map.of());
        assertEquals(401, unauth.statusCode());
        assertEquals("SESSION_REQUIRED", json.readTree(unauth.body()).path("code").asText());
        assertEquals(
                unauth.headers().firstValue("X-Request-ID").orElseThrow(),
                json.readTree(unauth.body()).path("request_id").asText());
        assertTrue(unauth.headers().firstValue("Cache-Control").orElseThrow().contains("no-store"));
        var entries = ensureScopeDirectory();
        String token = scopeLogin();
        var csrfReply = call("GET", base + "/csrf", token, null, Map.of());
        assertEquals(200, csrfReply.statusCode());
        String csrf = json.readTree(csrfReply.body()).path("csrf_token").asText();
        assertTrue(csrf.length() >= 16 && csrf.length() <= 255);
        String body =
                "{\"mode\":\"FILTER\",\"account_ids\":[],\"filter\":{\"q\":\"\",\"status\":null,\"auth_status\":null,\"operator_user_id\":null,\"vendor_id\":null}}";
        String key = "http printable key " + UUID.randomUUID();
        var headers = Map.of("Idempotency-Key", key, "X-CSRF-Token", csrf);
        assertEquals(
                400, call("POST", base, token, body, Map.of("Idempotency-Key", key)).statusCode());
        assertEquals(
                403,
                call(
                                "POST",
                                base,
                                token,
                                body,
                                Map.of(
                                        "Idempotency-Key",
                                        key,
                                        "X-CSRF-Token",
                                        "invalid-csrf-token"))
                        .statusCode());
        headers = new HashMap<>(headers);
        headers.put("X-Request-ID", "client-controlled-not-trusted");
        var created = call("POST", base, token, body, headers);
        assertEquals(201, created.statusCode());
        String createdRequest = created.headers().firstValue("X-Request-ID").orElseThrow();
        assertEquals(createdRequest, UUID.fromString(createdRequest).toString());
        String snapshotId = json.readTree(created.body()).path("id").asText();
        assertEquals(
                createdRequest,
                jdbc.queryForObject(
                        "SELECT request_id FROM orbit_account_scope_audit WHERE snapshot_id=?",
                        String.class,
                        snapshotId));
        var replayRequest = call("POST", base, token, body, headers);
        assertEquals(201, replayRequest.statusCode());
        assertEquals(created.body(), replayRequest.body());
        assertNotEquals(
                createdRequest, replayRequest.headers().firstValue("X-Request-ID").orElseThrow());
        assertEquals(
                createdRequest,
                jdbc.queryForObject(
                        "SELECT request_id FROM orbit_account_scope_audit WHERE snapshot_id=?",
                        String.class,
                        snapshotId));
        var frozen = json.readTree(created.body());
        assertEquals(45, frozen.path("count").intValue());
        assertEquals(64, frozen.path("hash").asText().length());
        Set<String> fields = new HashSet<>();
        frozen.fieldNames().forEachRemaining(fields::add);
        assertEquals(Set.of("id", "count", "scope_version", "hash", "created_at"), fields);
        assertEquals(frozen, json.readTree(call("POST", base, token, body, headers).body()));
        var conflict =
                call("POST", base, token, body.replace("\"q\":\"\"", "\"q\":\"changed\""), headers);
        assertEquals(409, conflict.statusCode());
        assertEquals("IDEMPOTENCY_CONFLICT", json.readTree(conflict.body()).path("code").asText());
        String memberPath = base + "/" + frozen.path("id").asText() + "/members";
        var first = call("GET", memberPath + "?page_size=20", token, null, Map.of());
        assertEquals(200, first.statusCode());
        var firstPage = json.readTree(first.body());
        assertEquals(20, firstPage.path("items").size());
        assertEquals(frozen.path("scope_version"), firstPage.path("scope_version"));
        String cursor =
                java.net.URLEncoder.encode(
                        firstPage.path("next_cursor").asText(),
                        java.nio.charset.StandardCharsets.UTF_8);
        var next =
                json.readTree(
                        call(
                                        "GET",
                                        memberPath + "?page_size=20&cursor=" + cursor,
                                        token,
                                        null,
                                        Map.of())
                                .body());
        assertEquals(20, next.path("items").size());
        Set<String> ids = new HashSet<>();
        firstPage.path("items").forEach(row -> ids.add(row.path("account_id").asText()));
        next.path("items").forEach(row -> assertTrue(ids.add(row.path("account_id").asText())));
        assertEquals(
                422,
                call("GET", memberPath + "?status=ACTIVE", token, null, Map.of()).statusCode());
        assertEquals(400, call("GET", memberPath + "?q=a&q=b", token, null, Map.of()).statusCode());
        assertEquals(
                400, call("GET", memberPath + "?unknown=true", token, null, Map.of()).statusCode());
        assertEquals(
                422,
                call("GET", memberPath + "?page_size=20&cursor=invalid", token, null, Map.of())
                        .statusCode());
        String secondToken = scopeLogin();
        assertEquals(403, call("POST", base, secondToken, body, headers).statusCode());
        var unknown =
                call(
                        "POST",
                        base,
                        token,
                        body.replace("\"mode\"", "\"unknown\""),
                        Map.of(
                                "Idempotency-Key",
                                UUID.randomUUID().toString(),
                                "X-CSRF-Token",
                                csrf));
        assertEquals(400, unknown.statusCode());
        var error = json.readTree(unknown.body());
        Set<String> errorFields = new HashSet<>();
        error.fieldNames().forEachRemaining(errorFields::add);
        assertEquals(
                Set.of("code", "message", "field_errors", "retryable", "request_id"), errorFields);
        assertEquals(
                unknown.headers().firstValue("X-Request-ID").orElseThrow(),
                error.path("request_id").asText());
        // 逐字段正向筛选及成员响应；空结果必须是合法冻结，未知外部ID不得转为数值。
        var filters =
                List.of(
                        Map.entry("q", "scope fixture 1"),
                        Map.entry("status", "DISABLED"),
                        Map.entry("auth_status", "EXPIRED"),
                        Map.entry("operator_user_id", tenant),
                        Map.entry("vendor_id", UUID.randomUUID().toString()));
        int[] expectedCounts = {11, 0, 0, 45, 0};
        for (int i = 0; i < filters.size(); i++) {
            var selected = scopeFilter();
            var filter = (com.fasterxml.jackson.databind.node.ObjectNode) selected.path("filter");
            filter.put(filters.get(i).getKey(), filters.get(i).getValue());
            var response = call("POST", base, token, selected.toString(), scopeHeaders(token));
            assertEquals(201, response.statusCode());
            assertEquals(
                    expectedCounts[i], json.readTree(response.body()).path("count").intValue());
        }
        var selected = scopeFilter().put("mode", "IDS");
        selected.putNull("filter");
        String chosen = entries.getFirst().id();
        selected.withArray("account_ids").add(chosen).add(chosen.toUpperCase(Locale.ROOT));
        var selectedHeaders = scopeHeaders(token);
        var selectedResponse = call("POST", base, token, selected.toString(), selectedHeaders);
        assertEquals(201, selectedResponse.statusCode());
        var selectedSnapshot = json.readTree(selectedResponse.body());
        assertEquals(1, selectedSnapshot.path("count").intValue());
        selected.withArray("account_ids").removeAll().add(chosen);
        assertEquals(
                selectedSnapshot,
                json.readTree(
                        call("POST", base, token, selected.toString(), selectedHeaders).body()));
        String selectedPath = base + "/" + selectedSnapshot.path("id").asText() + "/members";
        for (int size : List.of(20, 50, 100, 200)) {
            var response = call("GET", selectedPath + "?page_size=" + size, token, null, Map.of());
            assertEquals(200, response.statusCode());
            var page = json.readTree(response.body());
            assertEquals(1, page.path("items").size());
            assertTrue(page.path("next_cursor").isNull());
            var member = page.path("items").get(0);
            Set<String> memberFields = new HashSet<>();
            member.fieldNames().forEachRemaining(memberFields::add);
            assertEquals(Set.of("account_id", "external_id", "name"), memberFields);
            assertEquals(chosen, member.path("account_id").asText());
            assertTrue(member.path("external_id").isTextual());
            assertEquals(entries.getFirst().externalId(), member.path("external_id").asText());
            assertEquals(entries.getFirst().name(), member.path("name").asText());
        }
        assertEquals(
                422,
                call("GET", memberPath + "?page_size=50&cursor=" + cursor, token, null, Map.of())
                        .statusCode());
        assertEquals(
                422,
                call(
                                "GET",
                                memberPath + "?page_size=20&q=changed&cursor=" + cursor,
                                token,
                                null,
                                Map.of())
                        .statusCode());
        assertEquals(
                422,
                call("GET", selectedPath + "?page_size=20&cursor=" + cursor, token, null, Map.of())
                        .statusCode());
        jdbc.update("UPDATE sys_menu SET status='1' WHERE menu_id=31011");
        try {
            assertEquals(403, call("GET", memberPath, token, null, Map.of()).statusCode());
        } finally {
            jdbc.update("UPDATE sys_menu SET status='0' WHERE menu_id=31011");
        }
        jdbc.update("UPDATE sys_menu SET status='1' WHERE menu_id=31010");
        try {
            assertEquals(403, call("GET", memberPath, token, null, Map.of()).statusCode());
        } finally {
            jdbc.update("UPDATE sys_menu SET status='0' WHERE menu_id=31010");
        }
        assertEquals(409, call("GET", memberPath, token, null, Map.of()).statusCode());
    }

    private String crossTenantDirectory() {
        String target = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'cross HTTP fixture')", target);
        for (int i = 0; i < 45; i++)
            jdbc.update(
                    "INSERT INTO orbit_account_scope_directory(tenant_id,id,external_id,name,currency,account_status,auth_status) VALUES(?,?,?,?,'USD','ACTIVE','AUTHORIZED')",
                    target,
                    UUID.randomUUID().toString(),
                    String.format(Locale.ROOT, "%032d", i + 1),
                    "cross fixture " + i);
        return target;
    }

    @Test
    void scopeHttpCrossTenantRoundTripKeepsAuditAndRejectsBothVersionRevocations()
            throws Exception {
        String base = "/api/v1/scope-snapshots", home = "00000000-0000-0000-0000-000000000001";
        ensureScopeDirectory();
        String target = crossTenantDirectory(), token = scopeLogin();
        var headers = new HashMap<>(scopeHeaders(token));
        headers.put("X-Target-Tenant", target.toUpperCase(Locale.ROOT));
        String body = scopeFilter().toString();
        headers = new HashMap<>(headers);
        headers.put("X-Request-ID", "client-controlled-not-trusted");
        var created = call("POST", base, token, body, headers);
        assertEquals(201, created.statusCode());
        String createdRequest = created.headers().firstValue("X-Request-ID").orElseThrow();
        assertEquals(createdRequest, UUID.fromString(createdRequest).toString());
        String snapshotId = json.readTree(created.body()).path("id").asText();
        assertEquals(
                createdRequest,
                jdbc.queryForObject(
                        "SELECT request_id FROM orbit_account_scope_audit WHERE snapshot_id=?",
                        String.class,
                        snapshotId));
        var replayRequest = call("POST", base, token, body, headers);
        assertEquals(201, replayRequest.statusCode());
        assertEquals(created.body(), replayRequest.body());
        assertNotEquals(
                createdRequest, replayRequest.headers().firstValue("X-Request-ID").orElseThrow());
        assertEquals(
                createdRequest,
                jdbc.queryForObject(
                        "SELECT request_id FROM orbit_account_scope_audit WHERE snapshot_id=?",
                        String.class,
                        snapshotId));
        var view = json.readTree(created.body());
        String id = view.path("id").asText();
        assertEquals(45, view.path("count").asInt());
        Set<String> fields = new HashSet<>();
        view.fieldNames().forEachRemaining(fields::add);
        assertEquals(Set.of("id", "count", "scope_version", "hash", "created_at"), fields);
        assertEquals(
                target,
                jdbc.queryForObject(
                        "SELECT tenant_id FROM orbit_account_scope_snapshot WHERE id=?",
                        String.class,
                        id));
        assertEquals(
                0,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orbit_business_user WHERE tenant_id=? AND user_id=1",
                        Integer.class,
                        target));
        assertEquals(created.body(), call("POST", base, token, body, headers).body());
        assertEquals(
                1,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orbit_account_scope_audit WHERE snapshot_id=? AND actor_id=1 AND home_tenant_id=? AND target_tenant_id=?",
                        Integer.class,
                        id,
                        home,
                        target));
        String member = base + "/" + id + "/members", cursor = null;
        List<String> ids = new ArrayList<>();
        String firstCursor = null;
        for (int expected : List.of(20, 20, 5)) {
            var response =
                    call(
                            "GET",
                            member + "?page_size=20" + (cursor == null ? "" : "&cursor=" + cursor),
                            token,
                            null,
                            Map.of());
            assertEquals(200, response.statusCode());
            assertTrue(
                    response.headers()
                            .firstValue("Cache-Control")
                            .orElseThrow()
                            .contains("no-store"));
            var page = json.readTree(response.body());
            assertEquals(expected, page.path("items").size());
            page.path("items")
                    .forEach(
                            item -> {
                                ids.add(item.path("account_id").asText());
                                assertTrue(item.path("external_id").isTextual());
                                assertEquals(32, item.path("external_id").asText().length());
                            });
            cursor = page.path("next_cursor").isNull() ? null : page.path("next_cursor").asText();
            if (firstCursor == null) firstCursor = cursor;
        }
        assertNull(cursor);
        assertEquals(45, new HashSet<>(ids).size());
        assertEquals(
                jdbc.queryForList(
                        "SELECT id FROM orbit_account_scope_directory WHERE tenant_id=? ORDER BY id",
                        String.class,
                        target),
                ids);
        var changed = scopeFilter();
        ((com.fasterxml.jackson.databind.node.ObjectNode) changed.get("filter"))
                .put("q", "changed");
        scopeRejectedWithoutInsert(token, headers, changed.toString(), 409, "IDEMPOTENCY_CONFLICT");
        String secondSession = scopeLogin();
        scopeRejectedWithoutInsert(secondSession, headers, body, 403, "CSRF_INVALID");
        var homeHeaders = new HashMap<>(headers);
        homeHeaders.remove("X-Target-Tenant");
        var homeCreated = call("POST", base, token, body, homeHeaders);
        assertEquals(201, homeCreated.statusCode());
        assertNotEquals(id, json.readTree(homeCreated.body()).path("id").asText());
        jdbc.update("UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=?", home);
        assertEquals(
                409,
                call("GET", member + "?page_size=20&cursor=" + firstCursor, token, null, Map.of())
                        .statusCode());
        scopeRejectedWithoutInsert(token, headers, body, 409, "SCOPE_CHANGED");
        var freshHeaders = new HashMap<>(scopeHeaders(token));
        freshHeaders.put("X-Target-Tenant", target);
        var fresh = call("POST", base, token, body, freshHeaders);
        assertEquals(201, fresh.statusCode());
        String freshId = json.readTree(fresh.body()).path("id").asText();
        jdbc.update("UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=?", target);
        assertEquals(
                409,
                call("GET", base + "/" + freshId + "/members", token, null, Map.of()).statusCode());
        jdbc.update("UPDATE orbit_tenant SET enabled=0 WHERE id=?", target);
        assertEquals(404, call("GET", member, token, null, Map.of()).statusCode());
        scopeRejectedWithoutInsert(token, freshHeaders, body, 404, "NOT_FOUND");
    }

    @Test
    void scopeHttpCrossTenantOtherActorHeadersAmbiguityAndAuditFailureAreSafe() throws Exception {
        String base = "/api/v1/scope-snapshots", home = "00000000-0000-0000-0000-000000000001";
        String target = crossTenantDirectory(), token = scopeLogin();
        var headers = new HashMap<>(scopeHeaders(token));
        headers.put("X-Target-Tenant", target);
        var first = call("POST", base, token, scopeFilter().toString(), headers);
        assertEquals(201, first.statusCode());
        String id = json.readTree(first.body()).path("id").asText();
        String cursor =
                json.readTree(
                                call(
                                                "GET",
                                                base + "/" + id + "/members?page_size=20",
                                                token,
                                                null,
                                                Map.of())
                                        .body())
                        .path("next_cursor")
                        .asText();
        jdbc.update(
                "INSERT INTO sys_user(user_id,dept_id,user_name,nick_name,password,status,del_flag) VALUES(902001,103,'cross_actor_fixture','跨租户身份fixture',?,'0','0')",
                new BCryptPasswordEncoder().encode(PASSWORD));
        jdbc.update(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(902001,?,'SUPER_ADMIN')",
                home);
        jdbc.update(
                "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,enabled) VALUES(?,?,902001,?,1)",
                home,
                UUID.randomUUID().toString(),
                home);
        jdbc.update(
                "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,status,del_flag) VALUES(902010,'跨租户范围fixture','cross-scope-http',99,'0','0')");
        jdbc.update("INSERT INTO sys_user_role(user_id,role_id) VALUES(902001,902010)");
        jdbc.update(
                "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(902010,31000),(902010,31010),(902010,31011)");
        String other = scopeLogin("cross_actor_fixture");
        assertEquals(
                404, call("GET", base + "/" + id + "/members", other, null, Map.of()).statusCode());
        var ownHeaders = new HashMap<>(scopeHeaders(other));
        ownHeaders.put("X-Target-Tenant", target);
        var own = call("POST", base, other, scopeFilter().toString(), ownHeaders);
        assertEquals(201, own.statusCode());
        String ownId = json.readTree(own.body()).path("id").asText();
        assertEquals(
                422,
                call(
                                "GET",
                                base + "/" + ownId + "/members?page_size=20&cursor=" + cursor,
                                other,
                                null,
                                Map.of())
                        .statusCode());
        for (String invalid : List.of("not-a-uuid", UUID.randomUUID().toString())) {
            var bad = new HashMap<>(ownHeaders);
            bad.put("X-Target-Tenant", invalid);
            scopeRejectedWithoutInsert(
                    other,
                    bad,
                    scopeFilter().toString(),
                    invalid.equals("not-a-uuid") ? 400 : 404,
                    invalid.equals("not-a-uuid") ? "INVALID_REQUEST" : "NOT_FOUND");
        }
        scopeRejectedWithoutInsert(
                other,
                ownHeaders,
                scopeFilter().put("actor_id", 1).toString(),
                400,
                "UNKNOWN_FIELD");
        jdbc.update("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=902001");
        assertEquals(
                404,
                call("GET", base + "/" + ownId + "/members", other, null, Map.of()).statusCode());
        scopeRejectedWithoutInsert(
                other, ownHeaders, scopeFilter().toString(), 403, "PERMISSION_DENIED");
        var same = new HashMap<>(ownHeaders);
        same.put("X-Target-Tenant", home);
        scopeRejectedWithoutInsert(other, same, scopeFilter().toString(), 403, "PERMISSION_DENIED");
        String duplicate = UUID.randomUUID().toString();
        jdbc.update(
                "INSERT INTO orbit_tenant(id,name) VALUES(?,'ambiguous HTTP fixture')", duplicate);
        jdbc.update(
                "INSERT INTO orbit_account_scope_snapshot(tenant_id,id,actor_id,request_key,request_json,request_hash,access_hash,directory_revision,members_hash,member_count,ready,created_at) SELECT ?,id,actor_id,request_key,request_json,request_hash,access_hash,directory_revision,members_hash,member_count,ready,created_at FROM orbit_account_scope_snapshot WHERE tenant_id=? AND id=?",
                duplicate,
                target,
                id);
        var ambiguous = call("GET", base + "/" + id + "/members", token, null, Map.of());
        assertEquals(409, ambiguous.statusCode());
        assertEquals("范围标识不唯一，请重新生成", json.readTree(ambiguous.body()).path("message").asText());
        jdbc.execute(
                "CREATE TRIGGER cross_http_audit_fail BEFORE INSERT ON orbit_account_scope_audit FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='controlled HTTP audit failure'");
        try {
            var freshHeaders = new HashMap<>(scopeHeaders(token));
            freshHeaders.put("X-Target-Tenant", target);
            long before =
                    jdbc.queryForObject(
                            "SELECT COUNT(*) FROM orbit_account_scope_snapshot", Long.class);
            var failed = call("POST", base, token, scopeFilter().toString(), freshHeaders);
            assertEquals(503, failed.statusCode());
            assertFalse(failed.body().contains("controlled HTTP audit failure"));
            assertFalse(failed.body().contains("INSERT INTO"));
            assertEquals(
                    before,
                    jdbc.queryForObject(
                            "SELECT COUNT(*) FROM orbit_account_scope_snapshot", Long.class));
        } finally {
            jdbc.execute("DROP TRIGGER cross_http_audit_fail");
        }
        jdbc.update("UPDATE sys_menu SET status='1' WHERE menu_id=31011");
        try {
            assertEquals(
                    403,
                    call("GET", base + "/" + ownId + "/members", token, null, Map.of())
                            .statusCode());
        } finally {
            jdbc.update("UPDATE sys_menu SET status='0' WHERE menu_id=31011");
        }
    }

    @Test
    void auditHttpRealGlobalQueryProjectsContractAndPagesWithoutLeaks() throws Exception {
        ensureScopeDirectory();
        String token = scopeLogin(), target = crossTenantDirectory();
        Set<String> expected = new HashSet<>();
        for (int i = 0; i < 25; i++) {
            var headers = new HashMap<>(scopeHeaders(token));
            if (i % 2 == 1) headers.put("X-Target-Tenant", target);
            var created =
                    call(
                            "POST",
                            "/api/v1/scope-snapshots",
                            token,
                            scopeFilter().toString(),
                            headers);
            assertEquals(201, created.statusCode());
            expected.add(json.readTree(created.body()).path("id").asText());
        }
        var unauth = call("GET", "/api/v1/audit-events", null, null, Map.of());
        assertEquals(401, unauth.statusCode());
        assertEquals(
                unauth.headers().firstValue("X-Request-ID").orElseThrow(),
                json.readTree(unauth.body()).path("request_id").asText());
        Set<String> eventIds = new HashSet<>(),
                objects = new HashSet<>(),
                tenants = new HashSet<>();
        String cursor = null, cutoff = null;
        for (int page = 0; page < 30; page++) {
            String path =
                    "/api/v1/audit-events?page_size=20"
                            + (cursor == null
                                    ? ""
                                    : "&cursor="
                                            + java.net.URLEncoder.encode(
                                                    cursor,
                                                    java.nio.charset.StandardCharsets.UTF_8));
            var reply = call("GET", path, token, null, Map.of());
            assertEquals(200, reply.statusCode());
            assertTrue(
                    reply.headers().firstValue("Cache-Control").orElseThrow().contains("no-store"));
            java.util.UUID.fromString(reply.headers().firstValue("X-Request-ID").orElseThrow());
            var data = json.readTree(reply.body());
            if (cutoff == null) cutoff = data.path("data_as_of").asText();
            else assertEquals(cutoff, data.path("data_as_of").asText());
            Set<String> pageFields = new HashSet<>();
            data.fieldNames().forEachRemaining(pageFields::add);
            assertEquals(Set.of("items", "next_cursor", "data_as_of", "scope_version"), pageFields);
            for (var item : data.path("items")) {
                Set<String> fields = new HashSet<>();
                item.fieldNames().forEachRemaining(fields::add);
                assertEquals(
                        Set.of(
                                "id",
                                "actor_user_id",
                                "action_code",
                                "target_id",
                                "tenant_id",
                                "reason",
                                "evidence_ref",
                                "occurred_at",
                                "request_id"),
                        fields);
                assertTrue(eventIds.add(item.path("id").asText()));
                objects.add(item.path("target_id").asText());
                tenants.add(item.path("tenant_id").asText());
                for (String field :
                        List.of("id", "actor_user_id", "target_id", "tenant_id", "request_id"))
                    java.util.UUID.fromString(item.path(field).asText());
                assertTrue(item.path("evidence_ref").isNull());
                assertFalse(reply.body().contains("request_hash"));
            }
            if (data.path("next_cursor").isNull()) {
                cursor = null;
                break;
            }
            cursor = data.path("next_cursor").asText();
        }
        assertNull(cursor);
        assertTrue(objects.containsAll(expected));
        assertTrue(tenants.contains(target));
        var empty =
                call("GET", "/api/v1/audit-events?q=no-matching-audit-code", token, null, Map.of());
        assertEquals(200, empty.statusCode());
        assertEquals(0, json.readTree(empty.body()).path("items").size());
        for (var pair :
                List.of(
                        Map.entry("tenant_id=x", 400),
                        Map.entry("q=a&q=b", 400),
                        Map.entry("status=ACTIVE", 422),
                        Map.entry("operator_user_id=invalid", 422),
                        Map.entry("page_size=21", 422)))
            assertEquals(
                    pair.getValue(),
                    call("GET", "/api/v1/audit-events?" + pair.getKey(), token, null, Map.of())
                            .statusCode());
        assertEquals(
                403,
                call("GET", "/api/v1/audit-events", token, null, Map.of("X-Target-Tenant", target))
                        .statusCode());
    }

    @Test
    void auditHttpNonAdminOwnHistoryAndCurrentMenuRevocation() throws Exception {
        ensureScopeDirectory();
        String home = "00000000-0000-0000-0000-000000000001",
                subject = UUID.randomUUID().toString();
        jdbc.update(
                "INSERT INTO sys_user(user_id,dept_id,user_name,nick_name,password,status,del_flag) VALUES(901100,103,'audit_user_fixture','审计fixture',?,'0','0')",
                new BCryptPasswordEncoder().encode(PASSWORD));
        try {
            jdbc.update(
                    "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role,enabled) VALUES(901100,?,'USER',1)",
                    home);
            jdbc.update(
                    "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id) VALUES(?,?,901100,?)",
                    home,
                    subject,
                    home);
            jdbc.update(
                    "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,status,del_flag) VALUES(901110,'审计fixture','audit-http-fixture',1,'0','0')");
            jdbc.update("INSERT INTO sys_user_role(user_id,role_id) VALUES(901100,901110)");
            for (long menu : List.of(31000L, 31080L, 31082L, 31083L, 31010L, 31011L))
                jdbc.update("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(901110,?)", menu);
            String token = scopeLogin("audit_user_fixture");
            var created =
                    call(
                            "POST",
                            "/api/v1/scope-snapshots",
                            token,
                            scopeFilter().toString(),
                            scopeHeaders(token));
            assertEquals(201, created.statusCode());
            var result = call("GET", "/api/v1/audit-events", token, null, Map.of());
            assertEquals(200, result.statusCode());
            var items = json.readTree(result.body()).path("items");
            assertEquals(1, items.size());
            assertEquals(subject, items.get(0).path("actor_user_id").asText());
            assertEquals(
                    json.readTree(created.body()).path("id").asText(),
                    items.get(0).path("target_id").asText());
            jdbc.update("DELETE FROM sys_role_menu WHERE role_id=901110 AND menu_id=31083");
            assertEquals(
                    403, call("GET", "/api/v1/audit-events", token, null, Map.of()).statusCode());
            jdbc.update("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(901110,31083)");
            jdbc.update("DELETE FROM sys_role_menu WHERE role_id=901110 AND menu_id=31082");
            assertEquals(
                    403, call("GET", "/api/v1/audit-events", token, null, Map.of()).statusCode());
        } finally {
            jdbc.update("DELETE FROM sys_role_menu WHERE role_id=901110");
            jdbc.update("DELETE FROM sys_user_role WHERE user_id=901100");
            jdbc.update("DELETE FROM sys_role WHERE role_id=901110");
            jdbc.update("DELETE FROM orbit_business_user WHERE user_id=901100");
            jdbc.update("DELETE FROM orbit_user_scope WHERE user_id=901100");
            jdbc.update("DELETE FROM sys_user WHERE user_id=901100");
        }
    }

    @Test
    void auditHttpUnknownHistoricalIdentityReturnsSafeExplicitError() throws Exception {
        String token = scopeLogin(),
                home = "00000000-0000-0000-0000-000000000001",
                id = UUID.randomUUID().toString(),
                subject = UUID.randomUUID().toString();
        jdbc.update(
                "INSERT INTO orbit_account_scope_audit(id,target_tenant_id,snapshot_id,actor_id,home_tenant_id,data_role,action,request_hash,members_hash,member_count,home_version,target_version,actor_subject_id,created_at) VALUES(?,?,?,1,?,'USER','SCOPE_FROZEN',?,?,0,1,1,?,'2026-11-06 12:00:00')",
                id,
                home,
                UUID.randomUUID().toString(),
                home,
                "0".repeat(64),
                "1".repeat(64),
                subject);
        try {
            var reply =
                    call(
                            "GET",
                            "/api/v1/audit-events?operator_user_id=" + subject,
                            token,
                            null,
                            Map.of());
            assertEquals(503, reply.statusCode());
            var error = json.readTree(reply.body());
            assertEquals("AUDIT_HISTORY_INCOMPLETE", error.path("code").asText());
            assertEquals(
                    reply.headers().firstValue("X-Request-ID").orElseThrow(),
                    error.path("request_id").asText());
            assertFalse(reply.body().contains(id));
            assertFalse(reply.body().contains("SQLException"));
            assertEquals(
                    1,
                    jdbc.queryForObject(
                            "SELECT COUNT(*) FROM orbit_account_scope_audit WHERE id=?",
                            Integer.class,
                            id));
        } finally {
            jdbc.update("DELETE FROM orbit_account_scope_audit WHERE id=?", id);
        }
    }

    /** 相同固定目录fixture只发布一次，HTTP与浏览器用例不依赖JUnit执行顺序。 */
    private List<com.ruoyi.system.orbit.scope.AccountDirectoryPublisher.Entry>
            ensureScopeDirectory() {
        String tenant = "00000000-0000-0000-0000-000000000001";
        List<com.ruoyi.system.orbit.scope.AccountDirectoryPublisher.Entry> entries =
                new ArrayList<>();
        for (int i = 0; i < 45; i++)
            entries.add(
                    new com.ruoyi.system.orbit.scope.AccountDirectoryPublisher.Entry(
                            UUID.nameUUIDFromBytes(
                                            ("scope-fixture-" + i)
                                                    .getBytes(
                                                            java.nio.charset.StandardCharsets
                                                                    .UTF_8))
                                    .toString(),
                            "1234567890123456789012345" + i,
                            "scope fixture " + i,
                            tenant,
                            tenant,
                            null,
                            "USD",
                            "ACTIVE",
                            "AUTHORIZED"));
        Long revision =
                jdbc.queryForObject(
                        "SELECT MAX(revision) FROM orbit_account_scope_clock WHERE tenant_id=?",
                        Long.class,
                        tenant);
        if (revision == null || revision == 1)
            directory.publishTrusted(tenant, 1, 1, entries, List.of());
        return entries;
    }

    /** 真正的非管理员登录：合并功能角色不等于扩大业务数据角色。 */
    @Test
    void scopeHttpNonAdminRoleUnionKeepsDataScopeAndImmediateRevocation() throws Exception {
        ensureScopeDirectory();
        String tenant = "00000000-0000-0000-0000-000000000001", base = "/api/v1/scope-snapshots";
        jdbc.update(
                "INSERT INTO sys_user(user_id,dept_id,user_name,nick_name,password,status,del_flag) VALUES(901001,103,'scope_union_fixture','范围权限fixture',?,'0','0')",
                new BCryptPasswordEncoder().encode(PASSWORD));
        try {
            jdbc.update(
                    "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role,enabled) VALUES(901001,?,'USER',1)",
                    tenant);
            jdbc.update(
                    "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id) VALUES(?,?,901001,?)",
                    tenant,
                    UUID.randomUUID().toString(),
                    tenant);
            jdbc.update(
                    "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,status,del_flag) VALUES(901010,'父菜单fixture','scope-http-parent',1,'0','0'),(901011,'页面fixture','scope-http-page',2,'0','0'),(901012,'动作fixture','scope-http-action',3,'0','0')");
            jdbc.update(
                    "INSERT INTO sys_user_role(user_id,role_id) VALUES(901001,901010),(901001,901011),(901001,901012)");
            jdbc.update(
                    "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(901010,31000),(901011,31011),(901012,31010)");
            String token = scopeLogin("scope_union_fixture");
            var headers = scopeHeaders(token);
            var frozen = call("POST", base, token, scopeFilter().toString(), headers);
            assertEquals(201, frozen.statusCode());
            assertEquals(
                    0,
                    json.readTree(frozen.body()).path("count").intValue(),
                    "USER不能因多个功能角色看到root的45个账户");
            jdbc.update("UPDATE sys_role SET status='1' WHERE role_id=901012");
            assertEquals(403, call("GET", base + "/csrf", token, null, Map.of()).statusCode());
            jdbc.update("UPDATE sys_role SET status='0' WHERE role_id=901012");
            assertEquals(200, call("GET", base + "/csrf", token, null, Map.of()).statusCode());
            jdbc.update("DELETE FROM sys_role_menu WHERE role_id=901011 AND menu_id=31011");
            assertEquals(403, call("GET", base + "/csrf", token, null, Map.of()).statusCode());
        } finally {
            // 仅清理本用例在随机fixture库内新建的身份/角色；范围元数据随整库清理。
            jdbc.update("DELETE FROM sys_role_menu WHERE role_id IN(901010,901011,901012)");
            jdbc.update("DELETE FROM sys_user_role WHERE user_id=901001");
            jdbc.update("DELETE FROM sys_role WHERE role_id IN(901010,901011,901012)");
            jdbc.update("DELETE FROM orbit_business_user WHERE user_id=901001");
            jdbc.update("DELETE FROM orbit_user_scope WHERE user_id=901001");
            jdbc.update("DELETE FROM sys_user WHERE user_id=901001");
        }
    }

    private static String randomKey(int size) {
        byte[] value = new byte[size];
        new SecureRandom().nextBytes(value);
        try {
            return Base64.getEncoder().encodeToString(value);
        } finally {
            Arrays.fill(value, (byte) 0);
        }
    }

    @DynamicPropertySource
    static void fixtureDatabaseAndKeys(DynamicPropertyRegistry registry) throws Exception {
        root = Path.of("").toAbsolutePath();
        while (!Files.exists(root.resolve("sql/orbit/V001__system_configuration.sql"))) {
            root = root.getParent();
            if (root == null) throw new IllegalStateException("未找到ORBIT仓库");
        }
        String options =
                "?useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=utf8&connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true";
        admin =
                new JdbcTemplate(
                        new DriverManagerDataSource(
                                "jdbc:mysql://127.0.0.1:13306/" + options, "root", ""));
        assertEquals(
                root.getParent()
                                .resolve(".runtime/mysql-it/data")
                                .toString()
                                .replace('\\', '/')
                                .toLowerCase(Locale.ROOT)
                        + "/",
                admin.queryForObject("SELECT @@datadir", String.class)
                        .replace('\\', '/')
                        .toLowerCase(Locale.ROOT));
        RedisClient redis = RedisClient.create("redis://127.0.0.1:16379/14");
        try (var connection = redis.connect()) {
            String dir =
                    connection
                            .sync()
                            .configGet("dir")
                            .get("dir")
                            .replace('\\', '/')
                            .toLowerCase(Locale.ROOT);
            String workspace =
                    root.getParent().toString().replace('\\', '/').toLowerCase(Locale.ROOT);
            assertEquals(
                    "/cygdrive/"
                            + workspace.charAt(0)
                            + workspace.substring(2)
                            + "/.runtime/redis-it",
                    dir);
            assertEquals(0, connection.sync().dbsize(), "DB14不是空的独立fixture上下文，拒绝复用");
        } finally {
            redis.shutdown();
        }
        database = "orbit_browser_" + UUID.randomUUID().toString().replace("-", "");
        admin.execute(
                "CREATE DATABASE "
                        + database
                        + " CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs");
        String url = "jdbc:mysql://127.0.0.1:13306/" + database + options;
        var source = new DriverManagerDataSource(url, "root", "");
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(root.resolve("sql/ry_20260417.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
            for (String name :
                    List.of(
                            "V001__system_configuration.sql",
                            "V002__configuration_history_cursor.sql",
                            "V003__configuration_audit_fingerprints.sql",
                            "V004__analysis_job_queue.sql",
                            "V005__rule_draft_versions.sql",
                            "V006__business_identity_mapping.sql",
                            "V007__metric_profile_versions.sql",
                            "V008__account_scope_snapshots.sql",
                            "V009__scope_permission_versions.sql",
                            "V010__scope_directory_identity_versions.sql",
                            "V011__scope_public_request_keys.sql",
                            "V012__scope_page_menu.sql",
                            "V013__scope_tenant_proof.sql",
                            "V014__scope_freeze_audit.sql",
                            "V015__scope_actor_locator.sql",
                            "V016__scope_audit_identity.sql",
                            "V017__scope_audit_request.sql",
                            "V018__scope_audit_query_indexes.sql",
                            "V019__audit_page_menu.sql"))
                ScriptUtils.executeSqlScript(
                        connection,
                        new EncodedResource(
                                new FileSystemResource(root.resolve("sql/orbit/" + name)),
                                java.nio.charset.StandardCharsets.UTF_8));
        }
        JdbcTemplate fixture = new JdbcTemplate(source);
        fixture.update(
                "UPDATE sys_config SET config_value='false' WHERE config_key='sys.account.captchaEnabled'");
        fixture.update(
                "UPDATE sys_user SET password=? WHERE user_id=1",
                new BCryptPasswordEncoder().encode(PASSWORD));
        registry.add("spring.datasource.druid.master.url", () -> url);
        registry.add("spring.datasource.druid.master.username", () -> "root");
        registry.add("spring.datasource.druid.master.password", () -> "");
        registry.add("token.secret", () -> SIGNING);
        registry.add("orbit.secrets.active-key-id", () -> "browser-fixture");
        registry.add("orbit.secrets.keys.browser-fixture", () -> ENCRYPTION);
        registry.add(
                "ruoyi.profile",
                () -> root.getParent().resolve(".runtime/application-it/uploads").toString());
    }

    @Test
    void browserTraversesRealLoginMenusConfigurationAndHistory() throws Exception {
        ensureScopeDirectory();
        org.mockito.Mockito.when(
                        externalPlatform.check(
                                org.mockito.ArgumentMatchers.anyString(),
                                org.mockito.ArgumentMatchers.anyMap(),
                                org.mockito.ArgumentMatchers.anyMap()))
                .thenReturn(new ConnectionProbe.Result("BLOCKED", "外部平台传输fixture，真实平台待实测"));
        Path runtime = root.getParent().resolve(".runtime/browser-it");
        Files.createDirectories(runtime);
        ProcessBuilder command =
                new ProcessBuilder(
                        "pnpm.cmd",
                        "exec",
                        "playwright",
                        "test",
                        "--config",
                        "playwright.orbit.config.ts");
        command.directory(root.getParent().resolve("orbit-web").toFile());
        command.environment().put("ORBIT_E2E_BACKEND_URL", "http://127.0.0.1:" + port);
        command.environment().put("ORBIT_E2E_FIXTURE_PASSWORD", PASSWORD);
        command.environment().put("ORBIT_E2E_OUTPUT", runtime.toString());
        command.redirectErrorStream(true)
                .redirectOutput(runtime.resolve("browser-run.log").toFile());
        Process browser = command.start();
        try {
            assertTrue(browser.waitFor(360, TimeUnit.SECONDS), "浏览器测试超时，诊断保留在本工作区runtime目录");
            assertEquals(
                    0, browser.exitValue(), "浏览器验证失败，查看本工作区runtime/browser-it/browser-run.log");
        } finally {
            // 仅结束本次启动的测试进程及其子进程，不影响其他本地服务。
            browser.descendants().toList().reversed().forEach(ProcessHandle::destroy);
            if (browser.isAlive()) browser.destroy();
        }
    }

    @AfterAll
    static void cleanupOnlyFixtureResources() {
        if (database != null && database.matches("orbit_browser_[a-f0-9]{32}"))
            admin.execute("DROP DATABASE " + database);
        RedisClient redis = RedisClient.create("redis://127.0.0.1:16379/14");
        try (var connection = redis.connect()) {
            // 预先已验证空DB14专属本轮应用；只删除明确已知的若依缓存前缀，不执行FLUSH。
            for (String prefix :
                    List.of(
                            "sys_config:",
                            "sys_dict:",
                            "login_tokens:",
                            "captcha_codes:",
                            "pwd_err_cnt:",
                            "repeat_submit:",
                            "rate_limit:")) {
                var keys = connection.sync().keys(prefix + "*");
                if (!keys.isEmpty()) connection.sync().del(keys.toArray(String[]::new));
            }
        } finally {
            redis.shutdown();
        }
    }
}

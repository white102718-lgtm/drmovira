package com.ruoyi.web.controller.orbit;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.config.RuoYiConfig;
import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.framework.config.*;
import com.ruoyi.framework.config.properties.PermitAllUrlProperties;
import com.ruoyi.framework.interceptor.impl.SameUrlDataInterceptor;
import com.ruoyi.framework.security.filter.JwtAuthenticationTokenFilter;
import com.ruoyi.framework.security.handle.*;
import com.ruoyi.framework.web.service.*;
import com.ruoyi.system.orbit.config.*;
import com.ruoyi.web.config.orbit.OrbitConfigurationSecurity;
import io.lettuce.core.RedisClient;
import java.net.URI;
import java.net.http.*;
import java.nio.file.Path;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.*;
import javax.sql.DataSource;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.*;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.*;
import org.springframework.core.io.*;
import org.springframework.core.io.support.EncodedResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.context.request.*;

/** 真实TCP HTTP、签名JWT、Redis会话、MySQL和业务事务联合测试；仅外部平台传输使用fixture。 */
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        classes = OrbitConfigurationNetworkIT.TestApplication.class,
        properties = {
            "server.address=127.0.0.1",
            "logging.config=classpath:logback-orbit-test.xml",
            "spring.data.redis.host=127.0.0.1",
            "spring.data.redis.port=16379",
            "spring.data.redis.database=15",
            "spring.data.redis.password=",
            "token.header=Authorization",
            "token.expireTime=30"
        })
@org.springframework.test.context.ActiveProfiles("orbit-network-fixture")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@ExtendWith(OutputCaptureExtension.class)
class OrbitConfigurationNetworkIT {
    private static final String TENANT = "00000000-0000-0000-0000-000000000001";
    private static final String PRIVATE = "fixture-private-input-not-a-real-secret";
    private static final String OPTIONS =
            "?useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=utf8&connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true";
    private static final String SIGNING = randomKey(64);
    private static final String ENCRYPTION = randomKey(32);
    private static DataSource source;
    private static JdbcTemplate admin;
    private static JdbcTemplate jdbc;
    private static String database;
    private final List<String> ownedSessions = new ArrayList<>();
    private final HttpClient client =
            HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(5))
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();
    @Autowired TokenService tokens;
    @Autowired RedisCache redis;
    @Autowired ObjectMapper json;
    @LocalServerPort int port;

    private static String randomKey(int size) {
        byte[] bytes = new byte[size];
        new SecureRandom().nextBytes(bytes);
        try {
            return Base64.getEncoder().encodeToString(bytes);
        } finally {
            Arrays.fill(bytes, (byte) 0);
        }
    }

    @DynamicPropertySource
    static void isolatedServices(DynamicPropertyRegistry registry) throws Exception {
        Path root = Path.of("").toAbsolutePath();
        while (!java.nio.file.Files.exists(
                root.resolve("sql/orbit/V001__system_configuration.sql"))) {
            root = root.getParent();
            if (root == null) throw new IllegalStateException("未找到本项目SQL");
        }
        // 连接前只允许固定回环地址；任何创建/清理之前核实数据目录属于本工作区。
        admin =
                new JdbcTemplate(
                        new DriverManagerDataSource(
                                "jdbc:mysql://127.0.0.1:13306/" + OPTIONS, "root", ""));
        String expected =
                root.getParent()
                                .resolve(".runtime/mysql-it/data")
                                .toString()
                                .replace('\\', '/')
                                .toLowerCase(Locale.ROOT)
                        + "/";
        assertEquals(
                expected,
                admin.queryForObject("SELECT @@datadir", String.class)
                        .replace('\\', '/')
                        .toLowerCase(Locale.ROOT));
        RedisClient preflight = RedisClient.create("redis://127.0.0.1:16379/15");
        try (var connection = preflight.connect()) {
            String dir =
                    connection
                            .sync()
                            .configGet("dir")
                            .get("dir")
                            .replace('\\', '/')
                            .toLowerCase(Locale.ROOT);
            String workspace =
                    root.getParent().toString().replace('\\', '/').toLowerCase(Locale.ROOT);
            String cygwin =
                    "/cygdrive/"
                            + workspace.charAt(0)
                            + workspace.substring(2)
                            + "/.runtime/redis-it";
            String msys = "/" + workspace.charAt(0) + workspace.substring(2) + "/.runtime/redis-it";
            assertTrue(
                    dir.equals(cygwin)
                            || dir.equals(msys)
                            || dir.equals(workspace + "/.runtime/redis-it"),
                    "Redis不属于本工作区测试目录");
        } finally {
            preflight.shutdown();
        }
        database = "orbit_net_" + UUID.randomUUID().toString().replace("-", "");
        admin.execute(
                "CREATE DATABASE "
                        + database
                        + " CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs");
        source =
                new DriverManagerDataSource(
                        "jdbc:mysql://127.0.0.1:13306/" + database + OPTIONS, "root", "");
        jdbc = new JdbcTemplate(source);
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
        registry.add("token.secret", () -> SIGNING);
    }

    @Configuration(proxyBeanMethods = false)
    @Profile("orbit-network-fixture")
    @EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
    @Import({
        SecurityConfig.class,
        ResourcesConfig.class,
        PermitAllUrlProperties.class,
        RuoYiConfig.class,
        SameUrlDataInterceptor.class,
        JwtAuthenticationTokenFilter.class,
        AuthenticationEntryPointImpl.class,
        LogoutSuccessHandlerImpl.class,
        PermissionService.class,
        TokenService.class,
        RedisConfig.class,
        RedisCache.class,
        OrbitConfigurationSecurity.class,
        OrbitConfigurationController.class,
        OrbitConfigurationExceptionHandler.class,
        ConfigurationService.class
    })
    static class TestApplication {
        @Bean
        DataSource source() {
            return source;
        }

        @Bean
        DataSourceTransactionManager transactionManager(DataSource source) {
            return new DataSourceTransactionManager(source);
        }

        @Bean
        ConfigurationMapper mapper(DataSource source) throws Exception {
            SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
            factory.setDataSource(source);
            factory.setConfigLocation(new ClassPathResource("mybatis/mybatis-config.xml"));
            factory.setMapperLocations(
                    new ClassPathResource("mapper/orbit/ConfigurationMapper.xml"));
            return new SqlSessionTemplate(factory.getObject()).getMapper(ConfigurationMapper.class);
        }

        @Bean
        SecretCipher cipher() {
            return new SecretCipher("network-fixture", Map.of("network-fixture", ENCRYPTION));
        }

        @Bean
        ConnectionProbe platformTransport() {
            ConnectionProbe controlled = org.mockito.Mockito.mock(ConnectionProbe.class);
            org.mockito.Mockito.when(
                            controlled.check(
                                    org.mockito.ArgumentMatchers.anyString(),
                                    org.mockito.ArgumentMatchers.anyMap(),
                                    org.mockito.ArgumentMatchers.anyMap()))
                    .thenReturn(
                            new ConnectionProbe.Result("READ_VERIFIED", "受控平台传输fixture，未验证真实平台"));
            return controlled;
        }
    }

    @BeforeEach
    void clearOnlyOwnedSchema() {
        for (String table :
                List.of(
                        "orbit_configuration_audit",
                        "orbit_configuration_idempotency",
                        "orbit_system_configuration")) jdbc.execute("DELETE FROM " + table);
        jdbc.update(
                "UPDATE orbit_user_scope SET tenant_id=?, enabled=1, data_role='SUPER_ADMIN' WHERE user_id=1",
                TENANT);
    }

    @AfterEach
    void revokeOnlyOwnedSessions() {
        ownedSessions.forEach(tokens::delLoginUser);
        ownedSessions.clear();
    }

    @AfterAll
    static void dropOnlyGeneratedSchema() {
        if (database != null && database.matches("orbit_net_[a-f0-9]{32}"))
            admin.execute("DROP DATABASE " + database);
    }

    private String session(Set<String> permissions) {
        LoginUser login = new LoginUser();
        login.setUserId(1L);
        login.setPermissions(permissions);
        SysUser user = new SysUser();
        user.setUserId(1L);
        user.setUserName("network-fixture-admin");
        login.setUser(user);
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setRemoteAddr("127.0.0.1");
        request.addHeader("User-Agent", "ORBIT-network-fixture");
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
        try {
            String signed = tokens.createToken(login);
            ownedSessions.add(login.getToken());
            return signed;
        } finally {
            RequestContextHolder.resetRequestAttributes();
        }
    }

    private String adminSession() {
        return session(Set.of("system.read", "system.integrations.manage"));
    }

    private HttpResponse<String> request(
            String method, String path, String token, String body, String... headers)
            throws Exception {
        HttpRequest.Builder request =
                HttpRequest.newBuilder(
                                URI.create(
                                        "http://127.0.0.1:"
                                                + port
                                                + "/api/v1/system-configurations"
                                                + path))
                        .timeout(Duration.ofSeconds(10));
        if (token != null) request.header("Authorization", "Bearer " + token);
        for (int i = 0; i < headers.length; i += 2) request.header(headers[i], headers[i + 1]);
        request.header("Content-Type", "application/json")
                .method(
                        method,
                        body == null
                                ? HttpRequest.BodyPublishers.noBody()
                                : HttpRequest.BodyPublishers.ofString(body));
        return client.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }

    private String writeBody(boolean enabled, String operation) {
        return "{\"section\":\"AI_GPT\",\"name\":\"网络验证模型\",\"enabled\":"
                + enabled
                + ",\"settings\":{\"model\":\"fixture-model\"},\"secrets\":{\"apiKey\":{\"operation\":\""
                + operation
                + "\""
                + (operation.equals("REPLACE") ? ",\"value\":\"" + PRIVATE + "\"" : "")
                + "}},\"reason\":\"网络联合验证\"}";
    }

    @Test
    void realHttpJwtRedisMysqlRoundTripAndClear(CapturedOutput output) throws Exception {
        String token = adminSession();
        var metadata = request("GET", "/metadata", token, null);
        assertEquals(200, metadata.statusCode());
        JsonNode catalog = json.readTree(metadata.body());
        assertTrue(catalog.path("encryptionReady").asBoolean());
        assertEquals(11, catalog.path("sections").size());
        int fields = 0;
        for (JsonNode section : catalog.path("sections")) fields += section.path("fields").size();
        assertEquals(62, fields);
        String body = writeBody(true, "REPLACE");
        var created = request("POST", "", token, body, "Idempotency-Key", "network-create-1");
        assertEquals(201, created.statusCode());
        String id = json.readTree(created.body()).path("id").asText();
        assertEquals("no-store", created.headers().firstValue("Cache-Control").orElseThrow());
        assertFalse(created.body().contains(PRIVATE));
        assertFalse(created.body().contains("v1.network-fixture."));
        var replay = request("POST", "", token, body, "Idempotency-Key", "network-create-1");
        assertEquals(201, replay.statusCode());
        assertEquals(id, json.readTree(replay.body()).path("id").asText());
        assertEquals(200, request("GET", "/" + id, token, null).statusCode());
        assertEquals(1, json.readTree(request("GET", "", token, null).body()).size());
        var tested =
                request(
                        "POST",
                        "/" + id + "/test",
                        token,
                        "{\"reason\":\"网络专项只读测试\"}",
                        "If-Match",
                        "\"1\"");
        assertEquals(200, tested.statusCode());
        assertEquals(
                "网络专项只读测试",
                jdbc.queryForObject(
                        "SELECT reason FROM orbit_configuration_audit WHERE action='READ_TEST'",
                        String.class));
        assertEquals(
                "READ_VERIFIED",
                json.readTree(tested.body())
                        .path("configuration")
                        .path("verificationStatus")
                        .asText());
        var cleared =
                request(
                        "PUT",
                        "/" + id,
                        token,
                        writeBody(false, "CLEAR"),
                        "If-Match",
                        "\"2\"",
                        "Idempotency-Key",
                        "network-clear-1");
        assertEquals(200, cleared.statusCode());
        JsonNode after = json.readTree(cleared.body());
        assertFalse(after.path("secrets").path("apiKey").path("configured").asBoolean());
        assertEquals("UNTESTED", after.path("verificationStatus").asText());
        assertEquals(
                3,
                json.readTree(request("GET", "/" + id + "/history", token, null).body())
                        .path("items")
                        .size());
        assertEquals(
                1,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orbit_system_configuration", Integer.class));
        assertEquals(
                3,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orbit_configuration_audit", Integer.class));
        assertTrue(
                redis.keys(com.ruoyi.common.constant.CacheConstants.REPEAT_SUBMIT_KEY + "*")
                        .isEmpty());
        assertFalse(
                json.writeValueAsString(
                                redis.getCacheObject(
                                        com.ruoyi.common.constant.CacheConstants.LOGIN_TOKEN_KEY
                                                + ownedSessions.getFirst()))
                        .contains(PRIVATE));
        assertFalse(output.getAll().contains(PRIVATE));
    }

    @Test
    void redisSessionRevocationRejectsPreviouslyValidSignedToken() throws Exception {
        String token = adminSession();
        assertEquals(200, request("GET", "/metadata", token, null).statusCode());
        tokens.delLoginUser(ownedSessions.getFirst());
        var denied = request("GET", "/metadata", token, null);
        assertEquals(401, denied.statusCode());
        assertEquals("UNAUTHENTICATED", json.readTree(denied.body()).path("code").asText());
    }

    @Test
    void malformedTokenNeverEchoesSensitiveInputInResponseOrLogs(CapturedOutput output)
            throws Exception {
        String malformedHeader =
                Base64.getUrlEncoder()
                        .withoutPadding()
                        .encodeToString(
                                ("{\"alg\":\"HS512\",\"private\":\"" + PRIVATE + "\" BROKEN}")
                                        .getBytes(java.nio.charset.StandardCharsets.UTF_8));
        for (String invalid : List.of(PRIVATE, malformedHeader + ".e30.c2ln")) {
            var denied = request("GET", "/metadata", invalid, null);
            assertEquals(401, denied.statusCode());
            assertFalse(denied.body().contains(PRIVATE));
        }
        assertFalse(output.getAll().contains(PRIVATE));
    }

    @Test
    void invalidSignatureCannotUseExistingRedisSession() throws Exception {
        String token = adminSession();
        int dot = token.lastIndexOf('.');
        String tampered =
                token.substring(0, dot + 1)
                        + (token.charAt(dot + 1) == 'a' ? 'b' : 'a')
                        + token.substring(dot + 2);
        assertEquals(401, request("GET", "/metadata", tampered, null).statusCode());
    }

    @Test
    void realSessionPermissionsAndDatabaseScopeAreBothRequired() throws Exception {
        String token = session(Set.of("system.read"));
        assertEquals(403, request("GET", "/metadata", token, null).statusCode());
        token = adminSession();
        jdbc.update("UPDATE orbit_user_scope SET enabled=0 WHERE user_id=1");
        assertEquals(403, request("GET", "/metadata", token, null).statusCode());
    }

    @Test
    void expiredRedisSessionCannotAuthenticateEvenWithValidSignature() throws Exception {
        String token = adminSession();
        redis.redisTemplate.expire(
                com.ruoyi.common.constant.CacheConstants.LOGIN_TOKEN_KEY + ownedSessions.getFirst(),
                Duration.ofMillis(100));
        Thread.sleep(200);
        assertEquals(401, request("GET", "/metadata", token, null).statusCode());
    }
}

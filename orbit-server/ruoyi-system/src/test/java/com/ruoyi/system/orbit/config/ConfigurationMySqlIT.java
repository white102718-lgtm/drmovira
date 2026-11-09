package com.ruoyi.system.orbit.config;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.system.orbit.analysis.*;
import com.ruoyi.system.orbit.analysis.AnalysisJobModels.*;
import com.ruoyi.system.orbit.config.ConfigurationModels.*;
import com.ruoyi.system.orbit.metrics.*;
import com.ruoyi.system.orbit.rules.*;
import com.ruoyi.system.orbit.reference.*;
import com.ruoyi.system.orbit.scope.*;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.*;
import javax.sql.DataSource;
import org.junit.jupiter.api.*;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.support.EncodedResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.annotation.EnableTransactionManagement;

/** 真MySQL8、MyBatis与Spring事务测试；仅允许本工作区13306临时实例，不接受外部数据库地址。 */
class ConfigurationMySqlIT {
    private static final String TENANT = "00000000-0000-0000-0000-000000000001";
    private static final String URL = "jdbc:mysql://127.0.0.1:13306/";
    private static final String OPTIONS =
            "?useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=utf8&connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true";
    private static String database;
    private static JdbcTemplate admin;
    private static com.zaxxer.hikari.HikariDataSource fixturePool;
    private static JdbcTemplate jdbc;
    private static AnnotationConfigApplicationContext context;
    private static ConfigurationService service;
    private static ConfigurationMapper mapper;
    private static boolean legacySummaryUnknown;
    private static int nativeMenuCount;
    private static final java.util.concurrent.atomic.AtomicReference<java.time.Instant>
            ANALYSIS_NOW =
                    new java.util.concurrent.atomic.AtomicReference<>(
                            java.time.Instant.parse("2026-11-07T07:59:00Z"));
    private static final java.time.Clock ANALYSIS_CLOCK =
            new java.time.Clock() {
                public java.time.ZoneId getZone() {
                    return java.time.ZoneOffset.UTC;
                }

                public java.time.Clock withZone(java.time.ZoneId zone) {
                    return this;
                }

                public java.time.Instant instant() {
                    return ANALYSIS_NOW.get();
                }
            };

    @Configuration
    @EnableTransactionManagement
    static class Transactions {}

    @BeforeAll
    static void initializeIsolatedSchema() throws Exception {
        Path root = Path.of("").toAbsolutePath();
        while (!java.nio.file.Files.exists(
                root.resolve("sql/orbit/V001__system_configuration.sql"))) {
            root = root.getParent();
            if (root == null) throw new IllegalStateException("未找到ORBIT仓库");
        }
        admin = new JdbcTemplate(new DriverManagerDataSource(URL + OPTIONS, "root", ""));
        String dataDirectory =
                admin.queryForObject("SELECT @@datadir", String.class).replace('\\', '/');
        String expected =
                root.getParent().resolve(".runtime/mysql-it/data").toString().replace('\\', '/');
        assertEquals(
                expected.toLowerCase(Locale.ROOT) + "/", dataDirectory.toLowerCase(Locale.ROOT));
        assertTrue(admin.queryForObject("SELECT VERSION()", String.class).startsWith("8."));
        database = "orbit_it_" + UUID.randomUUID().toString().replace("-", "");
        admin.execute(
                "CREATE DATABASE "
                        + database
                        + " CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs");
        // 真实独立连接池保留并发与事务语义，避免容量套件逐次建连累积数千TIME_WAIT。
        var poolConfig = new com.zaxxer.hikari.HikariConfig();
        poolConfig.setJdbcUrl(URL + database + OPTIONS);
        poolConfig.setUsername("root");
        poolConfig.setPassword("");
        poolConfig.setMaximumPoolSize(8);
        poolConfig.setMinimumIdle(1);
        poolConfig.setConnectionTimeout(10000);
        poolConfig.setPoolName("orbit-isolated-mysql-it");
        fixturePool = new com.zaxxer.hikari.HikariDataSource(poolConfig);
        DataSource source = fixturePool;
        jdbc = new JdbcTemplate(source);
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(root.resolve("sql/ry_20260417.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
            nativeMenuCount = jdbc.queryForObject("SELECT COUNT(*) FROM sys_menu", Integer.class);
            for (String file :
                    List.of(
                            "V001__system_configuration.sql",
                            "V002__configuration_history_cursor.sql")) {
                ScriptUtils.executeSqlScript(
                        connection,
                        new EncodedResource(
                                new FileSystemResource(root.resolve("sql/orbit/" + file)),
                                java.nio.charset.StandardCharsets.UTF_8));
            }
            jdbc.update(
                    "INSERT INTO orbit_configuration_audit(id,tenant_id,config_id,actor_id,action,revision,changed_fields_json,reason) VALUES('legacy','legacy','legacy',1,'UPDATE',1,'[]','fixture')");
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve(
                                            "sql/orbit/V003__configuration_audit_fingerprints.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
            legacySummaryUnknown =
                    jdbc.queryForObject(
                                    "SELECT COUNT(*) FROM orbit_configuration_audit WHERE id='legacy' AND before_revision IS NULL AND before_hash IS NULL AND after_hash IS NULL AND hash_algorithm IS NULL",
                                    Integer.class)
                            == 1;
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V004__analysis_job_queue.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V005__rule_draft_versions.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V006__business_identity_mapping.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V007__metric_profile_versions.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V008__account_scope_snapshots.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V009__scope_permission_versions.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve(
                                            "sql/orbit/V010__scope_directory_identity_versions.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V011__scope_public_request_keys.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V012__scope_page_menu.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V013__scope_tenant_proof.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V014__scope_freeze_audit.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V015__scope_actor_locator.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V016__scope_audit_identity.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V017__scope_audit_request.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V018__scope_audit_query_indexes.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V019__audit_page_menu.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(connection, new EncodedResource(new FileSystemResource(root.resolve("sql/orbit/V020__reference_catalog_imports.sql")), java.nio.charset.StandardCharsets.UTF_8));
        }
        SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
        factory.setDataSource(source);
        // 使用若依实际全局配置；不能在测试中额外开启转驼峰掩盖映射缺失。
        factory.setConfigLocation(
                new FileSystemResource(
                        root.resolve("ruoyi-admin/src/main/resources/mybatis/mybatis-config.xml")));
        factory.setMapperLocations(
                new ClassPathResource("mapper/orbit/ConfigurationMapper.xml"),
                new ClassPathResource("mapper/orbit/AnalysisJobMapper.xml"),
                new ClassPathResource("mapper/orbit/RuleDraftMapper.xml"),
                new ClassPathResource("mapper/orbit/MetricProfileMapper.xml"),
                new ClassPathResource("mapper/orbit/AccountScopeMapper.xml"));
        factory.getObject().getConfiguration().addMapper(ReferenceCatalogMapper.class);
        var sqlSession = new SqlSessionTemplate(factory.getObject());
        var analysisMapper =
                sqlSession.getMapper(com.ruoyi.system.orbit.analysis.AnalysisJobMapper.class);
        mapper = new SqlSessionTemplate(factory.getObject()).getMapper(ConfigurationMapper.class);
        context = new AnnotationConfigApplicationContext();
        context.register(Transactions.class);
        context.registerBean(ConfigurationMapper.class, () -> mapper);
        context.registerBean(
                ObjectMapper.class,
                () ->
                        new ObjectMapper()
                                .findAndRegisterModules()
                                .disable(
                                        com.fasterxml.jackson.databind.SerializationFeature
                                                .WRITE_DATES_AS_TIMESTAMPS));
        context.registerBean(
                SecretCipher.class,
                () ->
                        new SecretCipher(
                                "fixture",
                                Map.of(
                                        "fixture",
                                        Base64.getEncoder().encodeToString(new byte[32]))));
        // 仅平台传输使用受控fixture；数据库、Mapper和事务全部是真实实现。
        context.registerBean(
                ConnectionProbe.class,
                () -> {
                    ConnectionProbe controlled = org.mockito.Mockito.mock(ConnectionProbe.class);
                    org.mockito.Mockito.when(
                                    controlled.check(
                                            org.mockito.ArgumentMatchers.anyString(),
                                            org.mockito.ArgumentMatchers.anyMap(),
                                            org.mockito.ArgumentMatchers.anyMap()))
                            .thenReturn(
                                    new ConnectionProbe.Result(
                                            "READ_VERIFIED", "受控只读探测fixture，未访问真实平台"));
                    return controlled;
                });
        context.registerBean(
                DataSourceTransactionManager.class, () -> new DataSourceTransactionManager(source));
        context.registerBean(ConfigurationService.class);
        context.registerBean(com.ruoyi.system.orbit.analysis.AnalysisInputGuard.class);
        context.registerBean(
                com.ruoyi.system.orbit.analysis.AnalysisJobMapper.class, () -> analysisMapper);
        context.registerBean(
                com.ruoyi.system.orbit.analysis.AnalysisJobStore.class,
                () ->
                        new com.ruoyi.system.orbit.analysis.AnalysisJobStore(
                                analysisMapper,
                                context.getBean(
                                        com.ruoyi.system.orbit.analysis.AnalysisInputGuard.class),
                                context.getBean(ObjectMapper.class),
                                ANALYSIS_CLOCK));
        context.registerBean(
                RuleDraftMapper.class, () -> sqlSession.getMapper(RuleDraftMapper.class));
        context.registerBean(RuleSchedule.class);
        context.registerBean(RuleConditions.class);
        context.registerBean(RuleWriteGuard.class);
        context.registerBean(RuleOwnership.class);
        context.registerBean(RuleDraftStore.class);
        context.registerBean(
                MetricProfileMapper.class, () -> sqlSession.getMapper(MetricProfileMapper.class));
        context.registerBean(MetricProfileGuard.class);
        context.registerBean(MetricProfileRegistry.class);
        context.registerBean(
                AccountScopeMapper.class, () -> sqlSession.getMapper(AccountScopeMapper.class));
        context.registerBean(ScopeRequestGuard.class);
        context.registerBean(AccountScopeService.class);
        context.registerBean(ScopeVersionService.class);
        context.registerBean(ScopeMemberPager.class);
        context.registerBean(ServerTenantScope.class);
        context.registerBean(TenantScopeVersionProof.class);
        context.registerBean(ScopeHttpService.class);
        context.registerBean(ScopeFreezeAuditReader.class);
        context.registerBean(ScopeFreezeAuditQuery.class);
        context.registerBean(AuditEventsService.class);
        context.registerBean(ReferenceCatalogMapper.class, () -> sqlSession.getMapper(ReferenceCatalogMapper.class));
        context.registerBean(ReferenceImportGuard.class);
        context.registerBean(ReferenceImportStore.class);
        context.registerBean(AccountDirectoryPublisher.class);
        context.refresh();
        service = context.getBean(ConfigurationService.class);
    }

    @BeforeEach
    void resetDataAndSession() {
        for (String table :
                List.of(
                        "orbit_reference_outbox",
                        "orbit_reference_event",
                        "orbit_reference_idempotency",
                        "orbit_reference_import",
                        "orbit_reference_product_agent",
                        "orbit_reference_record",
                        "orbit_account_scope_audit",
                        "orbit_account_scope_tenant_proof",
                        "orbit_account_scope_permission",
                        "orbit_account_scope_member",
                        "orbit_account_scope_snapshot",
                        "orbit_account_scope_clock",
                        "orbit_account_scope_directory",
                        "orbit_metric_profile_event",
                        "orbit_metric_profile_version",
                        "orbit_rule_draft_idempotency",
                        "orbit_rule_draft_event",
                        "orbit_rule_draft_version",
                        "orbit_rule_draft",
                        "orbit_analysis_job_event",
                        "orbit_analysis_job",
                        "orbit_analysis_daily_quota",
                        "orbit_analysis_gate",
                        "orbit_configuration_audit",
                        "orbit_configuration_idempotency",
                        "orbit_system_configuration")) jdbc.execute("DELETE FROM " + table);
        jdbc.update("UPDATE orbit_reference_catalog_version SET revision=0");
        jdbc.update("DELETE FROM orbit_business_team_manager");
        jdbc.update("DELETE FROM orbit_business_user WHERE user_id<>1");
        jdbc.update("UPDATE orbit_business_user SET team_id=?,enabled=1 WHERE user_id=1", TENANT);
        jdbc.update(
                "UPDATE orbit_business_team SET enabled=1 WHERE tenant_id=? AND id=?",
                TENANT,
                TENANT);
        jdbc.update("DELETE FROM orbit_business_team WHERE id<>?", TENANT);
        jdbc.update("DELETE FROM orbit_user_scope WHERE user_id>=900000");
        jdbc.update("DELETE FROM sys_user WHERE user_id>=900000");
        jdbc.update("UPDATE sys_user SET status='0',del_flag='0' WHERE user_id=1");
        jdbc.update(
                "UPDATE orbit_user_scope SET tenant_id=?, enabled=1, data_role='SUPER_ADMIN' WHERE user_id=1",
                TENANT);
        ANALYSIS_NOW.set(java.time.Instant.parse("2026-11-07T07:59:00Z"));
        login();
    }

    private static void login() {
        LoginUser user = new LoginUser();
        user.setUserId(1L);
        user.setPermissions(Set.of("system.read", "system.integrations.manage"));
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, null, List.of()));
    }

    @AfterEach
    void clearSession() {
        SecurityContextHolder.clearContext();
    }

    @AfterAll
    static void cleanupOnlyCreatedSchema() {
        if (context != null) context.close();
        if (fixturePool != null) fixturePool.close();
        if (database != null && database.matches("orbit_it_[a-f0-9]{32}"))
            admin.execute("DROP DATABASE " + database);
    }

    private WriteRequest request(String name) {
        return new WriteRequest(
                "AI_GPT",
                name,
                true,
                Map.of("model", "fixture-model"),
                Map.of("apiKey", new SecretChange("REPLACE", "fixture-token-no-platform")),
                "本地集成测试");
    }

    private int count(String table) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM " + table, Integer.class);
    }

    @Test
    void originalAndUpgradeScriptsPreserveNativeMenusAndUnknownLegacyHashes() {
        assertTrue(legacySummaryUnknown);
        assertEquals(
                nativeMenuCount,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM sys_menu WHERE menu_id < 31000", Integer.class));
        assertEquals(
                3,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM sys_menu WHERE menu_id IN (31000,31080,31081)",
                        Integer.class));
        assertEquals(
                4,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='orbit_configuration_audit' AND column_name IN ('before_revision','before_hash','after_hash','hash_algorithm') AND column_comment <> ''",
                        Integer.class));
    }

    @Test
    void savesEncryptedCredentialReadsAllMappedFieldsAndReplaysSanitizedResponse()
            throws Exception {
        View created = service.save(null, 0, "mysql-create-1", request("集成模型"));
        View replay = service.save(null, 0, "mysql-create-1", request("集成模型"));
        assertEquals(created.id(), replay.id());
        assertEquals(1, count("orbit_system_configuration"));
        assertEquals(1, count("orbit_configuration_audit"));
        Row stored = mapper.find(TENANT, created.id());
        assertEquals(TENANT, stored.tenantId);
        assertEquals("fixture-model", created.settings().get("model"));
        assertNotNull(created.updatedAt());
        assertTrue(created.secrets().get("apiKey").configured());
        assertFalse(stored.secretsJson.contains("fixture-token-no-platform"));
        String response = new ObjectMapper().findAndRegisterModules().writeValueAsString(replay);
        assertFalse(response.contains("fixture-token-no-platform"));
        assertFalse(response.contains("v1.fixture."));
        AuditView audit = service.history(created.id(), null, 1).items().getFirst();
        assertEquals(1L, audit.actorId());
        assertEquals(0L, audit.beforeRevision());
        assertEquals(ConfigurationFingerprint.of(stored), audit.afterHash());
        assertNotNull(audit.createdAt());
    }

    @Test
    void failedValidationRollsBackIdempotencyReservation() {
        WriteRequest bad =
                new WriteRequest(
                        "AI_GPT",
                        "无凭据",
                        true,
                        Map.of("model", "fixture-model"),
                        Map.of(),
                        "fixture");
        assertThrows(
                ConfigurationException.class, () -> service.save(null, 0, "mysql-invalid", bad));
        assertEquals(0, count("orbit_system_configuration"));
        assertEquals(0, count("orbit_configuration_audit"));
        assertEquals(0, count("orbit_configuration_idempotency"));
    }

    @Test
    void auditInsertFailureRollsBackConfigurationAndIdempotencyTogether() {
        jdbc.execute(
                "CREATE TRIGGER orbit_it_audit_fail BEFORE INSERT ON orbit_configuration_audit FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture audit failure'");
        try {
            assertThrows(
                    RuntimeException.class,
                    () -> service.save(null, 0, "mysql-audit-fail", request("审计失败")));
            assertEquals(0, count("orbit_system_configuration"));
            assertEquals(0, count("orbit_configuration_idempotency"));
        } finally {
            jdbc.execute("DROP TRIGGER orbit_it_audit_fail");
        }
    }

    @Test
    void historyPaginatesAndConnectsPersistedStateDigests() {
        View created = service.save(null, 0, "mysql-history-1", request("历史模型"));
        String before = ConfigurationFingerprint.of(mapper.find(TENANT, created.id()));
        service.save(
                created.id(),
                1,
                "mysql-history-2",
                new WriteRequest(
                        "AI_GPT",
                        "已停用",
                        false,
                        Map.of("model", "fixture-model"),
                        Map.of("apiKey", new SecretChange("CLEAR", null)),
                        "清除凭据"));
        AuditPage first = service.history(created.id(), null, 1);
        assertEquals(2L, first.nextBeforeRevision());
        assertEquals(before, first.items().getFirst().beforeHash());
        assertEquals(
                ConfigurationFingerprint.of(mapper.find(TENANT, created.id())),
                first.items().getFirst().afterHash());
        AuditPage second = service.history(created.id(), first.nextBeforeRevision(), 1);
        assertEquals(1, second.items().getFirst().revision());
        assertNull(second.nextBeforeRevision());
        assertFalse(service.get(created.id()).secrets().get("apiKey").configured());
    }

    @Test
    void readVerificationWritesUtcTimestampAndAuditThenEditInvalidatesVerification() {
        View created = service.save(null, 0, "mysql-read-create", request("只读验证模型"));
        String before = ConfigurationFingerprint.of(mapper.find(TENANT, created.id()));
        java.time.Instant started = java.time.Instant.now().minusSeconds(2);
        service.test(created.id(), 1, "数据库专项只读测试");
        View verified = service.get(created.id());
        assertEquals("READ_VERIFIED", verified.verificationStatus());
        assertEquals(2, verified.revision());
        assertNotNull(verified.verifiedAt());
        assertTrue(verified.verifiedAt().isAfter(started));
        assertTrue(verified.verifiedAt().isBefore(java.time.Instant.now().plusSeconds(2)));
        AuditView audit = service.history(created.id(), null, 1).items().getFirst();
        assertEquals("READ_TEST", audit.action());
        assertEquals("数据库专项只读测试", audit.reason());
        assertEquals(before, audit.beforeHash());
        assertEquals(
                ConfigurationFingerprint.of(mapper.find(TENANT, created.id())), audit.afterHash());
        service.save(created.id(), 2, "mysql-read-update", request("已修改模型"));
        assertEquals("UNTESTED", service.get(created.id()).verificationStatus());
        assertNull(service.get(created.id()).verifiedAt());
    }

    @Test
    void foreignTenantAndRevokedScopeCannotReadConfigurationOrHistory() {
        View created = service.save(null, 0, "mysql-tenant-1", request("隔离模型"));
        String other = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,?)", other, "测试其他租户");
        jdbc.update("UPDATE orbit_user_scope SET tenant_id=? WHERE user_id=1", other);
        assertTrue(service.list().isEmpty());
        assertThrows(ConfigurationException.class, () -> service.get(created.id()));
        assertThrows(ConfigurationException.class, () -> service.history(created.id(), null, 50));
        jdbc.update("UPDATE orbit_user_scope SET enabled=0 WHERE user_id=1");
        assertEquals(
                403, assertThrows(ConfigurationException.class, () -> service.list()).status());
    }

    private List<Object> concurrent(Callable<Object> first, Callable<Object> second)
            throws Exception {
        try (ExecutorService workers = Executors.newFixedThreadPool(2)) {
            CountDownLatch ready = new CountDownLatch(2);
            CountDownLatch start = new CountDownLatch(1);
            java.util.function.Function<Callable<Object>, Callable<Object>> gated =
                    task ->
                            () -> {
                                login();
                                ready.countDown();
                                try {
                                    if (!start.await(5, TimeUnit.SECONDS))
                                        throw new IllegalStateException("并发屏障超时");
                                    return task.call();
                                } catch (ConfigurationException
                                        | RuleDraftStore.Failure
                                        | MetricProfileRegistry.Failure
                                        | AccountScopeService.Failure error) {
                                    return error;
                                } finally {
                                    SecurityContextHolder.clearContext();
                                }
                            };
            Future<Object> a = workers.submit(gated.apply(first));
            Future<Object> b = workers.submit(gated.apply(second));
            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();
            return List.of(a.get(15, TimeUnit.SECONDS), b.get(15, TimeUnit.SECONDS));
        }
    }

    @Test
    void concurrentSameIdempotencyKeyProducesOneConfigurationAndAudit() throws Exception {
        WriteRequest request = request("并发幂等模型");
        List<Object> results =
                concurrent(
                        () -> service.save(null, 0, "mysql-race-same", request),
                        () -> service.save(null, 0, "mysql-race-same", request));
        assertInstanceOf(View.class, results.get(0));
        assertInstanceOf(View.class, results.get(1));
        assertEquals(((View) results.get(0)).id(), ((View) results.get(1)).id());
        assertEquals(1, count("orbit_system_configuration"));
        assertEquals(1, count("orbit_configuration_audit"));
    }

    @Test
    void concurrentRevisionUpdatesCommitExactlyOnce() throws Exception {
        View created = service.save(null, 0, "mysql-cas-create", request("并发版本模型"));
        List<Object> results =
                concurrent(
                        () -> service.save(created.id(), 1, "mysql-cas-a", request("版本A")),
                        () -> service.save(created.id(), 1, "mysql-cas-b", request("版本B")));
        assertEquals(1, results.stream().filter(View.class::isInstance).count());
        ConfigurationException failure =
                (ConfigurationException)
                        results.stream()
                                .filter(ConfigurationException.class::isInstance)
                                .findFirst()
                                .orElseThrow();
        assertEquals(409, failure.status());
        assertEquals(2, count("orbit_configuration_audit"));
        assertEquals(2, count("orbit_configuration_idempotency"));
        assertEquals(2, mapper.find(TENANT, created.id()).revision);
    }

    @Test
    void analysisLimitsPersistWithRevisionAndChangedFieldAudit() {
        View created =
                service.save(
                        null,
                        0,
                        "limits-create",
                        new WriteRequest(
                                "AI_SUGGESTIONS",
                                "分析限制策略",
                                false,
                                Map.of(
                                        "minimumCooldownMinutes",
                                        120,
                                        "maximumDailyAnalysesPerObject",
                                        7),
                                Map.of(),
                                "新增限制"));
        assertEquals(120, service.get(created.id()).settings().get("minimumCooldownMinutes"));
        assertEquals(28, service.get(created.id()).settings().get("maxDailyPoints"));
        assertEquals(500, service.get(created.id()).settings().get("maxEvidenceItems"));
        assertEquals(4096, service.get(created.id()).settings().get("maxOutputTokens"));
        assertEquals(
                7,
                jdbc.queryForObject(
                        "SELECT JSON_EXTRACT(settings_json, '$.maximumDailyAnalysesPerObject') FROM orbit_system_configuration WHERE id=?",
                        Integer.class,
                        created.id()));
        View changed =
                service.save(
                        created.id(),
                        1,
                        "limits-update",
                        new WriteRequest(
                                "AI_SUGGESTIONS",
                                "分析限制策略",
                                false,
                                Map.of(
                                        "minimumCooldownMinutes",
                                        180,
                                        "maximumDailyAnalysesPerObject",
                                        3),
                                Map.of(),
                                "收紧限制"));
        assertEquals(2, changed.revision());
        assertEquals(180, changed.settings().get("minimumCooldownMinutes"));
        assertEquals(3, changed.settings().get("maximumDailyAnalysesPerObject"));
        AuditView audit = service.history(created.id(), null, 1).items().getFirst();
        assertEquals("收紧限制", audit.reason());
        assertTrue(
                audit.changedFields()
                        .containsAll(
                                List.of(
                                        "minimumCooldownMinutes",
                                        "maximumDailyAnalysesPerObject")));
    }

    private record AnalysisFixture(String provider, String policy, String rule, String entity) {}

    private AnalysisFixture analysisFixture(int cooldown, int daily) {
        View provider =
                service.save(
                        null,
                        0,
                        "job-provider-create",
                        new WriteRequest(
                                "AI_GPT",
                                "队列模型",
                                true,
                                Map.of("model", "fixture-model", "maxOutputTokens", 2048),
                                Map.of(
                                        "apiKey",
                                        new SecretChange("REPLACE", "fixture-token-no-platform")),
                                "测试提供商"));
        service.test(provider.id(), 1, "受控只读验证");
        View policy =
                service.save(
                        null,
                        0,
                        "job-policy-create",
                        new WriteRequest(
                                "AI_SUGGESTIONS",
                                "队列策略",
                                true,
                                Map.of(
                                        "providerConfigId",
                                        provider.id(),
                                        "minimumCooldownMinutes",
                                        cooldown,
                                        "maximumDailyAnalysesPerObject",
                                        daily,
                                        "maxOutputTokens",
                                        1024),
                                Map.of(),
                                "测试策略"));
        return new AnalysisFixture(
                provider.id(),
                policy.id(),
                java.util.UUID.randomUUID().toString(),
                java.util.UUID.randomUUID().toString());
    }

    private TrustedHit hit(AnalysisFixture f, String hitId) {
        var json = new ObjectMapper();
        var facts = json.createObjectNode();
        facts.put("schema_version", 1);
        facts.put("tenant_id", TENANT);
        facts.put("snapshot_id", TENANT);
        facts.put("entity_id", f.entity());
        facts.put("metric_profile_id", TENANT);
        facts.put("entity_type", "AD");
        facts.put("policy_version", "untrusted-version-overwritten");
        facts.put("currency", "USD");
        var metrics = json.createObjectNode();
        for (String key :
                List.of(
                        "spend",
                        "impressions",
                        "clicks",
                        "registrations",
                        "purchases",
                        "purchase_value",
                        "roas",
                        "cpm",
                        "ctr",
                        "cpc",
                        "cpa",
                        "usage")) metrics.put(key, "100");
        facts.set("current", metrics);
        facts.set("previous", metrics.deepCopy());
        facts.putArray("daily_points");
        var evidence = json.createObjectNode();
        evidence.put("id", "a".repeat(64));
        evidence.put("entity_id", f.entity());
        evidence.put("metric", "spend");
        evidence.put("date_from", "2026-11-01");
        evidence.put("date_to", "2026-11-02");
        evidence.put("value", "100");
        evidence.put("unit", "USD");
        evidence.put("calculation_version", "fixture-v1");
        facts.putArray("evidence").add(evidence);
        facts.put("budget_owner_id", f.entity());
        facts.put("budget_before", "100");
        facts.put("coverage", "1");
        facts.put("observed_at", ANALYSIS_NOW.get().toString());
        facts.put("entity_age_hours", "24");
        facts.put("paused_hours", "72");
        facts.put("maturity_days", 28);
        facts.put("quality", "SUFFICIENT");
        return new TrustedHit(
                TENANT,
                f.rule(),
                1,
                f.entity(),
                hitId,
                "fixture-slot",
                "America/Los_Angeles",
                f.policy(),
                0,
                1000,
                facts);
    }

    private AnalysisJobStore jobs() {
        return context.getBean(AnalysisJobStore.class);
    }

    @Test
    void analysisJobFreezesPublicVersionsAndReplaysWithoutChargingAgain() throws Exception {
        var f = analysisFixture(0, 5);
        var hit = hit(f, java.util.UUID.randomUUID().toString());
        Admission first = jobs().admitTrustedHit(hit);
        Admission replay = jobs().admitTrustedHit(hit);
        assertEquals(first.id(), replay.id());
        assertEquals(1, first.generation());
        assertEquals(1, count("orbit_analysis_job_event"));
        assertEquals(
                1,
                jdbc.queryForObject(
                        "SELECT SUM(admitted_count) FROM orbit_analysis_daily_quota",
                        Integer.class));
        String input =
                jdbc.queryForObject("SELECT input_json FROM orbit_analysis_job", String.class);
        assertEquals(
                first.inputHash(),
                java.util.HexFormat.of()
                        .formatHex(
                                java.security.MessageDigest.getInstance("SHA-256")
                                        .digest(
                                                input.getBytes(
                                                        java.nio.charset.StandardCharsets.UTF_8))));
        assertTrue(input.contains(f.policy() + ":1"));
        assertFalse(input.contains("untrusted-version-overwritten"));
        String settings =
                jdbc.queryForObject("SELECT settings_json FROM orbit_analysis_job", String.class);
        assertFalse(settings.contains("fixture-token-no-platform"));
        assertTrue(settings.contains("fixture-model"));
        assertEquals(
                2,
                jdbc.queryForObject(
                        "SELECT provider_revision FROM orbit_analysis_job", Integer.class));
        service.save(
                f.provider(),
                2,
                "job-provider-edit",
                new WriteRequest(
                        "AI_GPT",
                        "队列模型",
                        true,
                        Map.of("model", "changed-model"),
                        Map.of(),
                        "更换当前模型"));
        assertEquals(
                settings,
                jdbc.queryForObject("SELECT settings_json FROM orbit_analysis_job", String.class));
    }

    @Test
    void concurrentDifferentHitsCannotExceedDailyAdmissionQuota() throws Exception {
        var f = analysisFixture(0, 1);
        var a = hit(f, java.util.UUID.randomUUID().toString());
        var b = hit(f, java.util.UUID.randomUUID().toString());
        var results = concurrent(() -> jobs().admitTrustedHit(a), () -> jobs().admitTrustedHit(b));
        assertEquals(1, results.stream().filter(Admission.class::isInstance).count());
        assertEquals(
                "ANALYSIS_DAILY_LIMIT",
                ((ConfigurationException)
                                results.stream()
                                        .filter(ConfigurationException.class::isInstance)
                                        .findFirst()
                                        .orElseThrow())
                        .code());
        assertEquals(1, count("orbit_analysis_job"));
        assertEquals(1, count("orbit_analysis_job_event"));
        assertEquals(
                1,
                jdbc.queryForObject("SELECT generation FROM orbit_analysis_gate", Integer.class));
        assertEquals(
                1,
                jdbc.queryForObject(
                        "SELECT admitted_count FROM orbit_analysis_daily_quota", Integer.class));
    }

    @Test
    void concurrentSameHitReplaysBeforeCooldownAndQuota() throws Exception {
        var f = analysisFixture(60, 1);
        var hit = hit(f, java.util.UUID.randomUUID().toString());
        var results =
                concurrent(() -> jobs().admitTrustedHit(hit), () -> jobs().admitTrustedHit(hit));
        assertTrue(results.stream().allMatch(Admission.class::isInstance));
        assertEquals(((Admission) results.get(0)).id(), ((Admission) results.get(1)).id());
        assertEquals(1, count("orbit_analysis_job"));
        assertEquals(
                1,
                jdbc.queryForObject(
                        "SELECT admitted_count FROM orbit_analysis_daily_quota", Integer.class));
    }

    @Test
    void dailyQuotaResetsAtRuleLocalMidnightAndSupersedesQueuedGeneration() {
        var f = analysisFixture(0, 1);
        var first = jobs().admitTrustedHit(hit(f, java.util.UUID.randomUUID().toString()));
        assertThrows(
                ConfigurationException.class,
                () -> jobs().admitTrustedHit(hit(f, java.util.UUID.randomUUID().toString())));
        ANALYSIS_NOW.set(java.time.Instant.parse("2026-11-07T08:01:00Z"));
        var next = jobs().admitTrustedHit(hit(f, java.util.UUID.randomUUID().toString()));
        assertEquals(2, next.generation());
        assertEquals(2, count("orbit_analysis_daily_quota"));
        assertEquals(
                "SUPERSEDED",
                jdbc.queryForObject(
                        "SELECT state FROM orbit_analysis_job WHERE id=?",
                        String.class,
                        first.id()));
        assertEquals(3, count("orbit_analysis_job_event"));
        assertEquals(
                2,
                jdbc.queryForObject(
                        "SELECT COUNT(DISTINCT business_date) FROM orbit_analysis_job",
                        Integer.class));
    }

    @Test
    void admissionCooldownUsesElapsedUtcAndAllowsExactBoundary() {
        var f = analysisFixture(60, 5);
        jobs().admitTrustedHit(hit(f, java.util.UUID.randomUUID().toString()));
        ANALYSIS_NOW.updateAndGet(now -> now.plusSeconds(3599));
        var error =
                assertThrows(
                        ConfigurationException.class,
                        () ->
                                jobs().admitTrustedHit(
                                                hit(f, java.util.UUID.randomUUID().toString())));
        assertEquals("ANALYSIS_COOLDOWN", error.code());
        assertEquals(1, count("orbit_analysis_job"));
        ANALYSIS_NOW.updateAndGet(now -> now.plusSeconds(1));
        assertEquals(
                2,
                jobs().admitTrustedHit(hit(f, java.util.UUID.randomUUID().toString()))
                        .generation());
    }

    @Test
    void analysisEventFailureRollsBackJobGateQuotaAndGeneration() {
        var f = analysisFixture(0, 5);
        jdbc.execute(
                "CREATE TRIGGER analysis_event_fail BEFORE INSERT ON orbit_analysis_job_event FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='controlled analysis audit failure'");
        try {
            assertThrows(
                    org.springframework.dao.DataAccessException.class,
                    () -> jobs().admitTrustedHit(hit(f, java.util.UUID.randomUUID().toString())));
        } finally {
            jdbc.execute("DROP TRIGGER analysis_event_fail");
        }
        for (String table :
                List.of(
                        "orbit_analysis_job",
                        "orbit_account_scope_permission",
                        "orbit_account_scope_member",
                        "orbit_account_scope_snapshot",
                        "orbit_account_scope_clock",
                        "orbit_account_scope_directory",
                        "orbit_metric_profile_event",
                        "orbit_metric_profile_version",
                        "orbit_rule_draft_idempotency",
                        "orbit_rule_draft_event",
                        "orbit_rule_draft_version",
                        "orbit_rule_draft",
                        "orbit_analysis_job_event",
                        "orbit_analysis_daily_quota",
                        "orbit_analysis_gate")) assertEquals(0, count(table));
    }

    @Test
    void foreignTenantAndUnverifiedProviderCannotCreateQueueRows() {
        var f = analysisFixture(0, 5);
        var hit = hit(f, java.util.UUID.randomUUID().toString());
        ((com.fasterxml.jackson.databind.node.ObjectNode) hit.facts())
                .put("tenant_id", "00000000-0000-0000-0000-000000000002");
        assertEquals(
                403,
                assertThrows(ConfigurationException.class, () -> jobs().admitTrustedHit(hit))
                        .status());
        service.save(
                f.provider(),
                2,
                "job-unverify",
                new WriteRequest(
                        "AI_GPT", "队列模型", true, Map.of("model", "changed"), Map.of(), "失效原验证"));
        assertEquals(
                "ANALYSIS_CONFIGURATION_UNAVAILABLE",
                assertThrows(
                                ConfigurationException.class,
                                () ->
                                        jobs().admitTrustedHit(
                                                        hit(
                                                                f,
                                                                java.util
                                                                        .UUID
                                                                        .randomUUID()
                                                                        .toString())))
                        .code());
        assertEquals(0, count("orbit_analysis_gate"));
        assertEquals(0, count("orbit_analysis_job"));
    }

    @Test
    void replayHitCannotRebindRuleRevisionOrSlot() {
        var f = analysisFixture(0, 5);
        var first = hit(f, java.util.UUID.randomUUID().toString());
        jobs().admitTrustedHit(first);
        var changed =
                new TrustedHit(
                        first.tenantId(),
                        first.ruleId(),
                        2,
                        first.entityId(),
                        first.hitId(),
                        first.slot(),
                        first.zone(),
                        first.policyId(),
                        first.ruleCooldown(),
                        first.ruleDaily(),
                        first.facts());
        assertEquals(
                "ANALYSIS_HIT_REBOUND",
                assertThrows(ConfigurationException.class, () -> jobs().admitTrustedHit(changed))
                        .code());
        assertEquals(1, count("orbit_analysis_job_event"));
    }

    private RuleDraftStore drafts() {
        return context.getBean(RuleDraftStore.class);
    }

    private com.fasterxml.jackson.databind.node.ObjectNode ruleBody() {
        return RuleWriteGuardTest.request(context.getBean(ObjectMapper.class));
    }

    private MetricProfileRegistry profiles() {
        return context.getBean(MetricProfileRegistry.class);
    }

    private com.fasterxml.jackson.databind.node.ObjectNode profileDefinition() {
        return MetricProfileGuardTest.definition(context.getBean(ObjectMapper.class));
    }

    @Test
    void metricProfilePersistsFullUnknownMappingAndNeverClaimsVerification() throws Exception {
        String id = key();
        var row = profiles().registerTrustedVersion(TENANT, 1, id, profileDefinition(), "登记待核验口径");
        assertTrue(row.published);
        assertEquals("UNVERIFIED", row.verificationState);
        assertEquals("META", row.source);
        var body = new ObjectMapper().readTree(row.bodyJson);
        assertTrue(body.get("purchase_action_type").isNull());
        assertEquals(28, body.path("maturity_days").asInt());
        assertEquals("ACCOUNT_LOCAL", body.path("timezone_policy").asText());
        assertEquals(
                row.bodyHash,
                HexFormat.of()
                        .formatHex(
                                java.security.MessageDigest.getInstance("SHA-256")
                                        .digest(
                                                row.bodyJson.getBytes(
                                                        java.nio.charset.StandardCharsets.UTF_8))));
        assertEquals(1, count("orbit_metric_profile_event"));
    }

    @Test
    void metricProfileVersionIsImmutableAndSameDefinitionReplayDoesNotAuditTwice() {
        String id = key();
        var first = profiles().registerTrustedVersion(TENANT, 1, id, profileDefinition(), "登记");
        assertEquals(
                first.bodyHash,
                profiles()
                        .registerTrustedVersion(TENANT, 1, id, profileDefinition(), "再次读取同一定义")
                        .bodyHash);
        assertEquals(
                409,
                assertThrows(
                                MetricProfileRegistry.Failure.class,
                                () ->
                                        profiles()
                                                .registerTrustedVersion(
                                                        TENANT,
                                                        1,
                                                        id,
                                                        profileDefinition()
                                                                .put("maturity_days", 14),
                                                        "不能覆盖旧版"))
                        .status());
        profiles()
                .registerTrustedVersion(
                        TENANT,
                        1,
                        id,
                        profileDefinition().put("version", "v2").put("maturity_days", 14),
                        "登记新版本");
        assertEquals(2, count("orbit_metric_profile_version"));
        assertEquals(2, count("orbit_metric_profile_event"));
        assertEquals(
                first.bodyHash,
                jdbc.queryForObject(
                        "SELECT body_hash FROM orbit_metric_profile_version WHERE tenant_id=? AND profile_id=? AND version='v1'",
                        String.class,
                        TENANT,
                        id));
    }

    @Test
    void metricProfileConcurrentSameVersionPublishesOneDefinitionAndEvent() throws Exception {
        String id = key();
        var results =
                concurrent(
                        () ->
                                profiles()
                                        .registerTrustedVersion(
                                                TENANT, 1, id, profileDefinition(), "并发登记"),
                        () ->
                                profiles()
                                        .registerTrustedVersion(
                                                TENANT, 1, id, profileDefinition(), "并发登记"));
        assertTrue(results.stream().allMatch(MetricProfileRegistry.Row.class::isInstance));
        assertEquals(1, count("orbit_metric_profile_version"));
        assertEquals(1, count("orbit_metric_profile_event"));
    }

    @Test
    void metricProfileConcurrentChangedDefinitionCannotOverwriteSameVersion() throws Exception {
        String id = key();
        var results =
                concurrent(
                        () ->
                                profiles()
                                        .registerTrustedVersion(
                                                TENANT, 1, id, profileDefinition(), "并发定义A"),
                        () ->
                                profiles()
                                        .registerTrustedVersion(
                                                TENANT,
                                                1,
                                                id,
                                                profileDefinition().put("maturity_days", 14),
                                                "并发定义B"));
        assertEquals(
                1, results.stream().filter(MetricProfileRegistry.Row.class::isInstance).count());
        assertEquals(
                1,
                results.stream()
                        .filter(
                                value ->
                                        value instanceof MetricProfileRegistry.Failure error
                                                && error.status() == 409)
                        .count());
        assertEquals(1, count("orbit_metric_profile_event"));
    }

    @Test
    void metricProfileEventFailureRollsBackDefinitionReservationAndPublish() {
        jdbc.execute(
                "CREATE TRIGGER metric_event_fail BEFORE INSERT ON orbit_metric_profile_event FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='controlled metric event failure'");
        try {
            assertThrows(
                    RuntimeException.class,
                    () ->
                            profiles()
                                    .registerTrustedVersion(
                                            TENANT, 1, key(), profileDefinition(), "登记"));
        } finally {
            jdbc.execute("DROP TRIGGER metric_event_fail");
        }
        assertEquals(0, count("orbit_metric_profile_version"));
        assertEquals(0, count("orbit_metric_profile_event"));
    }

    @Test
    void metricProfileRegistrationNeedsCurrentManagementRole() {
        businessUser(900001, TENANT, "TEAM_ADMIN");
        assertEquals(
                403,
                assertThrows(
                                MetricProfileRegistry.Failure.class,
                                () ->
                                        profiles()
                                                .registerTrustedVersion(
                                                        TENANT,
                                                        900001,
                                                        key(),
                                                        profileDefinition(),
                                                        "不是口径管理员"))
                        .status());
        assertEquals(0, count("orbit_metric_profile_version"));
    }

    @Test
    void metricProfileMetaAndFixtureDefinitionsCannotPassVerifiedRuntimeGate() {
        for (String source : List.of("META", "FIXTURE")) {
            String id = key();
            profiles()
                    .registerTrustedVersion(
                            TENANT, 1, id, profileDefinition().put("source", source), "未实测定义");
            assertEquals(
                    422,
                    assertThrows(
                                    MetricProfileRegistry.Failure.class,
                                    () -> profiles().requireVerifiedMeta(TENANT, 1, id, "v1"))
                            .status());
            assertThrows(
                    org.springframework.dao.DataAccessException.class,
                    () ->
                            jdbc.update(
                                    "UPDATE orbit_metric_profile_version SET verification_state='READ_VERIFIED' WHERE tenant_id=? AND profile_id=?",
                                    TENANT,
                                    id));
        }
    }

    @Test
    void metricProfileTenantAndRevokedIdentityAreRecheckedOnReplay() {
        String id = key();
        profiles().registerTrustedVersion(TENANT, 1, id, profileDefinition(), "登记");
        assertEquals(
                404,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () -> profiles().requireVerifiedMeta(key(), 1, id, "v1"))
                        .status());
        assertEquals(
                404,
                assertThrows(
                                MetricProfileRegistry.Failure.class,
                                () -> profiles().requireVerifiedMeta(TENANT, 1, key(), "v1"))
                        .status());
        jdbc.update("UPDATE orbit_tenant SET enabled=0 WHERE id=?", TENANT);
        try {
            assertEquals(
                    403,
                    assertThrows(
                                    RuleDraftStore.Failure.class,
                                    () ->
                                            profiles()
                                                    .registerTrustedVersion(
                                                            TENANT,
                                                            1,
                                                            id,
                                                            profileDefinition(),
                                                            "登记"))
                            .status());
        } finally {
            jdbc.update("UPDATE orbit_tenant SET enabled=1 WHERE id=?", TENANT);
        }
        assertEquals(1, count("orbit_metric_profile_event"));
    }

    private String key() {
        return UUID.randomUUID().toString();
    }

    private AccountScopeService scopes() {
        return context.getBean(AccountScopeService.class);
    }

    private ScopeMemberPager pages() {
        return context.getBean(ScopeMemberPager.class);
    }

    private ServerTenantScope serverTenants() {
        return context.getBean(ServerTenantScope.class);
    }

    @Test
    void serverTenantScopeSuperAdminIncludesOnlyEnabledSystemTenants() {
        scopeSession();
        String active = key(), disabled = key();
        jdbc.update(
                "INSERT INTO orbit_tenant(id,name,enabled) VALUES(?,'active tenant fixture',1),(?,'disabled tenant fixture',0)",
                active,
                disabled);
        var scope = serverTenants().current();
        assertEquals(1L, scope.actorId());
        assertEquals(TENANT, scope.homeTenant());
        assertEquals("SUPER_ADMIN", scope.dataRole());
        assertTrue(scope.tenantIds().containsAll(List.of(TENANT, active)));
        assertFalse(scope.tenantIds().contains(disabled));
        assertThrows(UnsupportedOperationException.class, () -> scope.tenantIds().add(key()));
        assertEquals("ServerTenantScope[REDACTED]", scope.toString());
        assertEquals(active, serverTenants().resolveWriteTarget(active.toUpperCase(Locale.ROOT)));
        assertEquals(TENANT, serverTenants().resolveWriteTarget(null));
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> serverTenants().resolveWriteTarget(disabled))
                        .status());
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> serverTenants().resolveWriteTarget(key()))
                        .status());
        assertEquals(
                400,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> serverTenants().resolveWriteTarget("not-uuid"))
                        .status());
        assertEquals(
                0,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orbit_account_scope_snapshot", Integer.class),
                "目录解析不冒充业务冻结或审计写入");
    }

    @Test
    void serverTenantScopeNonSuperRolesCannotBroadenWithWildcardOrHeader() {
        scopeSession();
        LoginUser principal =
                (LoginUser) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        principal.setPermissions(Set.of("*:*:*"));
        for (String role : List.of("USER", "TEAM_ADMIN")) {
            jdbc.update("UPDATE orbit_user_scope SET data_role=? WHERE user_id=1", role);
            assertEquals(List.of(TENANT), serverTenants().current().tenantIds());
            assertEquals(TENANT, serverTenants().resolveWriteTarget(null));
            for (String target : List.of(TENANT, key(), "invalid"))
                assertEquals(
                        403,
                        assertThrows(
                                        AccountScopeService.Failure.class,
                                        () -> serverTenants().resolveWriteTarget(target))
                                .status());
        }
    }

    @Test
    void serverTenantScopeRechecksRoleAndTenantRevocationsInsteadOfTrustingOldSnapshot() {
        scopeSession();
        String other = key();
        jdbc.update(
                "INSERT INTO orbit_tenant(id,name,enabled) VALUES(?,'scope revocation fixture',1)",
                other);
        var old = serverTenants().current();
        assertTrue(old.tenantIds().contains(other));
        jdbc.update("UPDATE orbit_tenant SET enabled=0 WHERE id=?", other);
        assertFalse(serverTenants().current().tenantIds().contains(other));
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> serverTenants().resolveWriteTarget(other))
                        .status());
        jdbc.update("UPDATE orbit_tenant SET enabled=1 WHERE id=?", other);
        assertEquals(other, serverTenants().resolveWriteTarget(other));
        jdbc.update("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1");
        assertTrue(old.tenantIds().contains(other), "旧结果仍只是历史数据，不是授权能力");
        assertEquals(
                403,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> serverTenants().resolveWriteTarget(other))
                        .status());
        assertEquals(List.of(TENANT), serverTenants().current().tenantIds());
    }

    @Test
    void serverTenantScopeRequiresLiveSessionAndEnabledHomeIdentity() {
        scopeSession();
        LoginUser principal =
                (LoginUser) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        String token = principal.getToken();
        principal.setToken(null);
        assertEquals(
                401,
                assertThrows(AccountScopeService.Failure.class, () -> serverTenants().current())
                        .status());
        principal.setToken(token);
        jdbc.update("UPDATE orbit_user_scope SET enabled=0 WHERE user_id=1");
        try {
            assertEquals(
                    403,
                    assertThrows(AccountScopeService.Failure.class, () -> serverTenants().current())
                            .status());
        } finally {
            jdbc.update("UPDATE orbit_user_scope SET enabled=1 WHERE user_id=1");
        }
        jdbc.update("UPDATE orbit_tenant SET enabled=0 WHERE id=?", TENANT);
        try {
            assertEquals(
                    403,
                    assertThrows(AccountScopeService.Failure.class, () -> serverTenants().current())
                            .status());
        } finally {
            jdbc.update("UPDATE orbit_tenant SET enabled=1 WHERE id=?", TENANT);
        }
        assertEquals(TENANT, serverTenants().current().homeTenant());
    }

    private TenantScopeVersionProof tenantProofs() {
        return context.getBean(TenantScopeVersionProof.class);
    }

    @Test
    void tenantProofEitherClockChangeInvalidatesOldPair() {
        scopeSession();
        String other = key();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'dual clock fixture')", other);
        var first = tenantProofs().currentTrusted(other);
        tenantProofs().requireCurrentTrusted(first);
        jdbc.update("UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=?", TENANT);
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> tenantProofs().requireCurrentTrusted(first))
                        .status());
        var second = tenantProofs().currentTrusted(other);
        assertEquals(first.homeVersion() + 1, second.homeVersion());
        assertEquals(first.targetVersion(), second.targetVersion());
        jdbc.update("UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=?", other);
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> tenantProofs().requireCurrentTrusted(second))
                        .status());
        var third = tenantProofs().currentTrusted(other);
        assertEquals(second.homeVersion(), third.homeVersion());
        assertEquals(second.targetVersion() + 1, third.targetVersion());
        tenantProofs().requireCurrentTrusted(third);
    }

    @Test
    void tenantProofSameTenantUsesOneClockAndMaximumPairDoesNotOverflow() {
        scopeSession();
        var same = tenantProofs().currentTrusted(TENANT);
        assertEquals(same.homeVersion(), same.targetVersion());
        String other = key();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'max clock fixture')", other);
        jdbc.update(
                "UPDATE orbit_scope_version SET version=? WHERE tenant_id IN(?,?)",
                ScopeVersionService.MAX_VERSION,
                TENANT,
                other);
        try {
            var proof = tenantProofs().currentTrusted(other);
            assertEquals(ScopeVersionService.MAX_VERSION, proof.homeVersion());
            assertEquals(ScopeVersionService.MAX_VERSION, proof.targetVersion());
            tenantProofs().requireCurrentTrusted(proof);
            assertEquals("TenantScopeVersionProof[REDACTED]", proof.toString());
        } finally {
            // 仅测试库版本边界fixture；恢复后续用例可继续验证真实触发器，不代表业务允许回退版本。
            jdbc.update(
                    "UPDATE orbit_scope_version SET version=1000 WHERE tenant_id IN(?,?)",
                    TENANT,
                    other);
        }
    }

    @Test
    void tenantProofRechecksRoleTargetAndRejectsForgedContextOrMissingClock() {
        scopeSession();
        String other = key();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'proof access fixture')", other);
        var proof = tenantProofs().currentTrusted(other);
        var wrongActor =
                new TenantScopeVersionProof.Proof(
                        2,
                        proof.homeTenant(),
                        proof.targetTenant(),
                        proof.dataRole(),
                        proof.homeVersion(),
                        proof.targetVersion());
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> tenantProofs().requireCurrentTrusted(wrongActor))
                        .status());
        var invalid =
                new TenantScopeVersionProof.Proof(
                        1,
                        proof.homeTenant(),
                        proof.targetTenant(),
                        proof.dataRole(),
                        0,
                        proof.targetVersion());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> tenantProofs().requireCurrentTrusted(invalid))
                        .status());
        jdbc.update("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1");
        assertEquals(
                403,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> tenantProofs().requireCurrentTrusted(proof))
                        .status());
        jdbc.update("UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=1");
        jdbc.update("UPDATE orbit_tenant SET enabled=0 WHERE id=?", other);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> tenantProofs().currentTrusted(other))
                        .status());
        jdbc.update("UPDATE orbit_tenant SET enabled=1 WHERE id=?", other);
        long restoreVersion = context.getBean(AccountScopeMapper.class).scopeVersion(other);
        jdbc.update("DELETE FROM orbit_scope_version WHERE tenant_id=?", other);
        try {
            assertEquals(
                    503,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> tenantProofs().currentTrusted(other))
                            .status());
        } finally {
            // 仅恢复本例破坏的随机测试租户原版本，不允许污染后续全租户查询。
            jdbc.update(
                    "INSERT INTO orbit_scope_version(tenant_id,version) VALUES(?,?)",
                    other,
                    restoreVersion);
        }
    }

    @Test
    void sessionScopeFreezesOnlyTargetAndReplaysBoundIdentityWithoutTargetMembership() {
        scopeSession();
        String other = key();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'target snapshot fixture')", other);
        String account = key();
        jdbc.update(
                "INSERT INTO orbit_account_scope_directory(tenant_id,id,external_id,name,currency,account_status,auth_status) VALUES(?,?,'12345678901234567890123456789012','target member','USD','ACTIVE','AUTHORIZED')",
                other,
                account);
        String request = key();
        var frozen = scopes().freezeForSessionTrusted(other, request, scopeFilter());
        assertEquals(1, frozen.members().size());
        assertEquals(account, frozen.members().getFirst().accountId);
        assertEquals("12345678901234567890123456789012", frozen.members().getFirst().externalId);
        assertEquals(other, frozen.snapshot().tenantId);
        assertEquals(1, frozen.snapshot().actorId);
        assertEquals(
                frozen.snapshot().id,
                scopes().freezeForSessionTrusted(other, request, scopeFilter()).snapshot().id);
        assertEquals(
                frozen.snapshot().id,
                scopes().sessionSnapshotTrusted(other, frozen.snapshot().id).id);
        assertEquals(
                0,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orbit_business_user WHERE tenant_id=? AND user_id=1",
                        Integer.class,
                        other));
        var changed = scopeFilter();
        ((com.fasterxml.jackson.databind.node.ObjectNode) changed.get("filter"))
                .put("q", "changed");
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().freezeForSessionTrusted(other, request, changed))
                        .status());
        jdbc.update("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1");
        assertEquals(
                403,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().sessionSnapshotTrusted(other, frozen.snapshot().id))
                        .status());
        jdbc.update("UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=1");
        jdbc.update("UPDATE orbit_tenant SET enabled=0 WHERE id=?", other);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().sessionSnapshotTrusted(other, frozen.snapshot().id))
                        .status());
        assertEquals(1, count("orbit_account_scope_tenant_proof"));
        assertEquals(
                0,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orbit_account_scope_snapshot WHERE tenant_id=?",
                        Integer.class,
                        TENANT));
    }

    @Test
    void sessionScopeBoundVersionsInvalidateReplayAndReadsWithoutRebinding() {
        scopeSession();
        String other = key();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'bound version fixture')", other);
        for (String changed : List.of(TENANT, other)) {
            String request = key();
            var frozen = scopes().freezeForSessionTrusted(other, request, scopeFilter());
            jdbc.update(
                    "UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=?", changed);
            assertEquals(
                    409,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () ->
                                            scopes().freezeForSessionTrusted(
                                                            other, request, scopeFilter()))
                            .status());
            assertEquals(
                    409,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () ->
                                            scopes().sessionSnapshotTrusted(
                                                            other, frozen.snapshot().id))
                            .status());
        }
        assertEquals(2, count("orbit_account_scope_tenant_proof"));
        assertEquals(2, count("orbit_account_scope_snapshot"));
    }

    @Test
    void sessionScopeRejectsUnauthorizedTargetOldSnapshotAndInvisibleIdsWithoutOrphans() {
        scopeSession();
        String oldKey = key();
        scopes().freezeTrusted(TENANT, 1, oldKey, scopeFilter());
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        scopes().freezeForSessionTrusted(
                                                        TENANT, oldKey, scopeFilter()))
                        .status());
        String other = key();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'denied target fixture')", other);
        var ids = new ObjectMapper().createObjectNode().put("mode", "IDS");
        ids.putArray("account_ids").add(key());
        ids.putNull("filter");
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().freezeForSessionTrusted(other, key(), ids))
                        .status());
        jdbc.update("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1");
        assertEquals(
                403,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().freezeForSessionTrusted(other, key(), scopeFilter()))
                        .status());
        assertEquals(0, count("orbit_account_scope_tenant_proof"));
        assertEquals(1, count("orbit_account_scope_snapshot"));
    }

    @Test
    void sessionScopeBindingAndMembersRollbackWithOuterTransaction() {
        scopeSession();
        directoryAccount("1234567", "rollback member", TENANT, TENANT);
        var tx =
                new org.springframework.transaction.support.TransactionTemplate(
                        context.getBean(DataSourceTransactionManager.class));
        tx.execute(
                status -> {
                    scopes().freezeForSessionTrusted(TENANT, key(), scopeFilter());
                    assertEquals(1, count("orbit_account_scope_tenant_proof"));
                    assertEquals(1, count("orbit_account_scope_member"));
                    status.setRollbackOnly();
                    return null;
                });
        assertEquals(0, count("orbit_account_scope_tenant_proof"));
        assertEquals(0, count("orbit_account_scope_snapshot"));
        assertEquals(0, count("orbit_account_scope_permission"));
        assertEquals(0, count("orbit_account_scope_member"));
    }

    @Test
    void sessionScopeWaitsForDirectoryGateBeforeReadingPermissionVersion() throws Exception {
        scopeSession();
        String account =
                directoryAccount("100000000000000001", "concurrent member", TENANT, TENANT);
        jdbc.update("INSERT INTO orbit_account_scope_clock(tenant_id) VALUES(?)", TENANT);
        var pool = Executors.newSingleThreadExecutor();
        var pending =
                new java.util.concurrent.atomic.AtomicReference<
                        Future<AccountScopeService.Frozen>>();
        var tx =
                new org.springframework.transaction.support.TransactionTemplate(
                        context.getBean(DataSourceTransactionManager.class));
        try {
            tx.execute(
                    status -> {
                        jdbc.queryForObject(
                                "SELECT revision FROM orbit_account_scope_clock WHERE tenant_id=? FOR UPDATE",
                                Long.class,
                                TENANT);
                        pending.set(
                                pool.submit(
                                        () -> {
                                            login();
                                            scopeSession();
                                            try {
                                                return scopes().freezeForSessionTrusted(
                                                                TENANT, key(), scopeFilter());
                                            } finally {
                                                SecurityContextHolder.clearContext();
                                            }
                                        }));
                        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                        boolean waiting = false;
                        while (System.nanoTime() < deadline) {
                            waiting =
                                    jdbc.queryForObject(
                                                    "SELECT COUNT(*) FROM performance_schema.data_lock_waits w JOIN performance_schema.data_locks b ON b.ENGINE_LOCK_ID=w.BLOCKING_ENGINE_LOCK_ID AND b.ENGINE=w.ENGINE WHERE b.OBJECT_SCHEMA=? AND b.OBJECT_NAME='orbit_account_scope_clock'",
                                                    Integer.class,
                                                    database)
                                            > 0;
                            if (waiting) break;
                            try {
                                Thread.sleep(20);
                            } catch (InterruptedException error) {
                                Thread.currentThread().interrupt();
                                throw new IllegalStateException(error);
                            }
                        }
                        assertTrue(waiting, "冻结必须先等待目录门闩");
                        // 修改授权版本触发字段；若冻结先持有版本共享锁，此处会与目录门闩形成死锁。
                        jdbc.update(
                                "UPDATE orbit_account_scope_directory SET external_id='100000000000000002' WHERE tenant_id=? AND id=?",
                                TENANT,
                                account);
                        return null;
                    });
            var frozen = pending.get().get(10, TimeUnit.SECONDS);
            assertEquals("100000000000000002", frozen.members().getFirst().externalId);
            assertEquals(
                    frozen.snapshot().id,
                    scopes().sessionSnapshotTrusted(TENANT, frozen.snapshot().id).id);
        } finally {
            pool.shutdownNow();
        }
    }

    private AccountScopeService.Frozen sessionPageFixture(String target, int count) {
        scopeSession();
        jdbc.update(
                "INSERT INTO orbit_tenant(id,name) VALUES(?,'session pagination fixture') ON DUPLICATE KEY UPDATE name=name",
                target);
        for (int i = 0; i < count; i++)
            jdbc.update(
                    "INSERT INTO orbit_account_scope_directory(tenant_id,id,external_id,name,currency,account_status,auth_status) VALUES(?,?,?,?,'USD','ACTIVE','AUTHORIZED')",
                    target,
                    key(),
                    String.format(java.util.Locale.ROOT, "%032d", i + 1),
                    "needle%_ é member " + i);
        return scopes().freezeForSessionTrusted(target, key(), scopeFilter());
    }

    @Test
    void sessionMembersKeysetPreservesTargetMembersWireFieldsAndBothCursorVersions()
            throws Exception {
        String target = key();
        var frozen = sessionPageFixture(target, 45);
        List<String> ids = new ArrayList<>();
        String cursor = null;
        for (int count : List.of(20, 20, 5)) {
            var page =
                    pages().pageForSessionTrusted(target, frozen.snapshot().id, null, 20, cursor);
            assertEquals(count, page.items().size());
            assertEquals(frozen.snapshot().createdAt, page.dataAsOf());
            assertEquals(frozen.snapshot().scopeVersion.longValue(), page.scopeVersion());
            ids.addAll(page.items().stream().map(ScopeMemberPager.Item::accountId).toList());
            cursor = page.nextCursor();
        }
        assertNull(cursor);
        assertEquals(frozen.members().stream().map(row -> row.accountId).toList(), ids);
        assertEquals(45, new HashSet<>(ids).size());
        var page = pages().pageForSessionTrusted(target, frozen.snapshot().id, null, 20, null);
        var cipher = context.getBean(SecretCipher.class);
        var json = context.getBean(ObjectMapper.class);
        var state =
                json.readTree(
                        cipher.decrypt(
                                page.nextCursor(),
                                target,
                                frozen.snapshot().id,
                                "SCOPE_SESSION_MEMBERS_V2/1"));
        var proof =
                context.getBean(AccountScopeMapper.class)
                        .boundTenantProof(target, frozen.snapshot().id);
        assertEquals(2, state.path("v").intValue());
        assertEquals(TENANT, state.path("home").textValue());
        assertEquals(proof.homeVersion(), state.path("home_scope").longValue());
        assertEquals(proof.targetVersion(), state.path("scope").longValue());
        assertEquals("SUPER_ADMIN", state.path("role").textValue());
        Set<String> fields = new HashSet<>();
        json.valueToTree(page).fieldNames().forEachRemaining(fields::add);
        assertEquals(Set.of("items", "next_cursor", "data_as_of", "scope_version"), fields);
        assertThrows(UnsupportedOperationException.class, () -> page.items().clear());
        assertEquals(
                0,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orbit_account_scope_snapshot WHERE tenant_id=?",
                        Integer.class,
                        TENANT));
    }

    @Test
    void sessionMembersCursorBindsQuerySizeSnapshotAndSeparatesLegacyProtocol() {
        var frozen = sessionPageFixture(TENANT, 45);
        String id = frozen.snapshot().id;
        String v2 = pages().pageForSessionTrusted(TENANT, id, "", 20, null).nextCursor();
        String v1 = pages().pageTrusted(TENANT, 1, id, "", 20, null).nextCursor();
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> pages().pageForSessionTrusted(TENANT, id, "", 20, v1))
                        .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> pages().pageTrusted(TENANT, 1, id, "", 20, v2))
                        .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> pages().pageForSessionTrusted(TENANT, id, "changed", 20, v2))
                        .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> pages().pageForSessionTrusted(TENANT, id, "", 50, v2))
                        .status());
        var other = scopes().freezeForSessionTrusted(TENANT, key(), scopeFilter());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageForSessionTrusted(
                                                        TENANT, other.snapshot().id, "", 20, v2))
                        .status());
        for (String token :
                List.of(
                        "",
                        "x".repeat(2049),
                        v2.substring(0, v2.length() / 2) + "!" + v2.substring(v2.length() / 2 + 1)))
            assertEquals(
                    422,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> pages().pageForSessionTrusted(TENANT, id, "", 20, token))
                            .status());
    }

    @Test
    void sessionMembersRejectsAuthenticatedButWrongProofFields() throws Exception {
        String target = key();
        var frozen = sessionPageFixture(target, 45);
        String id = frozen.snapshot().id;
        String cursor = pages().pageForSessionTrusted(target, id, null, 20, null).nextCursor();
        var cipher = context.getBean(SecretCipher.class);
        var json = context.getBean(ObjectMapper.class);
        var original =
                (com.fasterxml.jackson.databind.node.ObjectNode)
                        json.readTree(
                                cipher.decrypt(cursor, target, id, "SCOPE_SESSION_MEMBERS_V2/1"));
        for (String field : List.of("home", "home_scope", "role", "scope", "v", "extra")) {
            var state = original.deepCopy();
            switch (field) {
                case "home" -> state.put(field, key());
                case "home_scope" -> state.put(field, original.path(field).longValue() + 1);
                case "role" -> state.put(field, "USER");
                case "scope" -> state.put(field, original.path(field).longValue() + 1);
                case "v" -> state.put(field, 1);
                default -> state.put(field, "unknown");
            }
            String token =
                    cipher.encrypt(
                            json.writeValueAsString(state),
                            target,
                            id,
                            "SCOPE_SESSION_MEMBERS_V2/1");
            assertEquals(
                    422,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () ->
                                            pages().pageForSessionTrusted(
                                                            target, id, null, 20, token))
                            .status());
        }
        for (String field : List.of("home", "home_scope", "role")) {
            var state = original.deepCopy();
            state.remove(field);
            String token =
                    cipher.encrypt(
                            json.writeValueAsString(state),
                            target,
                            id,
                            "SCOPE_SESSION_MEMBERS_V2/1");
            assertEquals(
                    422,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () ->
                                            pages().pageForSessionTrusted(
                                                            target, id, null, 20, token))
                            .status());
        }
    }

    @Test
    void sessionMembersEitherTenantClockRevokesFirstAndSubsequentPages() {
        String target = key();
        sessionPageFixture(target, 45);
        for (String changed : List.of(TENANT, target)) {
            var frozen = scopes().freezeForSessionTrusted(target, key(), scopeFilter());
            String id = frozen.snapshot().id;
            String cursor = pages().pageForSessionTrusted(target, id, null, 20, null).nextCursor();
            jdbc.update(
                    "UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=?", changed);
            assertEquals(
                    409,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () ->
                                            pages().pageForSessionTrusted(
                                                            target, id, null, 20, cursor))
                            .status());
            assertEquals(
                    409,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> pages().pageForSessionTrusted(target, id, null, 20, null))
                            .status());
        }
    }

    @Test
    void sessionMembersCurrentActorRoleAndEnabledTargetRemainMandatory() {
        String target = key();
        var frozen = sessionPageFixture(target, 45);
        String id = frozen.snapshot().id;
        String cursor = pages().pageForSessionTrusted(target, id, null, 20, null).nextCursor();
        businessUser(900001, TENANT, "SUPER_ADMIN");
        ((LoginUser) SecurityContextHolder.getContext().getAuthentication().getPrincipal())
                .setUserId(900001L);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> pages().pageForSessionTrusted(target, id, null, 20, cursor))
                        .status());
        var own = scopes().freezeForSessionTrusted(target, key(), scopeFilter());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageForSessionTrusted(
                                                        target,
                                                        own.snapshot().id,
                                                        null,
                                                        20,
                                                        cursor))
                        .status());
        jdbc.update("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=900001");
        assertEquals(
                403,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageForSessionTrusted(
                                                        target, own.snapshot().id, null, 20, null))
                        .status());
        jdbc.update("UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=900001");
        jdbc.update("UPDATE orbit_tenant SET enabled=0 WHERE id=?", target);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageForSessionTrusted(
                                                        target, own.snapshot().id, null, 20, null))
                        .status());
    }

    @Test
    void sessionMembersSearchPageSizesMissingProofAndEncryptionFailClosed() {
        String target = key();
        var frozen = sessionPageFixture(target, 45);
        String id = frozen.snapshot().id;
        var first = pages().pageForSessionTrusted(target, id, " %_ ", 20, null);
        assertEquals(20, first.items().size());
        assertEquals(
                20,
                pages().pageForSessionTrusted(target, id, "%_", 20, first.nextCursor())
                        .items()
                        .size());
        assertEquals(
                20,
                pages().pageForSessionTrusted(target, id, " e\u0301 ", 20, null).items().size());
        String external = frozen.members().getFirst().externalId;
        var exact = pages().pageForSessionTrusted(target, id, external, 50, null);
        assertEquals(1, exact.items().size());
        assertEquals(external, exact.items().getFirst().externalId());
        for (int size : List.of(20, 50, 100, 200))
            assertEquals(
                    Math.min(45, size),
                    pages().pageForSessionTrusted(target, id, null, size, null).items().size());
        for (int size : List.of(0, 1, 21, 201))
            assertEquals(
                    422,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () ->
                                            pages().pageForSessionTrusted(
                                                            target, id, null, size, null))
                            .status());
        var none = pages().pageForSessionTrusted(target, id, "no matches", 20, null);
        assertTrue(none.items().isEmpty());
        assertNull(none.nextCursor());
        var unavailable =
                new ScopeMemberPager(
                        context.getBean(AccountScopeMapper.class),
                        scopes(),
                        new SecretCipher(null, Map.of()),
                        context.getBean(ObjectMapper.class));
        assertEquals(
                503,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> unavailable.pageForSessionTrusted(target, id, null, 20, null))
                        .status());
        jdbc.update(
                "DELETE FROM orbit_account_scope_permission WHERE tenant_id=? AND snapshot_id=?",
                target,
                id);
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> pages().pageForSessionTrusted(target, id, null, 20, null))
                        .status());
    }

    @Test
    void scopeAuditCapturesActorHomeTargetVersionsHashesAndDatabaseUtcOnly() {
        scopeSession();
        String target = key();
        var before = java.time.Instant.now();
        var frozen = sessionPageFixture(target, 1);
        var after = java.time.Instant.now();
        var row =
                jdbc.queryForMap(
                        "SELECT * FROM orbit_account_scope_audit WHERE target_tenant_id=? AND snapshot_id=?",
                        target,
                        frozen.snapshot().id);
        assertEquals(1L, ((Number) row.get("actor_id")).longValue());
        assertEquals(TENANT, row.get("home_tenant_id"));
        assertEquals(target, row.get("target_tenant_id"));
        assertEquals("SUPER_ADMIN", row.get("data_role"));
        assertEquals(TENANT, row.get("actor_subject_id"));
        assertEquals(TENANT, row.get("actor_team_id"));
        assertEquals("SCOPE_FROZEN", row.get("action"));
        assertEquals(frozen.snapshot().requestHash, row.get("request_hash"));
        assertEquals(frozen.snapshot().membersHash, row.get("members_hash"));
        assertEquals(1, ((Number) row.get("member_count")).intValue());
        var proof =
                context.getBean(AccountScopeMapper.class)
                        .boundTenantProof(target, frozen.snapshot().id);
        assertEquals(proof.homeVersion(), ((Number) row.get("home_version")).longValue());
        assertEquals(proof.targetVersion(), ((Number) row.get("target_version")).longValue());
        var at =
                ((java.time.LocalDateTime)
                                jdbc.queryForObject(
                                        "SELECT created_at FROM orbit_account_scope_audit WHERE snapshot_id=?",
                                        java.time.LocalDateTime.class,
                                        frozen.snapshot().id))
                        .toInstant(java.time.ZoneOffset.UTC);
        assertFalse(at.isBefore(before.minusSeconds(1)));
        assertFalse(at.isAfter(after.plusSeconds(1)));
        assertEquals(
                Set.of(
                        "id",
                        "target_tenant_id",
                        "snapshot_id",
                        "actor_id",
                        "home_tenant_id",
                        "data_role",
                        "action",
                        "request_hash",
                        "members_hash",
                        "member_count",
                        "home_version",
                        "target_version",
                        "created_at",
                        "actor_subject_id",
                        "actor_team_id",
                        "request_id"),
                row.keySet());
        assertNull(row.get("request_id"), "内部非HTTP冻结不伪造请求UUID");
        assertFalse(row.toString().contains("needle"));
        assertFalse(row.toString().contains(frozen.members().getFirst().externalId));
        assertEquals(
                0,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=? AND table_name='orbit_account_scope_audit' AND column_comment=''",
                        Integer.class,
                        database));
    }

    @Test
    void scopeAuditSameTenantAndIdempotentReplayCreateOneSuccessEventPerSnapshot() {
        scopeSession();
        String request = key();
        var input = scopeFilter();
        var first = scopes().freezeTrusted(TENANT, 1, request, input);
        assertEquals(
                first.snapshot().id,
                scopes().freezeTrusted(TENANT, 1, request, input).snapshot().id);
        assertEquals(1, count("orbit_account_scope_audit"));
        var row =
                jdbc.queryForMap(
                        "SELECT * FROM orbit_account_scope_audit WHERE snapshot_id=?",
                        first.snapshot().id);
        assertEquals(TENANT, row.get("home_tenant_id"));
        assertEquals(TENANT, row.get("target_tenant_id"));
        assertEquals(row.get("home_version"), row.get("target_version"));
        assertEquals(0, ((Number) row.get("member_count")).intValue());
        var changed = scopeFilter();
        ((com.fasterxml.jackson.databind.node.ObjectNode) changed.get("filter"))
                .put("q", "different request");
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().freezeTrusted(TENANT, 1, request, changed))
                        .status());
        String target = key();
        var cross = sessionPageFixture(target, 1);
        scopes().freezeForSessionTrusted(target, cross.snapshot().requestKey, scopeFilter());
        assertEquals(2, count("orbit_account_scope_audit"));
    }

    @Test
    void scopeAuditInsertFailureRollsBackSnapshotMembersVersionsAndBinding() {
        scopeSession();
        directoryAccount(
                "99999999999999999999999999999999", "audit rollback account", TENANT, TENANT);
        jdbc.execute(
                "CREATE TRIGGER scope_audit_fail BEFORE INSERT ON orbit_account_scope_audit FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='controlled scope audit failure'");
        try {
            assertThrows(
                    org.springframework.dao.DataAccessException.class,
                    () -> scopes().freezeForSessionTrusted(TENANT, key(), scopeFilter()));
            for (String table :
                    List.of(
                            "orbit_reference_outbox",
                        "orbit_reference_event",
                        "orbit_reference_idempotency",
                        "orbit_reference_import",
                        "orbit_reference_product_agent",
                        "orbit_reference_record",
                        "orbit_account_scope_audit",
                            "orbit_account_scope_snapshot",
                            "orbit_account_scope_member",
                            "orbit_account_scope_permission",
                            "orbit_account_scope_tenant_proof",
                            "orbit_account_scope_clock")) assertEquals(0, count(table), table);
        } finally {
            jdbc.execute("DROP TRIGGER scope_audit_fail");
        }
    }

    @Test
    void scopeAuditOuterRollbackDoesNotLeaveSuccessEvent() {
        scopeSession();
        var tx =
                new org.springframework.transaction.support.TransactionTemplate(
                        context.getBean(DataSourceTransactionManager.class));
        tx.execute(
                status -> {
                    scopes().freezeForSessionTrusted(TENANT, key(), scopeFilter());
                    assertEquals(1, count("orbit_account_scope_audit"));
                    status.setRollbackOnly();
                    return null;
                });
        assertEquals(0, count("orbit_account_scope_audit"));
        assertEquals(0, count("orbit_account_scope_snapshot"));
        assertEquals(0, count("orbit_account_scope_tenant_proof"));
    }

    @Test
    void scopeAuditConcurrentSameSessionKeyProducesOneSnapshotAndOneEvent() throws Exception {
        scopeSession();
        String target = key();
        jdbc.update(
                "INSERT INTO orbit_tenant(id,name) VALUES(?,'concurrent audit fixture')", target);
        String request = key();
        var pool = Executors.newFixedThreadPool(2);
        var start = new CountDownLatch(1);
        try {
            List<Future<AccountScopeService.Frozen>> jobs = new ArrayList<>();
            for (int i = 0; i < 2; i++)
                jobs.add(
                        pool.submit(
                                () -> {
                                    login();
                                    scopeSession();
                                    try {
                                        start.await();
                                        return scopes().freezeForSessionTrusted(
                                                        target, request, scopeFilter());
                                    } finally {
                                        SecurityContextHolder.clearContext();
                                    }
                                }));
            start.countDown();
            var first = jobs.getFirst().get(10, TimeUnit.SECONDS);
            assertEquals(
                    first.snapshot().id, jobs.getLast().get(10, TimeUnit.SECONDS).snapshot().id);
            assertEquals(1, count("orbit_account_scope_snapshot"));
            assertEquals(1, count("orbit_account_scope_audit"));
            assertEquals(1, count("orbit_account_scope_tenant_proof"));
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void crossScopePublicCreateReadsTargetMembersAndAuditWithoutTargetIdentity() {
        scopeSession();
        String target = key();
        sessionPageFixture(target, 45);
        String csrf = scopeHttp().csrf().get("csrf_token"), request = key();
        var view =
                scopeHttp()
                        .create(
                                request,
                                csrf,
                                target.toUpperCase(java.util.Locale.ROOT),
                                scopeFilter().toString());
        assertEquals(45, view.count());
        assertEquals(view, scopeHttp().create(request, csrf, target, scopeFilter().toString()));
        assertEquals(
                target,
                jdbc.queryForObject(
                        "SELECT tenant_id FROM orbit_account_scope_snapshot WHERE id=?",
                        String.class,
                        view.id()));
        List<String> ids = new ArrayList<>();
        String cursor = null;
        for (int count : List.of(20, 20, 5)) {
            var page = scopeHttp().members(view.id(), null, 20, cursor);
            assertEquals(count, page.items().size());
            ids.addAll(page.items().stream().map(ScopeMemberPager.Item::accountId).toList());
            cursor = page.nextCursor();
        }
        assertNull(cursor);
        assertEquals(45, new HashSet<>(ids).size());
        assertEquals(
                jdbc.queryForList(
                        "SELECT id FROM orbit_account_scope_directory WHERE tenant_id=? ORDER BY id",
                        String.class,
                        target),
                ids);
        assertEquals(
                1,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orbit_account_scope_audit WHERE target_tenant_id=? AND snapshot_id=? AND actor_id=1 AND home_tenant_id=?",
                        Integer.class,
                        target,
                        view.id(),
                        TENANT));
        assertEquals(
                0,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orbit_business_user WHERE tenant_id=? AND user_id=1",
                        Integer.class,
                        target));
    }

    @Test
    void crossScopePublicVersionChangesDisableOldCreateReplayAndMemberReads() {
        scopeSession();
        String target = key();
        sessionPageFixture(target, 45);
        String csrf = scopeHttp().csrf().get("csrf_token");
        for (String changed : List.of(TENANT, target)) {
            String request = key();
            var view = scopeHttp().create(request, csrf, target, scopeFilter().toString());
            String cursor = scopeHttp().members(view.id(), null, 20, null).nextCursor();
            jdbc.update(
                    "UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=?", changed);
            assertEquals(
                    409,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () ->
                                            scopeHttp()
                                                    .create(
                                                            request,
                                                            csrf,
                                                            target,
                                                            scopeFilter().toString()))
                            .status());
            assertEquals(
                    409,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> scopeHttp().members(view.id(), null, 20, cursor))
                            .status());
            assertEquals(
                    1,
                    jdbc.queryForObject(
                            "SELECT COUNT(*) FROM orbit_account_scope_audit WHERE snapshot_id=?",
                            Integer.class,
                            view.id()));
        }
        var current = scopeHttp().create(key(), csrf, target, scopeFilter().toString());
        jdbc.update("UPDATE orbit_tenant SET enabled=0 WHERE id=?", target);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopeHttp().members(current.id(), null, 20, null))
                        .status());
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        scopeHttp()
                                                .create(
                                                        key(),
                                                        csrf,
                                                        target,
                                                        scopeFilter().toString()))
                        .status());
    }

    @Test
    void crossScopePublicLocatorRejectsAmbiguityAndCurrentRoleCannotBroadenScope() {
        scopeSession();
        String target = key();
        sessionPageFixture(target, 1);
        String csrf = scopeHttp().csrf().get("csrf_token");
        var view = scopeHttp().create(key(), csrf, target, scopeFilter().toString());
        String other = key();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'duplicate uuid fixture')", other);
        jdbc.update(
                "INSERT INTO orbit_account_scope_snapshot(tenant_id,id,actor_id,request_key,request_json,request_hash,access_hash,directory_revision,members_hash,member_count,ready,created_at) SELECT ?,id,actor_id,request_key,request_json,request_hash,access_hash,directory_revision,members_hash,member_count,ready,created_at FROM orbit_account_scope_snapshot WHERE tenant_id=? AND id=?",
                other,
                target,
                view.id());
        var ambiguous =
                assertThrows(
                        AccountScopeService.Failure.class,
                        () -> scopeHttp().members(view.id(), null, 20, null));
        assertEquals(409, ambiguous.status());
        assertEquals("范围标识不唯一，请重新生成", ambiguous.getMessage());
        jdbc.update("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1");
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopeHttp().members(view.id(), null, 20, null))
                        .status());
        assertEquals(
                403,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        scopeHttp()
                                                .create(
                                                        key(),
                                                        csrf,
                                                        TENANT,
                                                        scopeFilter().toString()))
                        .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopeHttp().members(key(), "", 21, null))
                        .status());
    }

    @Test
    void crossScopePublicAuditFailureRollsBackWithoutSuccessMetadata() {
        scopeSession();
        String target = key();
        jdbc.update(
                "INSERT INTO orbit_tenant(id,name) VALUES(?,'public audit failure fixture')",
                target);
        String csrf = scopeHttp().csrf().get("csrf_token");
        jdbc.execute(
                "CREATE TRIGGER cross_scope_audit_fail BEFORE INSERT ON orbit_account_scope_audit FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='controlled public scope audit failure'");
        try {
            assertThrows(
                    org.springframework.dao.DataAccessException.class,
                    () -> scopeHttp().create(key(), csrf, target, scopeFilter().toString()));
            assertEquals(0, count("orbit_account_scope_snapshot"));
            assertEquals(0, count("orbit_account_scope_tenant_proof"));
            assertEquals(0, count("orbit_account_scope_audit"));
        } finally {
            jdbc.execute("DROP TRIGGER cross_scope_audit_fail");
        }
    }

    @Test
    void crossScopeLocatorIndexMigrationCanReplayWithoutChangingNativeMenus() throws Exception {
        java.nio.file.Path root = java.nio.file.Path.of("").toAbsolutePath();
        while (!java.nio.file.Files.exists(root.resolve("sql/orbit/V015__scope_actor_locator.sql")))
            root = root.getParent();
        var source = context.getBean(DataSourceTransactionManager.class).getDataSource();
        try (var connection = source.getConnection()) {
            for (int i = 0; i < 2; i++)
                ScriptUtils.executeSqlScript(
                        connection,
                        new EncodedResource(
                                new FileSystemResource(
                                        root.resolve("sql/orbit/V015__scope_actor_locator.sql")),
                                java.nio.charset.StandardCharsets.UTF_8));
        }
        assertEquals(
                3,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=? AND table_name='orbit_account_scope_snapshot' AND index_name='idx_scope_actor_locator'",
                        Integer.class,
                        database));
        assertEquals(
                nativeMenuCount,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM sys_menu WHERE menu_id<31000", Integer.class));
    }

    private ScopeFreezeAuditReader auditReads() {
        return context.getBean(ScopeFreezeAuditReader.class);
    }

    private void auditAs(long user) {
        ((LoginUser) SecurityContextHolder.getContext().getAuthentication().getPrincipal())
                .setUserId(user);
        scopeSession();
    }

    private String auditId(AccountScopeService.Frozen frozen) {
        return jdbc.queryForObject(
                "SELECT id FROM orbit_account_scope_audit WHERE target_tenant_id=? AND snapshot_id=?",
                String.class,
                frozen.snapshot().tenantId,
                frozen.snapshot().id);
    }

    private void grantAuditRoles(long user) {
        for (long role : List.of(909040L, 909041L, 909042L)) {
            jdbc.update(
                    "INSERT IGNORE INTO sys_role(role_id,role_name,role_key,role_sort,status,del_flag) VALUES(?,?,?,99,'0','0')",
                    role,
                    "审计读取fixture " + role,
                    "audit-fixture-" + role);
            jdbc.update(
                    "INSERT IGNORE INTO sys_user_role(user_id,role_id) VALUES(?,?)", user, role);
        }
        jdbc.update(
                "INSERT IGNORE INTO sys_role_menu(role_id,menu_id) VALUES(909040,31000),(909041,31080),(909042,31082)");
    }

    @AfterEach
    void cleanAuditReadRoleFixtures() {
        jdbc.update("DELETE FROM sys_role_menu WHERE role_id IN(909040,909041,909042)");
        jdbc.update("DELETE FROM sys_user_role WHERE role_id IN(909040,909041,909042)");
        jdbc.update("DELETE FROM sys_role WHERE role_id IN(909040,909041,909042)");
    }

    @Test
    void auditReadSuperAdminReadsEnabledTargetAndFrozenIdentityWithoutRawPayload() {
        scopeSession();
        String target = key();
        var frozen = sessionPageFixture(target, 1);
        String id = auditId(frozen);
        var row = auditReads().readTrusted(target, id);
        assertEquals(TENANT, row.actorSubjectId);
        assertEquals(TENANT, row.actorTeamId);
        assertEquals(target, row.targetTenantId);
        assertEquals(1, row.memberCount);
        assertEquals("ScopeFreezeAudit[REDACTED]", row.toString());
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditReads().readTrusted(TENANT, id))
                        .status());
        jdbc.update("UPDATE orbit_tenant SET enabled=0 WHERE id=?", target);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditReads().readTrusted(target, id))
                        .status());
    }

    @Test
    void auditReadUserOwnHistoryDoesNotGrantOtherActorsOrForeignTargetEvents() {
        scopeSession();
        businessUser(900001, TENANT, "USER");
        businessUser(900002, TENANT, "USER");
        var own = scopes().freezeTrusted(TENANT, 900001, key(), scopeFilter());
        var other = scopes().freezeTrusted(TENANT, 900002, key(), scopeFilter());
        grantAuditRoles(900001);
        auditAs(900001);
        assertEquals(900001, auditReads().readTrusted(TENANT, auditId(own)).actorId);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditReads().readTrusted(TENANT, auditId(other)))
                        .status());
        login();
        scopeSession();
        String foreign = key();
        var oldSuper = sessionPageFixture(foreign, 1);
        String homeEvent = auditId(scopes().freezeTrusted(TENANT, 1, key(), scopeFilter()));
        String foreignEvent = auditId(oldSuper);
        jdbc.update("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1");
        assertEquals("SUPER_ADMIN", auditReads().readTrusted(TENANT, homeEvent).dataRole);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditReads().readTrusted(foreign, foreignEvent))
                        .status());
    }

    @Test
    void auditReadTeamUsesFrozenOwnershipAndCurrentManagedTeamsAndMemberVisibility() {
        scopeSession();
        businessUser(900001, TENANT, "TEAM_ADMIN");
        String team = businessTeam(),
                nextTeam = businessTeam(),
                owner = businessUser(900002, team, "USER");
        String account = directoryAccount("200000000000000001", "team audit member", owner, team);
        var frozen = scopes().freezeTrusted(TENANT, 900002, key(), scopeFilter());
        String id = auditId(frozen);
        grantAuditRoles(900001);
        jdbc.update(
                "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) VALUES(?,900001,?)",
                TENANT,
                team);
        auditAs(900001);
        assertEquals(team, auditReads().readTrusted(TENANT, id).actorTeamId);
        jdbc.update("UPDATE orbit_business_user SET team_id=? WHERE user_id=900002", nextTeam);
        assertEquals(team, auditReads().readTrusted(TENANT, id).actorTeamId, "调队不能改写事件冻结团队");
        jdbc.update(
                "UPDATE orbit_business_team_manager SET enabled=0 WHERE manager_user_id=900001");
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditReads().readTrusted(TENANT, id))
                        .status());
        jdbc.update(
                "UPDATE orbit_business_team_manager SET enabled=1 WHERE manager_user_id=900001");
        jdbc.update(
                "UPDATE orbit_account_scope_directory SET owner_team_id=? WHERE tenant_id=? AND id=?",
                nextTeam,
                TENANT,
                account);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditReads().readTrusted(TENANT, id))
                        .status());
        jdbc.update(
                "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) VALUES(?,900001,?)",
                TENANT,
                nextTeam);
        assertEquals(team, auditReads().readTrusted(TENANT, id).actorTeamId);
        jdbc.update(
                "UPDATE orbit_business_team_manager SET enabled=0 WHERE manager_user_id=900001 AND team_id=?",
                team);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditReads().readTrusted(TENANT, id))
                        .status());
    }

    @Test
    void auditReadRequiresCurrentMenuRoleUnionNotCachedWildcardOrHistoricalRole() {
        scopeSession();
        String id = auditId(scopes().freezeTrusted(TENANT, 1, key(), scopeFilter()));
        businessUser(900001, TENANT, "SUPER_ADMIN");
        auditAs(900001);
        ((LoginUser) SecurityContextHolder.getContext().getAuthentication().getPrincipal())
                .setPermissions(Set.of("*:*:*"));
        assertEquals(
                403,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditReads().readTrusted(TENANT, id))
                        .status());
        grantAuditRoles(900001);
        assertEquals(id, auditReads().readTrusted(TENANT, id).id);
        jdbc.update("UPDATE sys_role SET status='1' WHERE role_id=909042");
        assertEquals(
                403,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditReads().readTrusted(TENANT, id))
                        .status());
        jdbc.update("UPDATE sys_role SET status='0' WHERE role_id=909042");
        assertEquals(id, auditReads().readTrusted(TENANT, id).id);
        jdbc.update("DELETE FROM sys_role_menu WHERE role_id=909042 AND menu_id=31082");
        assertEquals(
                403,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditReads().readTrusted(TENANT, id))
                        .status());
        jdbc.update("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(909042,31082)");
        jdbc.update("UPDATE sys_menu SET status='1' WHERE menu_id=31082");
        try {
            assertEquals(
                    403,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> auditReads().readTrusted(TENANT, id))
                            .status());
        } finally {
            jdbc.update("UPDATE sys_menu SET status='0' WHERE menu_id=31082");
        }
    }

    @Test
    void auditReadUnknownLegacyIdentityNeverBecomesCurrentTeamOwnership() {
        scopeSession();
        String team = businessTeam();
        businessUser(900001, TENANT, "TEAM_ADMIN");
        businessUser(900002, team, "USER");
        String id = key();
        jdbc.update(
                "INSERT INTO orbit_account_scope_audit(id,target_tenant_id,snapshot_id,actor_id,home_tenant_id,data_role,action,request_hash,members_hash,member_count,home_version,target_version) VALUES(?,?,?,900002,?,'USER','SCOPE_FROZEN',?,?,0,1,1)",
                id,
                TENANT,
                key(),
                TENANT,
                "0".repeat(64),
                "1".repeat(64));
        grantAuditRoles(900001);
        grantAuditRoles(900002);
        jdbc.update(
                "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) VALUES(?,900001,?)",
                TENANT,
                team);
        auditAs(900001);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditReads().readTrusted(TENANT, id))
                        .status());
        auditAs(900002);
        assertNull(auditReads().readTrusted(TENANT, id).actorTeamId);
        assertNull(auditReads().readTrusted(TENANT, id).actorSubjectId);
        login();
        scopeSession();
        assertNull(auditReads().readTrusted(TENANT, id).actorTeamId);
    }

    @Test
    void auditReadIdentityMigrationReplaysWithoutBackfillOrNativeMenuChanges() throws Exception {
        scopeSession();
        String id = key();
        jdbc.update(
                "INSERT INTO orbit_account_scope_audit(id,target_tenant_id,snapshot_id,actor_id,home_tenant_id,data_role,action,request_hash,members_hash,member_count,home_version,target_version) VALUES(?,?,?,1,?,'SUPER_ADMIN','SCOPE_FROZEN',?,?,0,1,1)",
                id,
                TENANT,
                key(),
                TENANT,
                "0".repeat(64),
                "1".repeat(64));
        java.nio.file.Path root = java.nio.file.Path.of("").toAbsolutePath();
        while (!java.nio.file.Files.exists(
                root.resolve("sql/orbit/V016__scope_audit_identity.sql"))) root = root.getParent();
        try (var c =
                context.getBean(DataSourceTransactionManager.class)
                        .getDataSource()
                        .getConnection()) {
            for (int i = 0; i < 2; i++)
                ScriptUtils.executeSqlScript(
                        c,
                        new EncodedResource(
                                new FileSystemResource(
                                        root.resolve("sql/orbit/V016__scope_audit_identity.sql")),
                                java.nio.charset.StandardCharsets.UTF_8));
        }
        var entry = auditReads().readTrusted(TENANT, id);
        assertNull(entry.actorTeamId);
        assertNull(entry.actorSubjectId);
        assertEquals(
                nativeMenuCount,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM sys_menu WHERE menu_id<31000", Integer.class));
        assertEquals(
                1,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM sys_menu WHERE menu_id=31082 AND perms='system.audit.read'",
                        Integer.class));
    }

    @Test
    void auditRequestSameTenantAndForeignKeepFirstSuccessAcrossNewHttpIds() {
        scopeSession();
        String csrf = scopeHttp().csrf().get("csrf_token"), body = scopeFilter().toString();
        for (String target : List.of(TENANT, key())) {
            if (!target.equals(TENANT))
                jdbc.update(
                        "INSERT INTO orbit_tenant(id,name) VALUES(?,'request fixture')", target);
            String requestId = key(), idempotency = key();
            var first = scopeHttp().create(idempotency, csrf, target, body, requestId);
            assertEquals(first, scopeHttp().create(idempotency, csrf, target, body, key()));
            assertEquals(
                    requestId,
                    jdbc.queryForObject(
                            "SELECT request_id FROM orbit_account_scope_audit WHERE snapshot_id=?",
                            String.class,
                            first.id()));
            assertEquals(
                    1,
                    jdbc.queryForObject(
                            "SELECT COUNT(*) FROM orbit_account_scope_audit WHERE snapshot_id=?",
                            Integer.class,
                            first.id()));
            assertNotEquals(first.id(), requestId);
            assertNotEquals(idempotency, requestId);
            assertEquals(
                    requestId,
                    auditReads()
                            .readTrusted(
                                    target,
                                    jdbc.queryForObject(
                                            "SELECT id FROM orbit_account_scope_audit WHERE snapshot_id=?",
                                            String.class,
                                            first.id()))
                            .requestId);
        }
    }

    @Test
    void auditRequestInvalidTrustedValueRejectsBeforeAnySnapshotOrEvent() {
        scopeSession();
        int snapshots = count("orbit_account_scope_snapshot"),
                events = count("orbit_account_scope_audit");
        for (String invalid : List.of("", "1-1-1-1-1", "not-uuid", key() + "\n")) {
            assertThrows(
                    IllegalArgumentException.class,
                    () -> scopes().freezeTrusted(TENANT, 1, key(), scopeFilter(), invalid));
            assertThrows(
                    IllegalArgumentException.class,
                    () -> scopes().freezeForSessionTrusted(TENANT, key(), scopeFilter(), invalid));
        }
        assertEquals(snapshots, count("orbit_account_scope_snapshot"));
        assertEquals(events, count("orbit_account_scope_audit"));
    }

    @Test
    void auditRequestMigrationReplaysWithoutForgingInternalOrLegacyOrigin() throws Exception {
        scopeSession();
        var frozen = scopes().freezeTrusted(TENANT, 1, key(), scopeFilter());
        assertNull(auditReads().readTrusted(TENANT, auditId(frozen)).requestId);
        java.nio.file.Path root = java.nio.file.Path.of("").toAbsolutePath();
        while (!java.nio.file.Files.exists(root.resolve("sql/orbit/V017__scope_audit_request.sql")))
            root = root.getParent();
        try (var c =
                context.getBean(DataSourceTransactionManager.class)
                        .getDataSource()
                        .getConnection()) {
            for (int i = 0; i < 2; i++)
                ScriptUtils.executeSqlScript(
                        c,
                        new EncodedResource(
                                new FileSystemResource(
                                        root.resolve("sql/orbit/V017__scope_audit_request.sql")),
                                java.nio.charset.StandardCharsets.UTF_8));
        }
        assertNull(auditReads().readTrusted(TENANT, auditId(frozen)).requestId);
        String csrf = scopeHttp().csrf().get("csrf_token");
        scopeHttp()
                .create(frozen.snapshot().requestKey, csrf, null, scopeFilter().toString(), key());
        assertNull(
                auditReads().readTrusted(TENANT, auditId(frozen)).requestId,
                "重放旧快照不能回填当前HTTP请求为历史首个请求");
        assertEquals(
                nativeMenuCount,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM sys_menu WHERE menu_id<31000", Integer.class));
    }

    private ScopeFreezeAuditQuery auditQueries() {
        return context.getBean(ScopeFreezeAuditQuery.class);
    }

    private void auditQueryFixture(String id, long actor, String subject, String at) {
        jdbc.update(
                "INSERT INTO orbit_account_scope_audit(id,target_tenant_id,snapshot_id,actor_id,home_tenant_id,data_role,action,request_hash,members_hash,member_count,home_version,target_version,actor_subject_id,actor_team_id,created_at) VALUES(?,?,?,?,?,'USER','SCOPE_FROZEN',?,?,0,1,1,?,?,?)",
                id,
                TENANT,
                key(),
                actor,
                TENANT,
                "0".repeat(64),
                "1".repeat(64),
                subject,
                TENANT,
                java.sql.Timestamp.valueOf(at));
    }

    private void auditQueryFixtures(int count, long actor, String subject) {
        for (int i = 0; i < count; i++)
            auditQueryFixture(key(), actor, subject, "2026-11-06 12:00:00.123");
    }

    @Test
    void auditQueryStableTimestampUuidPagesRetainCutoffAndUnknownFields() {
        scopeSession();
        auditQueryFixtures(45, 1, TENANT);
        var first = auditQueries().scanTrusted(TENANT, null, 20, null);
        assertEquals(20, first.entries().size());
        assertEquals(20, first.scanned());
        assertNotNull(first.continuation());
        assertEquals("ScopeAuditBatch[REDACTED]", first.toString());
        assertNull(first.entries().getFirst().requestId);
        assertFalse(first.continuation().contains(first.entries().getLast().id));
        jdbc.update(
                "INSERT INTO orbit_account_scope_audit(id,target_tenant_id,snapshot_id,actor_id,home_tenant_id,data_role,action,request_hash,members_hash,member_count,home_version,target_version,created_at) VALUES(?,?,?,1,?,'USER','SCOPE_FROZEN',?,?,0,1,1,?)",
                key(),
                TENANT,
                key(),
                TENANT,
                "0".repeat(64),
                "1".repeat(64),
                java.sql.Timestamp.from(first.cutoff().plusMillis(1)));
        List<String> ids = new ArrayList<>(first.entries().stream().map(e -> e.id).toList());
        var next = auditQueries().scanTrusted(TENANT, null, 20, first.continuation());
        assertEquals(first.cutoff(), next.cutoff());
        assertEquals(20, next.entries().size());
        ids.addAll(next.entries().stream().map(e -> e.id).toList());
        var last = auditQueries().scanTrusted(TENANT, null, 20, next.continuation());
        assertEquals(5, last.entries().size());
        assertNull(last.continuation());
        ids.addAll(last.entries().stream().map(e -> e.id).toList());
        assertEquals(45, new HashSet<>(ids).size());
        assertEquals(ids.stream().sorted(Comparator.reverseOrder()).toList(), ids);
    }

    @Test
    void auditQueryFiltersUseLiteralActionExactHistoricalSubjectAndInclusiveUtcDays() {
        scopeSession();
        String other = key();
        auditQueryFixture(key(), 1, TENANT, "2026-11-05 23:59:59.999");
        auditQueryFixture(key(), 1, TENANT, "2026-11-06 00:00:00.000");
        auditQueryFixture(key(), 1, TENANT, "2026-11-06 23:59:59.999");
        auditQueryFixture(key(), 1, other, "2026-11-06 12:00:00.000");
        auditQueryFixture(key(), 1, TENANT, "2026-11-07 00:00:00.000");
        var filter =
                new ScopeFreezeAuditQuery.Filter(
                        "  SCOPE  ", TENANT.toUpperCase(Locale.ROOT), "2026-11-06", "2026-11-06");
        assertEquals(2, auditQueries().scanTrusted(TENANT, filter, 20, null).entries().size());
        for (String literal : List.of("%", "SCOPE_%", "!", "' OR 1=1 --"))
            assertTrue(
                    auditQueries()
                            .scanTrusted(
                                    TENANT,
                                    new ScopeFreezeAuditQuery.Filter(literal, null, null, null),
                                    20,
                                    null)
                            .entries()
                            .isEmpty());
        assertEquals(
                5,
                auditQueries()
                        .scanTrusted(
                                TENANT,
                                new ScopeFreezeAuditQuery.Filter("_", null, null, null),
                                20,
                                null)
                        .entries()
                        .size(),
                "代码本身含字面下划线，应正常匹配，不等于允许通配符");
        for (var invalid :
                List.of(
                        new ScopeFreezeAuditQuery.Filter("x".repeat(101), null, null, null),
                        new ScopeFreezeAuditQuery.Filter("x\n", null, null, null),
                        new ScopeFreezeAuditQuery.Filter(null, "not-uuid", null, null),
                        new ScopeFreezeAuditQuery.Filter(null, null, "2026-02-30", null),
                        new ScopeFreezeAuditQuery.Filter(null, null, "2026-11-06", "2026-11-05"),
                        new ScopeFreezeAuditQuery.Filter(null, null, null, "2999-01-01")))
            assertEquals(
                    422,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> auditQueries().scanTrusted(TENANT, invalid, 20, null))
                            .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditQueries().scanTrusted(TENANT, null, 21, null))
                        .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        auditQueries()
                                                .scanTrusted(TENANT, null, 20, "x".repeat(2049)))
                        .status());
    }

    @Test
    void auditQueryHiddenCandidatesHaveBoundedEmptyContinuationWithoutLeakingEvents() {
        scopeSession();
        String subject = businessUser(900001, TENANT, "USER");
        grantAuditRoles(900001);
        for (int i = 1; i <= 203; i++)
            auditQueryFixture(
                    "00000000-0000-4000-8000-" + String.format("%012d", i),
                    i == 1 ? 900001 : 1,
                    i == 1 ? subject : TENANT,
                    "2026-11-06 12:00:00.000");
        auditAs(900001);
        var first = auditQueries().scanTrusted(TENANT, null, 20, null);
        assertEquals(200, first.scanned());
        assertTrue(first.entries().isEmpty());
        assertNotNull(first.continuation());
        var last = auditQueries().scanTrusted(TENANT, null, 20, first.continuation());
        assertEquals(3, last.scanned());
        assertEquals(1, last.entries().size());
        assertEquals(900001, last.entries().getFirst().actorId);
        assertNull(last.continuation());
    }

    @Test
    void auditQueryCursorRejectsTamperContextIdentityAndEitherTenantVersionChanges() {
        scopeSession();
        auditQueryFixtures(21, 1, TENANT);
        String cursor = auditQueries().scanTrusted(TENANT, null, 20, null).continuation();
        assertNotNull(cursor);
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        auditQueries()
                                                .scanTrusted(
                                                        TENANT,
                                                        null,
                                                        20,
                                                        "v2" + cursor.substring(2)))
                        .status());
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditQueries().scanTrusted(TENANT, null, 50, cursor))
                        .status());
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        auditQueries()
                                                .scanTrusted(
                                                        TENANT,
                                                        new ScopeFreezeAuditQuery.Filter(
                                                                "SCOPE", null, null, null),
                                                        20,
                                                        cursor))
                        .status());
        String target = key();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'audit query target')", target);
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditQueries().scanTrusted(target, null, 20, cursor))
                        .status());
        businessUser(900001, TENANT, "SUPER_ADMIN");
        grantAuditRoles(900001);
        auditAs(900001);
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditQueries().scanTrusted(TENANT, null, 20, cursor))
                        .status());
        login();
        scopeSession();
        String fresh = auditQueries().scanTrusted(TENANT, null, 20, null).continuation();
        jdbc.update("UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=?", TENANT);
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditQueries().scanTrusted(TENANT, null, 20, fresh))
                        .status());
        jdbc.update("UPDATE sys_menu SET status='1' WHERE menu_id=31082");
        try {
            assertEquals(
                    403,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> auditQueries().scanTrusted(TENANT, null, 20, null))
                            .status());
        } finally {
            jdbc.update("UPDATE sys_menu SET status='0' WHERE menu_id=31082");
        }
    }

    @Test
    void auditQueryTeamHistoryRequiresCurrentManagementAndOriginalObjectVisibility() {
        scopeSession();
        businessUser(900001, TENANT, "TEAM_ADMIN");
        String team = businessTeam(), owner = businessUser(900002, team, "USER");
        directoryAccount("200000000000000001", "team audit query", owner, team);
        var frozen = scopes().freezeTrusted(TENANT, 900002, key(), scopeFilter());
        // 使用确定的早期UTC时间避免测试依赖同一毫秒写入截止边界。
        jdbc.update(
                "UPDATE orbit_account_scope_audit SET created_at='2026-11-06 12:00:00' WHERE snapshot_id=?",
                frozen.snapshot().id);
        grantAuditRoles(900001);
        jdbc.update(
                "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) VALUES(?,900001,?)",
                TENANT,
                team);
        auditAs(900001);
        assertEquals(1, auditQueries().scanTrusted(TENANT, null, 20, null).entries().size());
        jdbc.update(
                "UPDATE orbit_business_team_manager SET enabled=0 WHERE manager_user_id=900001");
        assertTrue(auditQueries().scanTrusted(TENANT, null, 20, null).entries().isEmpty());
        jdbc.update("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=900001");
        assertTrue(auditQueries().scanTrusted(TENANT, null, 20, null).entries().isEmpty());
    }

    @Test
    void auditQueryForeignCursorRechecksEachClockAndTargetEnablement() {
        scopeSession();
        String target = key();
        jdbc.update(
                "INSERT INTO orbit_tenant(id,name) VALUES(?,'foreign audit query fixture')",
                target);
        auditQueryFixtures(21, 1, TENANT);
        jdbc.update("UPDATE orbit_account_scope_audit SET target_tenant_id=?", target);
        for (String changed : List.of(TENANT, target)) {
            var batch = auditQueries().scanTrusted(target, null, 20, null);
            assertEquals(20, batch.entries().size());
            assertNotNull(batch.continuation());
            assertTrue(
                    batch.entries().stream()
                            .allMatch(
                                    e ->
                                            target.equals(e.targetTenantId)
                                                    && TENANT.equals(e.homeTenantId)));
            jdbc.update(
                    "UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=?", changed);
            assertEquals(
                    409,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () ->
                                            auditQueries()
                                                    .scanTrusted(
                                                            target, null, 20, batch.continuation()))
                            .status());
        }
        jdbc.update("UPDATE orbit_tenant SET enabled=0 WHERE id=?", target);
        try {
            assertEquals(
                    404,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> auditQueries().scanTrusted(target, null, 20, null))
                            .status());
        } finally {
            jdbc.update("UPDATE orbit_tenant SET enabled=1 WHERE id=?", target);
        }
    }

    @Test
    void auditQueryIndexMigrationReplaysWithoutChangingHistoryOrNativeMenus() throws Exception {
        scopeSession();
        auditQueryFixtures(2, 1, TENANT);
        java.nio.file.Path root = java.nio.file.Path.of("").toAbsolutePath();
        while (!java.nio.file.Files.exists(
                root.resolve("sql/orbit/V018__scope_audit_query_indexes.sql")))
            root = root.getParent();
        try (var c =
                context.getBean(DataSourceTransactionManager.class)
                        .getDataSource()
                        .getConnection()) {
            for (int i = 0; i < 2; i++)
                ScriptUtils.executeSqlScript(
                        c,
                        new EncodedResource(
                                new FileSystemResource(
                                        root.resolve(
                                                "sql/orbit/V018__scope_audit_query_indexes.sql")),
                                java.nio.charset.StandardCharsets.UTF_8));
        }
        assertEquals(2, count("orbit_account_scope_audit"));
        assertEquals(
                2,
                jdbc.queryForObject(
                        "SELECT COUNT(DISTINCT index_name) FROM information_schema.statistics WHERE table_schema=? AND table_name='orbit_account_scope_audit' AND index_name IN('idx_scope_audit_target_page','idx_scope_audit_subject')",
                        Integer.class,
                        database));
        assertEquals(
                nativeMenuCount,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM sys_menu WHERE menu_id<31000", Integer.class));
    }

    private AuditEventsService auditEvents() {
        return context.getBean(AuditEventsService.class);
    }

    private void auditPublicFixtures(int count) {
        auditQueryFixtures(count, 1, TENANT);
        jdbc.update("UPDATE orbit_account_scope_audit SET request_id=UUID()");
    }

    private String auditForeignRows(int count) {
        String target = key();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'public audit target')", target);
        for (String id :
                jdbc.queryForList(
                        "SELECT id FROM orbit_account_scope_audit ORDER BY id LIMIT " + count,
                        String.class))
            jdbc.update(
                    "UPDATE orbit_account_scope_audit SET target_tenant_id=? WHERE id=?",
                    target,
                    id);
        return target;
    }

    @Test
    void auditPublicMergesEveryEnabledTenantWithStableGlobalPages() {
        scopeSession();
        auditPublicFixtures(45);
        String target = auditForeignRows(24);
        var first = auditEvents().pageTrusted(Map.of("page_size", List.of("20")));
        assertEquals(20, first.items().size());
        assertNotNull(first.nextCursor());
        var ids = new ArrayList<>(first.items().stream().map(AuditEventsService.Item::id).toList());
        Set<String> targets =
                new HashSet<>(
                        first.items().stream().map(AuditEventsService.Item::tenantId).toList());
        String cursor = first.nextCursor();
        for (int expected : List.of(20, 5)) {
            var page =
                    auditEvents()
                            .pageTrusted(
                                    Map.of("page_size", List.of("20"), "cursor", List.of(cursor)));
            assertEquals(expected, page.items().size());
            assertEquals(first.dataAsOf(), page.dataAsOf());
            ids.addAll(page.items().stream().map(AuditEventsService.Item::id).toList());
            targets.addAll(page.items().stream().map(AuditEventsService.Item::tenantId).toList());
            cursor = page.nextCursor();
        }
        assertNull(cursor);
        assertEquals(45, new HashSet<>(ids).size());
        assertEquals(ids.stream().sorted(Comparator.reverseOrder()).toList(), ids);
        assertEquals(Set.of(TENANT, target), targets);
        assertEquals("AuditPage[REDACTED]", first.toString());
    }

    @Test
    void auditPublicCurrentUserCannotReadOtherActorsOrOtherTenants() {
        scopeSession();
        String subject = businessUser(900001, TENANT, "USER");
        grantAuditRoles(900001);
        jdbc.update("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(909042,31083)");
        auditPublicFixtures(3);
        auditForeignRows(1);
        auditQueryFixture(key(), 900001, subject, "2026-11-06 12:00:00.123");
        jdbc.update(
                "UPDATE orbit_account_scope_audit SET request_id=UUID() WHERE request_id IS NULL");
        auditAs(900001);
        var page = auditEvents().pageTrusted(Map.of());
        assertEquals(1, page.items().size());
        assertEquals(subject, page.items().getFirst().actorUserId());
        assertEquals(TENANT, page.items().getFirst().tenantId());
    }

    @Test
    void auditPublicPageAndActionMenuAreBothCurrentRequirements() {
        scopeSession();
        auditPublicFixtures(1);
        for (long menu : List.of(31083L, 31082L, 31080L, 31000L)) {
            jdbc.update("UPDATE sys_menu SET status='1' WHERE menu_id=?", menu);
            try {
                assertEquals(
                        403,
                        assertThrows(
                                        AccountScopeService.Failure.class,
                                        () -> auditEvents().pageTrusted(Map.of()))
                                .status());
            } finally {
                jdbc.update("UPDATE sys_menu SET status='0' WHERE menu_id=?", menu);
            }
        }
        assertEquals(1, auditEvents().pageTrusted(Map.of()).items().size());
    }

    @Test
    void auditPublicCursorBindsAllVersionsTenantRosterFiltersActorAndSize() {
        scopeSession();
        auditPublicFixtures(25);
        String target = auditForeignRows(4);
        String cursor = auditEvents().pageTrusted(Map.of("page_size", List.of("20"))).nextCursor();
        assertNotNull(cursor);
        for (var query :
                List.of(
                        Map.of("page_size", List.of("50"), "cursor", List.of(cursor)),
                        Map.of(
                                "page_size",
                                List.of("20"),
                                "q",
                                List.of("SCOPE"),
                                "cursor",
                                List.of(cursor)),
                        Map.of(
                                "page_size",
                                List.of("20"),
                                "cursor",
                                List.of("v2" + cursor.substring(2)))))
            assertEquals(
                    409,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> auditEvents().pageTrusted(query))
                            .status());
        jdbc.update("UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=?", target);
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        auditEvents()
                                                .pageTrusted(
                                                        Map.of(
                                                                "page_size",
                                                                List.of("20"),
                                                                "cursor",
                                                                List.of(cursor))))
                        .status());
        String fresh = auditEvents().pageTrusted(Map.of("page_size", List.of("20"))).nextCursor();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'new enabled target')", key());
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        auditEvents()
                                                .pageTrusted(
                                                        Map.of(
                                                                "page_size",
                                                                List.of("20"),
                                                                "cursor",
                                                                List.of(fresh))))
                        .status());
        String identityCursor =
                auditEvents().pageTrusted(Map.of("page_size", List.of("20"))).nextCursor();
        businessUser(900001, TENANT, "SUPER_ADMIN");
        grantAuditRoles(900001);
        jdbc.update("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(909042,31083)");
        auditAs(900001);
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        auditEvents()
                                                .pageTrusted(
                                                        Map.of(
                                                                "page_size",
                                                                List.of("20"),
                                                                "cursor",
                                                                List.of(identityCursor))))
                        .status());
    }

    @Test
    void auditPublicUnknownLegacyIdentityFailsExplicitlyInsteadOfHidingOrInventing() {
        scopeSession();
        auditQueryFixtures(1, 1, TENANT);
        int before = count("orbit_account_scope_audit");
        var failure =
                assertThrows(
                        AccountScopeService.Failure.class,
                        () -> auditEvents().pageTrusted(Map.of()));
        assertEquals(503, failure.status());
        assertEquals("AUDIT_HISTORY_INCOMPLETE", failure.code());
        assertEquals(before, count("orbit_account_scope_audit"));
        jdbc.update("UPDATE orbit_account_scope_audit SET request_id=UUID(),actor_subject_id=NULL");
        assertEquals(
                "AUDIT_HISTORY_INCOMPLETE",
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> auditEvents().pageTrusted(Map.of()))
                        .code());
    }

    @Test
    void auditPublicProjectionMatchesNineContractFieldsWithoutInternalHashes() throws Exception {
        scopeSession();
        auditPublicFixtures(1);
        var page = auditEvents().pageTrusted(Map.of());
        var item = page.items().getFirst();
        assertEquals("AuditItem[REDACTED]", item.toString());
        var json = new ObjectMapper().findAndRegisterModules().valueToTree(page);
        Set<String> fields = new HashSet<>();
        json.fieldNames().forEachRemaining(fields::add);
        assertEquals(Set.of("items", "next_cursor", "data_as_of", "scope_version"), fields);
        Set<String> itemFields = new HashSet<>();
        json.path("items").get(0).fieldNames().forEachRemaining(itemFields::add);
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
                itemFields);
        assertNull(item.evidenceRef());
        assertEquals("冻结账户范围", item.reason());
        for (String id :
                List.of(
                        item.id(),
                        item.actorUserId(),
                        item.targetId(),
                        item.tenantId(),
                        item.requestId()))
            assertEquals(id, java.util.UUID.fromString(id).toString());
    }

    @Test
    void auditPublicUsesHomeClockAndRejectsUnsupportedOrIdentityQueryFields() {
        scopeSession();
        auditPublicFixtures(1);
        String target = auditForeignRows(1);
        jdbc.update(
                "UPDATE orbit_scope_version SET version=version+100000 WHERE tenant_id=?", target);
        long home = context.getBean(AccountScopeMapper.class).scopeVersion(TENANT);
        assertEquals(home, auditEvents().pageTrusted(Map.of()).scopeVersion());
        assertEquals(
                400,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        auditEvents()
                                                .pageTrusted(Map.of("tenant_id", List.of(target))))
                        .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        auditEvents()
                                                .pageTrusted(Map.of("status", List.of("ACTIVE"))))
                        .status());
    }

    @Test
    void auditPublicEmptyAuthorizedBatchRetainsSafeContinuationForHiddenCandidates() {
        scopeSession();
        String subject = businessUser(900001, TENANT, "USER");
        grantAuditRoles(900001);
        jdbc.update("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(909042,31083)");
        for (int i = 1; i <= 202; i++)
            auditQueryFixture(
                    "00000000-0000-4000-8000-" + String.format("%012d", i),
                    i == 1 ? 900001 : 1,
                    i == 1 ? subject : TENANT,
                    "2026-11-06 12:00:00.000");
        jdbc.update("UPDATE orbit_account_scope_audit SET request_id=UUID()");
        auditAs(900001);
        var first = auditEvents().pageTrusted(Map.of("page_size", List.of("20")));
        assertTrue(first.items().isEmpty());
        assertNotNull(first.nextCursor());
        var last =
                auditEvents()
                        .pageTrusted(
                                Map.of(
                                        "page_size",
                                        List.of("20"),
                                        "cursor",
                                        List.of(first.nextCursor())));
        assertEquals(1, last.items().size());
        assertNull(last.nextCursor());
    }

    @Test
    void auditPublicMissingAnyEnabledTenantClockFailsClosedWithoutRepairingDatabase() {
        scopeSession();
        auditPublicFixtures(1);
        String target = auditForeignRows(1);
        long restore = context.getBean(AccountScopeMapper.class).scopeVersion(target);
        jdbc.update("DELETE FROM orbit_scope_version WHERE tenant_id=?", target);
        try {
            assertEquals(
                    503,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> auditEvents().pageTrusted(Map.of()))
                            .status());
            assertEquals(
                    0,
                    jdbc.queryForObject(
                            "SELECT COUNT(*) FROM orbit_scope_version WHERE tenant_id=?",
                            Integer.class,
                            target));
        } finally {
            jdbc.update(
                    "INSERT INTO orbit_scope_version(tenant_id,version) VALUES(?,?)",
                    target,
                    restore);
        }
    }

    private ScopeHttpService scopeHttp() {
        return context.getBean(ScopeHttpService.class);
    }

    private void scopeSession() {
        ((LoginUser) SecurityContextHolder.getContext().getAuthentication().getPrincipal())
                .setToken("fixture_scope_session_0123456789");
    }

    @Test
    void scopeHttpAsciiKeysAndCsrfCreateReplayAreAtomic() {
        scopeSession();
        String csrf = scopeHttp().csrf().get("csrf_token"), body = scopeFilter().toString();
        for (String key :
                List.of(
                        "printable key 001",
                        "K".repeat(128),
                        "CaseSensitiveKey",
                        "casesensitivekey",
                        "space key value ")) {
            var first = scopeHttp().create(key, csrf, null, body);
            assertEquals(first, scopeHttp().create(key, csrf, null, body));
            assertEquals(0, first.count());
            assertEquals(64, first.hash().length());
        }
        assertEquals(5, count("orbit_account_scope_snapshot"));
        assertEquals(
                400,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopeHttp().create("x".repeat(129), csrf, null, body))
                        .status());
        assertEquals(
                400,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopeHttp().create("short", csrf, null, body))
                        .status());
        assertEquals(
                400,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopeHttp().create("non_ascii_key_中文", csrf, null, body))
                        .status());
        var changed = scopeFilter();
        changed.path("filter").deepCopy();
        ((com.fasterxml.jackson.databind.node.ObjectNode) changed.path("filter"))
                .put("q", "changed");
        assertEquals(
                "IDEMPOTENCY_CONFLICT",
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        scopeHttp()
                                                .create(
                                                        "printable key 001",
                                                        csrf,
                                                        null,
                                                        changed.toString()))
                        .code());
        assertEquals(5, count("orbit_account_scope_snapshot"));
    }

    @Test
    void scopeHttpCsrfRejectsDifferentSessionAndMissingOrTamperedToken() {
        scopeSession();
        String csrf = scopeHttp().csrf().get("csrf_token"), body = scopeFilter().toString();
        for (String token :
                new String[] {null, "bad-token-0123456789", csrf.substring(0, csrf.length() - 8)})
            assertEquals(
                    "CSRF_INVALID",
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> scopeHttp().create(key(), token, null, body))
                            .code());
        ((LoginUser) SecurityContextHolder.getContext().getAuthentication().getPrincipal())
                .setToken("different_scope_session_0123456789");
        assertEquals(
                403,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopeHttp().create(key(), csrf, null, body))
                        .status());
        assertEquals(0, count("orbit_account_scope_snapshot"));
    }

    @Test
    void scopeHttpCurrentMenuGrantCannotBeBypassedByCachedWildcard() {
        scopeSession();
        scopeHttp().csrf();
        jdbc.update("UPDATE sys_menu SET status='1' WHERE menu_id=31010");
        try {
            assertEquals(
                    403,
                    assertThrows(AccountScopeService.Failure.class, () -> scopeHttp().csrf())
                            .status());
        } finally {
            jdbc.update("UPDATE sys_menu SET status='0' WHERE menu_id=31010");
        }
        jdbc.update("UPDATE sys_menu SET status='1' WHERE menu_id=31011");
        try {
            assertEquals(
                    403,
                    assertThrows(AccountScopeService.Failure.class, () -> scopeHttp().csrf())
                            .status());
        } finally {
            jdbc.update("UPDATE sys_menu SET status='0' WHERE menu_id=31011");
        }
        businessUser(900001, TENANT, "USER");
        LoginUser principal =
                (LoginUser) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        principal.setUserId(900001L);
        principal.setPermissions(Set.of("*:*:*"));
        assertEquals(
                403,
                assertThrows(AccountScopeService.Failure.class, () -> scopeHttp().csrf()).status());
        jdbc.update("INSERT INTO sys_user_role(user_id,role_id) VALUES(900001,2)");
        jdbc.update("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(2,31000),(2,31010)");
        try {
            assertEquals(
                    403,
                    assertThrows(AccountScopeService.Failure.class, () -> scopeHttp().csrf())
                            .status());
            jdbc.update("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(2,31011)");
            assertNotNull(scopeHttp().csrf().get("csrf_token"));
            jdbc.update("DELETE FROM sys_role_menu WHERE role_id=2 AND menu_id=31011");
            assertEquals(
                    403,
                    assertThrows(AccountScopeService.Failure.class, () -> scopeHttp().csrf())
                            .status());
            jdbc.update("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(2,31011)");
            jdbc.update("DELETE FROM sys_role_menu WHERE role_id=2 AND menu_id=31010");
            assertEquals(
                    403,
                    assertThrows(AccountScopeService.Failure.class, () -> scopeHttp().csrf())
                            .status());
        } finally {
            jdbc.update("DELETE FROM sys_user_role WHERE user_id=900001");
            jdbc.update(
                    "DELETE FROM sys_role_menu WHERE role_id=2 AND menu_id IN(31000,31010,31011)");
        }
    }

    /** 功能角色按需求取并集；未分配、停用、删除或撤销的授权不能参加合并。 */
    @Test
    void scopeHttpUnionsAssignedEnabledRolesAndRechecksEveryRevocation() {
        scopeSession();
        businessUser(900001, TENANT, "USER");
        LoginUser principal =
                (LoginUser) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        principal.setUserId(900001L);
        principal.setPermissions(Set.of("*:*:*"));
        jdbc.update(
                "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,status,del_flag) VALUES(900010,'范围父菜单fixture','scope-parent-fixture',1,'0','0'),(900011,'范围页面fixture','scope-page-fixture',2,'0','0'),(900012,'范围动作fixture','scope-action-fixture',3,'0','0'),(900013,'未分配fixture','scope-unassigned-fixture',4,'0','0')");
        try {
            jdbc.update(
                    "INSERT INTO sys_user_role(user_id,role_id) VALUES(900001,900010),(900001,900011),(900001,900012)");
            jdbc.update(
                    "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(900010,31000),(900011,31011),(900012,31010),(900013,31010)");
            assertNotNull(scopeHttp().csrf().get("csrf_token"), "父菜单、页面和动作允许来自不同有效功能角色");
            jdbc.update("UPDATE sys_role SET status='1' WHERE role_id=900012");
            assertEquals(
                    403,
                    assertThrows(AccountScopeService.Failure.class, () -> scopeHttp().csrf())
                            .status());
            jdbc.update("UPDATE sys_role SET status='0',del_flag='2' WHERE role_id=900012");
            assertEquals(
                    403,
                    assertThrows(AccountScopeService.Failure.class, () -> scopeHttp().csrf())
                            .status());
            jdbc.update("UPDATE sys_role SET del_flag='0' WHERE role_id=900012");
            assertNotNull(scopeHttp().csrf().get("csrf_token"));
            jdbc.update("DELETE FROM sys_user_role WHERE user_id=900001 AND role_id=900012");
            assertEquals(
                    403,
                    assertThrows(AccountScopeService.Failure.class, () -> scopeHttp().csrf())
                            .status(),
                    "未分配角色上的相同动作不补权");
            jdbc.update("INSERT INTO sys_user_role(user_id,role_id) VALUES(900001,900012)");
            assertNotNull(scopeHttp().csrf().get("csrf_token"));
            jdbc.update("DELETE FROM sys_role_menu WHERE role_id=900011 AND menu_id=31011");
            assertEquals(
                    403,
                    assertThrows(AccountScopeService.Failure.class, () -> scopeHttp().csrf())
                            .status());
            jdbc.update("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(900011,31011)");
            assertNotNull(scopeHttp().csrf().get("csrf_token"));
            jdbc.update("DELETE FROM sys_role_menu WHERE role_id=900010 AND menu_id=31000");
            assertEquals(
                    403,
                    assertThrows(AccountScopeService.Failure.class, () -> scopeHttp().csrf())
                            .status());
        } finally {
            jdbc.update("DELETE FROM sys_role_menu WHERE role_id IN(900010,900011,900012,900013)");
            jdbc.update(
                    "DELETE FROM sys_user_role WHERE user_id=900001 AND role_id IN(900010,900011,900012,900013)");
            jdbc.update("DELETE FROM sys_role WHERE role_id IN(900010,900011,900012,900013)");
        }
    }

    @Test
    void scopeHttpUnknownDuplicateMalformedAndSemanticInputsNeverCreateRows() {
        scopeSession();
        String csrf = scopeHttp().csrf().get("csrf_token");
        for (String body :
                List.of(
                        "{}",
                        "{bad}",
                        scopeFilter() + " {}",
                        scopeFilter()
                                .toString()
                                .replace(
                                        "\"mode\":\"FILTER\"",
                                        "\"mode\":\"FILTER\",\"mode\":\"FILTER\""),
                        scopeFilter()
                                .toString()
                                .replace("\"q\":\"\"", "\"q\":\"\",\"unknown\":true")))
            assertEquals(
                    400,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> scopeHttp().create(key(), csrf, null, body))
                            .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        scopeHttp()
                                                .create(
                                                        key(),
                                                        csrf,
                                                        null,
                                                        scopeFilter()
                                                                .toString()
                                                                .replace("FILTER", "INVALID")))
                        .status());
        assertEquals(0, count("orbit_account_scope_snapshot"));
    }

    @Test
    void scopeHttpTargetTenantDoesNotBroadenDataAuthorization() {
        scopeSession();
        String csrf = scopeHttp().csrf().get("csrf_token"), body = scopeFilter().toString();
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopeHttp().create(key(), csrf, key(), body))
                        .status());
        assertEquals(
                400,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopeHttp().create(key(), csrf, "invalid", body))
                        .status());
        assertNotNull(scopeHttp().create(key(), csrf, TENANT, body));
        jdbc.update("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1");
        assertEquals(
                403,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopeHttp().create(key(), csrf, TENANT, body))
                        .status());
    }

    @Test
    void scopeMembersExistingRepeatableReadSnapshotCannotReturnOldVisibility() throws Exception {
        var initial = pageFixture(45, TENANT, 1);
        try (var writer = Executors.newSingleThreadExecutor()) {
            var committed =
                    transaction()
                            .execute(
                                    status -> {
                                        // 先建立旧MVCC视图，再由另一事务冻结新范围；锁定头、成员和权限须读取同一当前状态。
                                        assertEquals(1, count("orbit_account_scope_snapshot"));
                                        AccountScopeService.Frozen fresh;
                                        try {
                                            fresh =
                                                    writer.submit(
                                                                    () ->
                                                                            scopes().freezeTrusted(
                                                                                            TENANT,
                                                                                            1,
                                                                                            key(),
                                                                                            scopeFilter()))
                                                            .get(15, TimeUnit.SECONDS);
                                        } catch (Exception error) {
                                            throw new IllegalStateException("独立冻结事务失败", error);
                                        }
                                        assertEquals(
                                                20,
                                                pages().pageTrusted(
                                                                TENANT,
                                                                1,
                                                                fresh.snapshot().id,
                                                                null,
                                                                20,
                                                                null)
                                                        .items()
                                                        .size());
                                        return fresh;
                                    });
            transaction()
                    .executeWithoutResult(
                            status -> {
                                assertEquals(45, count("orbit_account_scope_directory"));
                                try {
                                    writer.submit(
                                                    () ->
                                                            directory()
                                                                    .publishTrusted(
                                                                            TENANT,
                                                                            1,
                                                                            2,
                                                                            List.of(),
                                                                            List.of(
                                                                                    initial.members()
                                                                                            .getLast()
                                                                                            .accountId)))
                                            .get(15, TimeUnit.SECONDS);
                                } catch (Exception error) {
                                    throw new IllegalStateException("独立目录事务失败", error);
                                }
                                // 不能用旧视图将对象已撤权误判为一般版本变化，仍应404。
                                assertEquals(
                                        404,
                                        assertThrows(
                                                        AccountScopeService.Failure.class,
                                                        () ->
                                                                pages().pageTrusted(
                                                                                TENANT,
                                                                                1,
                                                                                committed.snapshot()
                                                                                        .id,
                                                                                null,
                                                                                20,
                                                                                null))
                                                .status());
                                // 被测服务按预期标记回滚，夹具也明确回滚，不尝试提交已回滚事务。
                                status.setRollbackOnly();
                            });
        }
    }

    @Test
    void scopeMembersIdentityChangesAndProtocolUpgradeInvalidateVersionProof() throws Exception {
        var frozen = pageFixture(45, TENANT, 1);
        var row = frozen.members().getFirst();
        String cursor =
                pages().pageTrusted(TENANT, 1, frozen.snapshot().id, null, 20, null).nextCursor();
        long before = scopeVersion();
        directory()
                .publishTrusted(
                        TENANT,
                        1,
                        2,
                        List.of(
                                directoryEntry(
                                        row.accountId,
                                        "9999999999999999999999999999999999",
                                        row.name,
                                        TENANT,
                                        TENANT)),
                        List.of());
        assertEquals(before + 1, scopeVersion());
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageTrusted(
                                                        TENANT,
                                                        1,
                                                        frozen.snapshot().id,
                                                        null,
                                                        20,
                                                        cursor))
                        .status());
        var fresh = scopes().freezeTrusted(TENANT, 1, key(), scopeFilter());
        jdbc.update(
                "UPDATE orbit_account_scope_directory SET id=? WHERE tenant_id=? AND id=?",
                key(),
                TENANT,
                row.accountId);
        assertEquals(before + 2, scopeVersion());
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageTrusted(
                                                        TENANT,
                                                        1,
                                                        fresh.snapshot().id,
                                                        null,
                                                        20,
                                                        null))
                        .status());
        Path root = Path.of("").toAbsolutePath();
        while (!java.nio.file.Files.exists(
                root.resolve("sql/orbit/V010__scope_directory_identity_versions.sql")))
            root = root.getParent();
        long priorReplay = scopeVersion();
        try (var connection = jdbc.getDataSource().getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve(
                                            "sql/orbit/V010__scope_directory_identity_versions.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        assertEquals(priorReplay + 1, scopeVersion());
    }

    private AccountScopeService.Frozen pageFixture(int count, String owner, long actor) {
        List<AccountDirectoryPublisher.Entry> rows = new ArrayList<>();
        for (int i = 0; i < count; i++)
            rows.add(
                    directoryEntry(
                            key(),
                            "12345678901234567890" + i,
                            i < 25 ? "literal%_" + i : "plain" + i,
                            owner,
                            TENANT));
        if (!rows.isEmpty()) directory().publishTrusted(TENANT, 1, 1, rows, List.of());
        return scopes().freezeTrusted(TENANT, actor, key(), scopeFilter());
    }

    @Test
    void scopeMembersKeysetPaginationIsCompleteStableAndMatchesWireFields() {
        var frozen = pageFixture(45, TENANT, 1);
        String cursor = null;
        List<String> ids = new ArrayList<>();
        for (int expected : List.of(20, 20, 5)) {
            var page = pages().pageTrusted(TENANT, 1, frozen.snapshot().id, null, 20, cursor);
            assertEquals(expected, page.items().size());
            assertEquals(frozen.snapshot().createdAt, page.dataAsOf());
            assertEquals(frozen.snapshot().scopeVersion, page.scopeVersion());
            ids.addAll(page.items().stream().map(ScopeMemberPager.Item::accountId).toList());
            cursor = page.nextCursor();
            var wire = context.getBean(ObjectMapper.class).valueToTree(page);
            Set<String> fields = new HashSet<>();
            wire.fieldNames().forEachRemaining(fields::add);
            assertEquals(Set.of("items", "next_cursor", "data_as_of", "scope_version"), fields);
            Set<String> itemFields = new HashSet<>();
            wire.path("items").get(0).fieldNames().forEachRemaining(itemFields::add);
            assertEquals(Set.of("account_id", "external_id", "name"), itemFields);
            if (expected == 20) {
                assertNotNull(cursor);
                assertTrue(cursor.length() <= 2048);
            }
        }
        assertNull(cursor);
        assertEquals(frozen.members().stream().map(row -> row.accountId).toList(), ids);
        assertEquals(45, new HashSet<>(ids).size());
    }

    @Test
    void scopeMembersSearchEscapesWildcardsAndPreservesExternalIdStrings() {
        var frozen = pageFixture(45, TENANT, 1);
        var first = pages().pageTrusted(TENANT, 1, frozen.snapshot().id, "%_", 20, null);
        assertEquals(20, first.items().size());
        var last =
                pages().pageTrusted(TENANT, 1, frozen.snapshot().id, "%_", 20, first.nextCursor());
        assertEquals(5, last.items().size());
        assertNull(last.nextCursor());
        assertTrue(first.items().stream().allMatch(row -> row.name().contains("%_")));
        String external = frozen.members().getFirst().externalId;
        var exact = pages().pageTrusted(TENANT, 1, frozen.snapshot().id, external, 50, null);
        assertEquals(1, exact.items().size());
        assertEquals(external, exact.items().getFirst().externalId());
    }

    @Test
    void scopeMembersCursorRejectsTamperingChangedFilterSizeAndSnapshot() {
        var frozen = pageFixture(45, TENANT, 1);
        String id = frozen.snapshot().id,
                cursor = pages().pageTrusted(TENANT, 1, id, "", 20, null).nextCursor();
        int at = cursor.length() / 2;
        String changed =
                cursor.substring(0, at)
                        + (cursor.charAt(at) == 'A' ? 'B' : 'A')
                        + cursor.substring(at + 1);
        for (String token :
                List.of(
                        changed,
                        cursor.substring(0, cursor.length() - 8),
                        "invalid",
                        "x".repeat(2049),
                        ""))
            assertEquals(
                    422,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> pages().pageTrusted(TENANT, 1, id, "", 20, token))
                            .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> pages().pageTrusted(TENANT, 1, id, "changed", 20, cursor))
                        .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> pages().pageTrusted(TENANT, 1, id, "", 50, cursor))
                        .status());
        var other = scopes().freezeTrusted(TENANT, 1, key(), scopeFilter());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageTrusted(
                                                        TENANT,
                                                        1,
                                                        other.snapshot().id,
                                                        "",
                                                        20,
                                                        cursor))
                        .status());
    }

    @Test
    void scopeMembersActorAndTenantBindingCannotBeReusedByAnotherReader() {
        businessUser(900001, TENANT, "SUPER_ADMIN");
        var frozen = pageFixture(45, TENANT, 1);
        String cursor =
                pages().pageTrusted(TENANT, 1, frozen.snapshot().id, null, 20, null).nextCursor();
        var own = scopes().freezeTrusted(TENANT, 900001, key(), scopeFilter());
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageTrusted(
                                                        TENANT,
                                                        900001,
                                                        frozen.snapshot().id,
                                                        null,
                                                        20,
                                                        cursor))
                        .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageTrusted(
                                                        TENANT,
                                                        900001,
                                                        own.snapshot().id,
                                                        null,
                                                        20,
                                                        cursor))
                        .status());
        assertEquals(
                404,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        pages().pageTrusted(
                                                        key(),
                                                        1,
                                                        frozen.snapshot().id,
                                                        null,
                                                        20,
                                                        cursor))
                        .status());
    }

    @Test
    void scopeMembersOffPageTransferRevokesEntireScopeBeforeReturningAnyPage() {
        String owner = businessUser(900001, TENANT, "USER"),
                other = businessUser(900002, TENANT, "USER");
        var frozen = pageFixture(45, owner, 900001);
        String cursor =
                pages().pageTrusted(TENANT, 900001, frozen.snapshot().id, null, 20, null)
                        .nextCursor();
        var last = frozen.members().getLast();
        directory()
                .publishTrusted(
                        TENANT,
                        1,
                        2,
                        List.of(
                                directoryEntry(
                                        last.accountId, last.externalId, last.name, other, TENANT)),
                        List.of());
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageTrusted(
                                                        TENANT,
                                                        900001,
                                                        frozen.snapshot().id,
                                                        null,
                                                        20,
                                                        cursor))
                        .status());
    }

    @Test
    void scopeMembersPermissionVersionChangeRejectsCursorAndFirstPageUntilRefrozen() {
        var frozen = pageFixture(45, TENANT, 1);
        String cursor =
                pages().pageTrusted(TENANT, 1, frozen.snapshot().id, null, 20, null).nextCursor();
        businessUser(900001, TENANT, "USER");
        for (String token : new String[] {null, cursor})
            assertEquals(
                    409,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () ->
                                            pages().pageTrusted(
                                                            TENANT,
                                                            1,
                                                            frozen.snapshot().id,
                                                            null,
                                                            20,
                                                            token))
                            .status());
        var fresh = scopes().freezeTrusted(TENANT, 1, key(), scopeFilter());
        assertEquals(
                20,
                pages().pageTrusted(TENANT, 1, fresh.snapshot().id, null, 20, null).items().size());
    }

    @Test
    void scopeMembersRenameKeepsFrozenNamesAndDeletionMakesScopeInvisible() {
        var frozen = pageFixture(45, TENANT, 1);
        var row = frozen.members().getLast();
        directory()
                .publishTrusted(
                        TENANT,
                        1,
                        2,
                        List.of(
                                directoryEntry(
                                        row.accountId, row.externalId, "renamed", TENANT, TENANT)),
                        List.of());
        var page = pages().pageTrusted(TENANT, 1, frozen.snapshot().id, null, 100, null);
        assertTrue(
                page.items().stream()
                        .anyMatch(
                                item ->
                                        item.accountId().equals(row.accountId)
                                                && item.name().equals(row.name)));
        directory().publishTrusted(TENANT, 1, 3, List.of(), List.of(row.accountId));
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageTrusted(
                                                        TENANT,
                                                        1,
                                                        frozen.snapshot().id,
                                                        null,
                                                        100,
                                                        null))
                        .status());
    }

    @Test
    void scopeMembersPageBoundsEmptyScopeMissingKeyAndLegacyVersionFailClosed() {
        var frozen = pageFixture(0, TENANT, 1);
        for (int size : List.of(20, 50, 100, 200)) {
            var page = pages().pageTrusted(TENANT, 1, frozen.snapshot().id, null, size, null);
            assertTrue(page.items().isEmpty());
            assertNull(page.nextCursor());
        }
        for (int size : List.of(0, 10, 201))
            assertEquals(
                    422,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () ->
                                            pages().pageTrusted(
                                                            TENANT,
                                                            1,
                                                            frozen.snapshot().id,
                                                            null,
                                                            size,
                                                            null))
                            .status());
        for (String q : List.of("x".repeat(101), "bad\nquery"))
            assertEquals(
                    422,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () ->
                                            pages().pageTrusted(
                                                            TENANT,
                                                            1,
                                                            frozen.snapshot().id,
                                                            q,
                                                            20,
                                                            null))
                            .status());
        var unavailable =
                new ScopeMemberPager(
                        context.getBean(AccountScopeMapper.class),
                        scopes(),
                        new SecretCipher(null, Map.of()),
                        context.getBean(ObjectMapper.class));
        assertEquals(
                503,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        unavailable.pageTrusted(
                                                TENANT, 1, frozen.snapshot().id, null, 20, null))
                        .status());
        jdbc.update("DELETE FROM orbit_account_scope_permission");
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageTrusted(
                                                        TENANT,
                                                        1,
                                                        frozen.snapshot().id,
                                                        null,
                                                        20,
                                                        null))
                        .status());
    }

    @Test
    void scopeMembersTeamAdministratorGrantIsRecheckedOnEveryPage() {
        String owner = businessUser(900002, TENANT, "USER");
        businessUser(900001, TENANT, "TEAM_ADMIN");
        jdbc.update(
                "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) VALUES(?,900001,?)",
                TENANT,
                TENANT);
        var frozen = pageFixture(45, owner, 900001);
        String cursor =
                pages().pageTrusted(TENANT, 900001, frozen.snapshot().id, null, 20, null)
                        .nextCursor();
        jdbc.update(
                "UPDATE orbit_business_team_manager SET enabled=0 WHERE manager_user_id=900001");
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        pages().pageTrusted(
                                                        TENANT,
                                                        900001,
                                                        frozen.snapshot().id,
                                                        null,
                                                        20,
                                                        cursor))
                        .status());
    }

    private long scopeVersion() {
        return context.getBean(ScopeVersionService.class).currentTrusted(TENANT, 1);
    }

    private org.springframework.transaction.support.TransactionTemplate transaction() {
        return new org.springframework.transaction.support.TransactionTemplate(
                context.getBean(DataSourceTransactionManager.class));
    }

    @Test
    void scopeVersionRevokeRegrantCannotRestoreOldVersion() {
        businessUser(900001, TENANT, "USER");
        long before = scopeVersion();
        jdbc.update("UPDATE orbit_user_scope SET data_role='TEAM_ADMIN' WHERE user_id=900001");
        jdbc.update("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=900001");
        assertEquals(before + 2, scopeVersion());
        var versions = context.getBean(ScopeVersionService.class);
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> versions.requireCurrentTrusted(TENANT, 1, before))
                        .status());
        assertDoesNotThrow(() -> versions.requireCurrentTrusted(TENANT, 1, before + 2));
        jdbc.update("UPDATE orbit_user_scope SET enabled=0 WHERE user_id=1");
        assertEquals(
                403,
                assertThrows(RuleDraftStore.Failure.class, () -> versions.currentTrusted(TENANT, 1))
                        .status());
    }

    @Test
    void scopeVersionSharedRoleAndMenuChangesInvalidateAllTenantsAndRollback() {
        String other = key();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'version fixture')", other);
        long before = scopeVersion(),
                otherBefore =
                        jdbc.queryForObject(
                                "SELECT version FROM orbit_scope_version WHERE tenant_id=?",
                                Long.class,
                                other);
        transaction()
                .executeWithoutResult(
                        status -> {
                            jdbc.update(
                                    "UPDATE sys_menu SET menu_name=CONCAT(menu_name,'x') WHERE menu_id=1");
                            assertEquals(before + 1, scopeVersion());
                            assertEquals(
                                    otherBefore + 1,
                                    jdbc.queryForObject(
                                            "SELECT version FROM orbit_scope_version WHERE tenant_id=?",
                                            Long.class,
                                            other));
                            jdbc.update("UPDATE sys_role SET status='1' WHERE role_id=2");
                            jdbc.update(
                                    "INSERT INTO sys_user_role(user_id,role_id) VALUES(999999,2)");
                            jdbc.update(
                                    "DELETE FROM sys_user_role WHERE user_id=999999 AND role_id=2");
                            jdbc.update("DELETE FROM sys_role_menu WHERE role_id=2 AND menu_id=1");
                            assertTrue(scopeVersion() >= before + 4);
                            status.setRollbackOnly();
                        });
        assertEquals(before, scopeVersion());
        assertEquals(
                otherBefore,
                jdbc.queryForObject(
                        "SELECT version FROM orbit_scope_version WHERE tenant_id=?",
                        Long.class,
                        other));
        jdbc.update("DELETE FROM orbit_tenant WHERE id=?", other);
    }

    @Test
    void scopeVersionMembershipMutationAndVersionRollbackTogether() {
        businessUser(900001, TENANT, "USER");
        long before = scopeVersion();
        transaction()
                .executeWithoutResult(
                        status -> {
                            jdbc.update(
                                    "UPDATE orbit_business_user SET enabled=0 WHERE user_id=900001");
                            assertEquals(before + 1, scopeVersion());
                            status.setRollbackOnly();
                        });
        assertEquals(before, scopeVersion());
        assertEquals(
                1,
                jdbc.queryForObject(
                        "SELECT enabled FROM orbit_business_user WHERE user_id=900001",
                        Integer.class));
        jdbc.update(
                "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) VALUES(?,900001,?)",
                TENANT,
                TENANT);
        long granted = scopeVersion();
        jdbc.update(
                "UPDATE orbit_business_team_manager SET enabled=0 WHERE manager_user_id=900001");
        assertEquals(granted + 1, scopeVersion());
        jdbc.update("UPDATE sys_user SET status='1' WHERE user_id=900001");
        assertEquals(granted + 2, scopeVersion());
    }

    @Test
    void scopeVersionConcurrentGrantsDoNotLoseIncrements() throws Exception {
        businessUser(900001, TENANT, "USER");
        businessUser(900002, TENANT, "USER");
        long before = scopeVersion();
        var results =
                concurrent(
                        () ->
                                jdbc.update(
                                        "UPDATE orbit_business_user SET enabled=0 WHERE user_id=900001"),
                        () ->
                                jdbc.update(
                                        "UPDATE orbit_business_user SET enabled=0 WHERE user_id=900002"));
        assertEquals(List.of(1, 1), results);
        assertEquals(before + 2, scopeVersion());
    }

    @Test
    void scopeVersionAccountTransferInvalidatesButRenameKeepsFrozenVersion() {
        String id = key(), other = businessUser(900001, TENANT, "USER");
        directory()
                .publishTrusted(
                        TENANT,
                        1,
                        1,
                        List.of(directoryEntry(id, "1", "old", TENANT, TENANT)),
                        List.of());
        long before = scopeVersion();
        var frozen = scopes().freezeTrusted(TENANT, 1, key(), scopeIds(id));
        assertEquals(before, frozen.snapshot().scopeVersion);
        directory()
                .publishTrusted(
                        TENANT,
                        1,
                        2,
                        List.of(directoryEntry(id, "1", "new", TENANT, TENANT)),
                        List.of());
        assertEquals(before, scopeVersion());
        directory()
                .publishTrusted(
                        TENANT,
                        1,
                        3,
                        List.of(directoryEntry(id, "1", "new", other, TENANT)),
                        List.of());
        assertEquals(before + 1, scopeVersion());
        directory().publishTrusted(TENANT, 1, 4, List.of(), List.of(id));
        assertEquals(before + 2, scopeVersion());
        assertEquals(
                before,
                jdbc.queryForObject(
                        "SELECT scope_version FROM orbit_account_scope_permission WHERE snapshot_id=?",
                        Long.class,
                        frozen.snapshot().id));
    }

    @Test
    void scopeVersionTenantTombstoneAndMigrationReplayNeverResetVersion() throws Exception {
        String tenant = key();
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'tombstone fixture')", tenant);
        assertEquals(
                1,
                jdbc.queryForObject(
                        "SELECT version FROM orbit_scope_version WHERE tenant_id=?",
                        Long.class,
                        tenant));
        jdbc.update("DELETE FROM orbit_tenant WHERE id=?", tenant);
        jdbc.update("INSERT INTO orbit_tenant(id,name) VALUES(?,'recreated fixture')", tenant);
        long recreated =
                jdbc.queryForObject(
                        "SELECT version FROM orbit_scope_version WHERE tenant_id=?",
                        Long.class,
                        tenant);
        assertEquals(3, recreated);
        Path root = Path.of("").toAbsolutePath();
        while (!java.nio.file.Files.exists(
                root.resolve("sql/orbit/V009__scope_permission_versions.sql")))
            root = root.getParent();
        try (var connection = jdbc.getDataSource().getConnection()) {
            ScriptUtils.executeSqlScript(
                    connection,
                    new EncodedResource(
                            new FileSystemResource(
                                    root.resolve("sql/orbit/V009__scope_permission_versions.sql")),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
        assertEquals(
                recreated,
                jdbc.queryForObject(
                        "SELECT version FROM orbit_scope_version WHERE tenant_id=?",
                        Long.class,
                        tenant));
        jdbc.update("DELETE FROM orbit_tenant WHERE id=?", tenant);
    }

    @Test
    void scopeVersionOverflowRejectsAuthorizationChangeWithoutWrapping() {
        businessUser(900001, TENANT, "USER");
        long restore = scopeVersion();
        jdbc.update(
                "UPDATE orbit_scope_version SET version=? WHERE tenant_id=?",
                ScopeVersionService.MAX_VERSION,
                TENANT);
        try {
            assertThrows(
                    org.springframework.dao.DataAccessException.class,
                    () ->
                            jdbc.update(
                                    "UPDATE orbit_business_user SET enabled=0 WHERE user_id=900001"));
            assertEquals(
                    1,
                    jdbc.queryForObject(
                            "SELECT enabled FROM orbit_business_user WHERE user_id=900001",
                            Integer.class));
            assertEquals(ScopeVersionService.MAX_VERSION, scopeVersion());
        } finally {
            // 只在独立fixture中恢复极限值；生产服务没有重置版本接口。
            jdbc.update(
                    "UPDATE orbit_scope_version SET version=? WHERE tenant_id=?", restore, TENANT);
        }
    }

    @Test
    void scopeVersionMissingMetadataAndLegacySnapshotFailClosed() {
        var versions = context.getBean(ScopeVersionService.class);
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> versions.requireCurrentTrusted(TENANT, 1, 0))
                        .status());
        String request = key();
        scopes().freezeTrusted(TENANT, 1, request, scopeFilter());
        jdbc.update("DELETE FROM orbit_account_scope_permission");
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().freezeTrusted(TENANT, 1, request, scopeFilter()))
                        .status());
        long restore = scopeVersion();
        jdbc.update("DELETE FROM orbit_scope_version WHERE tenant_id=?", TENANT);
        try {
            assertEquals(
                    503,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () -> versions.currentTrusted(TENANT, 1))
                            .status());
        } finally {
            jdbc.update(
                    "INSERT INTO orbit_scope_version(tenant_id,version) VALUES(?,?)",
                    TENANT,
                    restore);
        }
    }

    @Test
    void scopeVersionFreezeMetadataFailureRollsBackHeaderMembersAndClock() {
        directoryAccount("1", "one", TENANT, TENANT);
        jdbc.execute(
                "CREATE TRIGGER scope_version_fail BEFORE INSERT ON orbit_account_scope_permission FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='controlled scope version failure'");
        try {
            assertThrows(
                    org.springframework.dao.DataAccessException.class,
                    () -> scopes().freezeTrusted(TENANT, 1, key(), scopeFilter()));
        } finally {
            jdbc.execute("DROP TRIGGER scope_version_fail");
        }
        assertEquals(0, count("orbit_account_scope_permission"));
        assertEquals(0, count("orbit_account_scope_member"));
        assertEquals(0, count("orbit_account_scope_snapshot"));
        assertEquals(0, count("orbit_account_scope_clock"));
    }

    private AccountDirectoryPublisher directory() {
        return context.getBean(AccountDirectoryPublisher.class);
    }

    @Test
    void directoryPublishRacingFreezeNeverMixesVersions() throws Exception {
        String a = key(), b = key();
        directory()
                .publishTrusted(
                        TENANT,
                        1,
                        1,
                        List.of(
                                directoryEntry(a, "1", "old", TENANT, TENANT),
                                directoryEntry(b, "2", "old", TENANT, TENANT)),
                        List.of());
        var results =
                concurrent(
                        () ->
                                directory()
                                        .publishTrusted(
                                                TENANT,
                                                1,
                                                2,
                                                List.of(
                                                        directoryEntry(
                                                                a, "1", "new", TENANT, TENANT),
                                                        directoryEntry(
                                                                b, "2", "new", TENANT, TENANT)),
                                                List.of()),
                        () -> scopes().freezeTrusted(TENANT, 1, key(), scopeIds(a, b)));
        assertEquals(3L, results.getFirst());
        var frozen = assertInstanceOf(AccountScopeService.Frozen.class, results.getLast());
        assertEquals(2, frozen.members().size());
        long revision = frozen.snapshot().directoryRevision;
        assertTrue(revision == 2 || revision == 3);
        assertTrue(
                frozen.members().stream()
                        .allMatch(
                                row ->
                                        row.revision == revision
                                                && row.name.equals(revision == 2 ? "old" : "new")));
    }

    private AccountDirectoryPublisher.Entry directoryEntry(
            String id, String external, String name, String operator, String team) {
        return new AccountDirectoryPublisher.Entry(
                id, external, name, operator, team, null, "USD", "ACTIVE", "AUTHORIZED");
    }

    @Test
    void directoryPublishCreatesUpdatesAndRemovesWithMonotonicFrozenVersions() {
        String id = key(), request = key();
        assertEquals(
                2,
                directory()
                        .publishTrusted(
                                TENANT,
                                1,
                                1,
                                List.of(
                                        directoryEntry(
                                                id,
                                                "12345678901234567890123456789012",
                                                "原名",
                                                TENANT,
                                                TENANT)),
                                List.of()));
        var old = scopes().freezeTrusted(TENANT, 1, request, scopeIds(id));
        assertEquals(2, old.snapshot().directoryRevision);
        assertEquals(2, old.members().getFirst().revision);
        assertEquals(
                3,
                directory()
                        .publishTrusted(
                                TENANT,
                                1,
                                2,
                                List.of(
                                        directoryEntry(
                                                id,
                                                "12345678901234567890123456789012",
                                                "新名",
                                                TENANT,
                                                TENANT)),
                                List.of()));
        assertEquals(
                "原名",
                scopes().freezeTrusted(TENANT, 1, request, scopeIds(id)).members().getFirst().name);
        var fresh = scopes().freezeTrusted(TENANT, 1, key(), scopeIds(id));
        assertEquals("新名", fresh.members().getFirst().name);
        assertEquals(3, fresh.members().getFirst().revision);
        assertEquals(
                "UNVERIFIED",
                jdbc.queryForObject(
                        "SELECT source_state FROM orbit_account_scope_directory", String.class));
        assertEquals(4, directory().publishTrusted(TENANT, 1, 3, List.of(), List.of(id)));
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().freezeTrusted(TENANT, 1, request, scopeIds(id)))
                        .status());
        assertEquals(0, count("orbit_account_scope_directory"));
    }

    @Test
    void directoryPublishConcurrentSameVersionAllowsExactlyOneCommit() throws Exception {
        var first = directoryEntry(key(), "1", "first", TENANT, TENANT);
        var second = directoryEntry(key(), "2", "second", TENANT, TENANT);
        var results =
                concurrent(
                        () -> directory().publishTrusted(TENANT, 1, 1, List.of(first), List.of()),
                        () -> directory().publishTrusted(TENANT, 1, 1, List.of(second), List.of()));
        assertEquals(1, results.stream().filter(Long.class::isInstance).count());
        assertEquals(
                1,
                results.stream()
                        .filter(AccountScopeService.Failure.class::isInstance)
                        .map(AccountScopeService.Failure.class::cast)
                        .filter(error -> error.status() == 409)
                        .count());
        assertEquals(1, count("orbit_account_scope_directory"));
        assertEquals(
                2L,
                jdbc.queryForObject("SELECT revision FROM orbit_account_scope_clock", Long.class));
    }

    @Test
    void directoryPublishExternalConflictAndLateMissingDeleteRollbackWholeBatch() {
        String a = "10000000-0000-0000-0000-000000000001",
                b = "20000000-0000-0000-0000-000000000001";
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        directory()
                                                .publishTrusted(
                                                        TENANT,
                                                        1,
                                                        1,
                                                        List.of(
                                                                directoryEntry(
                                                                        a, "1", "first", TENANT,
                                                                        TENANT),
                                                                directoryEntry(
                                                                        b,
                                                                        "1",
                                                                        "collision",
                                                                        TENANT,
                                                                        TENANT)),
                                                        List.of()))
                        .status());
        assertEquals(0, count("orbit_account_scope_directory"));
        assertEquals(0, count("orbit_account_scope_clock"));
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        directory()
                                                .publishTrusted(
                                                        TENANT,
                                                        1,
                                                        1,
                                                        List.of(
                                                                directoryEntry(
                                                                        a, "1", "first", TENANT,
                                                                        TENANT)),
                                                        List.of(b)))
                        .status());
        assertEquals(0, count("orbit_account_scope_directory"));
        assertEquals(0, count("orbit_account_scope_clock"));
    }

    @Test
    void directoryPublishTransferImmediatelyRevokesOldScopeReplay() {
        String owner = businessUser(900001, TENANT, "USER"),
                other = businessUser(900002, TENANT, "USER"),
                id = key(),
                request = key();
        directory()
                .publishTrusted(
                        TENANT,
                        1,
                        1,
                        List.of(directoryEntry(id, "1", "one", owner, TENANT)),
                        List.of());
        scopes().freezeTrusted(TENANT, 900001, request, scopeIds(id));
        directory()
                .publishTrusted(
                        TENANT,
                        1,
                        2,
                        List.of(directoryEntry(id, "1", "one", other, TENANT)),
                        List.of());
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().freezeTrusted(TENANT, 900001, request, scopeIds(id)))
                        .status());
        assertEquals(
                1, scopes().freezeTrusted(TENANT, 900002, key(), scopeIds(id)).members().size());
    }

    @Test
    void directoryPublishRejectsStaleRevisionDuplicatesAndInvalidInputWithoutWrites() {
        var good = directoryEntry(key(), "1", "one", TENANT, TENANT);
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        directory()
                                                .publishTrusted(
                                                        TENANT, 1, 2, List.of(good), List.of()))
                        .status());
        for (var entries :
                List.of(
                        List.of(good, good),
                        List.of(directoryEntry(key(), "1e10", "one", TENANT, TENANT)),
                        List.of(directoryEntry(key(), "1", "bad\nname", TENANT, TENANT))))
            assertEquals(
                    422,
                    assertThrows(
                                    AccountScopeService.Failure.class,
                                    () ->
                                            directory()
                                                    .publishTrusted(
                                                            TENANT, 1, 1, entries, List.of()))
                            .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        directory()
                                                .publishTrusted(
                                                        TENANT,
                                                        1,
                                                        1,
                                                        List.of(good),
                                                        List.of(good.id())))
                        .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        directory()
                                                .publishTrusted(
                                                        TENANT,
                                                        1,
                                                        Long.MAX_VALUE,
                                                        List.of(good),
                                                        List.of()))
                        .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        directory()
                                                .publishTrusted(
                                                        TENANT,
                                                        1,
                                                        1,
                                                        Collections.nCopies(1001, good),
                                                        List.of()))
                        .status());
        assertEquals(0, count("orbit_account_scope_directory"));
        assertEquals(0, count("orbit_account_scope_clock"));
    }

    @Test
    void directoryPublishRechecksRoleTenantAndCurrentOwnerMembership() {
        String owner = businessUser(900001, TENANT, "USER"), wrongTeam = businessTeam();
        var good = directoryEntry(key(), "1", "one", owner, TENANT);
        assertEquals(
                403,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        directory()
                                                .publishTrusted(
                                                        TENANT,
                                                        900001,
                                                        1,
                                                        List.of(good),
                                                        List.of()))
                        .status());
        assertEquals(
                404,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        directory()
                                                .publishTrusted(
                                                        key(), 1, 1, List.of(good), List.of()))
                        .status());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        directory()
                                                .publishTrusted(
                                                        TENANT,
                                                        1,
                                                        1,
                                                        List.of(
                                                                directoryEntry(
                                                                        good.id(), "1", "one",
                                                                        owner, wrongTeam)),
                                                        List.of()))
                        .status());
        jdbc.update("UPDATE orbit_business_user SET enabled=0 WHERE user_id=900001");
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        directory()
                                                .publishTrusted(
                                                        TENANT, 1, 1, List.of(good), List.of()))
                        .status());
        jdbc.update("UPDATE orbit_user_scope SET enabled=0 WHERE user_id=1");
        assertEquals(
                403,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        directory()
                                                .publishTrusted(
                                                        TENANT, 1, 1, List.of(good), List.of()))
                        .status());
        assertEquals(0, count("orbit_account_scope_directory"));
        assertEquals(0, count("orbit_account_scope_clock"));
    }

    private com.fasterxml.jackson.databind.node.ObjectNode scopeFilter() {
        return ScopeRequestGuardTest.filter(context.getBean(ObjectMapper.class));
    }

    private com.fasterxml.jackson.databind.node.ObjectNode scopeIds(String... ids) {
        return ScopeRequestGuardTest.ids(context.getBean(ObjectMapper.class), ids);
    }

    private String directoryAccount(String external, String name, String operator, String team) {
        String id = key();
        jdbc.update(
                "INSERT INTO orbit_account_scope_directory(tenant_id,id,external_id,name,operator_user_id,owner_team_id,currency,account_status,auth_status) VALUES(?,?,?,?,?,?,'USD','ACTIVE','AUTHORIZED')",
                TENANT,
                id,
                external,
                name,
                operator,
                team);
        return id;
    }

    @Test
    void accountScopeFreezesDirectoryMembersAndReplayKeepsOldNames() {
        String a = directoryAccount("12345678901234567890123456789012", "原账户名", TENANT, TENANT),
                b = directoryAccount("2", "第二账户", TENANT, TENANT),
                request = key();
        var frozen = scopes().freezeTrusted(TENANT, 1, request, scopeIds(b, a));
        assertTrue(frozen.snapshot().ready);
        assertEquals(2, frozen.snapshot().memberCount);
        assertEquals(
                frozen.members().stream().map(row -> row.accountId).sorted().toList(),
                frozen.members().stream().map(row -> row.accountId).toList());
        jdbc.update(
                "UPDATE orbit_account_scope_directory SET name='新账户名',revision=2 WHERE tenant_id=? AND id=?",
                TENANT,
                a);
        var replay = scopes().freezeTrusted(TENANT, 1, request, scopeIds(a, b));
        assertEquals(frozen.snapshot().id, replay.snapshot().id);
        assertEquals(frozen.snapshot().membersHash, replay.snapshot().membersHash);
        assertTrue(
                replay.members().stream()
                        .anyMatch(
                                row ->
                                        row.name.equals("原账户名")
                                                && row.externalId.equals(
                                                        "12345678901234567890123456789012")));
        assertEquals(1, count("orbit_account_scope_snapshot"));
        assertEquals(2, count("orbit_account_scope_member"));
    }

    @Test
    void accountScopeFiltersIntersectCurrentUserAndEscapeLikeWildcards() {
        String a = businessUser(900001, TENANT, "USER"),
                b = businessUser(900002, TENANT, "USER"),
                vendor = key();
        String visible = directoryAccount("123456789", "promo!%_abc", a, TENANT);
        directoryAccount("3", "promoXXXabc", a, TENANT);
        directoryAccount("4", "promo!%_abc", b, TENANT);
        jdbc.update(
                "UPDATE orbit_account_scope_directory SET vendor_id=? WHERE tenant_id=? AND id=?",
                vendor,
                TENANT,
                visible);
        var input = scopeFilter();
        ((com.fasterxml.jackson.databind.node.ObjectNode) input.get("filter"))
                .put("q", "!%_")
                .put("status", "ACTIVE")
                .put("auth_status", "AUTHORIZED")
                .put("operator_user_id", a)
                .put("vendor_id", vendor);
        assertEquals(
                List.of(visible),
                scopes().freezeTrusted(TENANT, 900001, key(), input).members().stream()
                        .map(row -> row.accountId)
                        .toList());
        var partial = scopeFilter();
        ((com.fasterxml.jackson.databind.node.ObjectNode) partial.get("filter")).put("q", "123");
        assertEquals(
                0, scopes().freezeTrusted(TENANT, 900001, key(), partial).snapshot().memberCount);
        var exact = scopeFilter();
        ((com.fasterxml.jackson.databind.node.ObjectNode) exact.get("filter"))
                .put("q", "123456789");
        assertEquals(
                1, scopes().freezeTrusted(TENANT, 900001, key(), exact).snapshot().memberCount);
    }

    @Test
    void accountScopeExplicitIdsNeverSilentlyDropForbiddenAccounts() {
        String a = businessUser(900001, TENANT, "USER"), b = businessUser(900002, TENANT, "USER");
        String own = directoryAccount("1", "own", a, TENANT),
                other = directoryAccount("2", "other", b, TENANT);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        scopes().freezeTrusted(
                                                        TENANT,
                                                        900001,
                                                        key(),
                                                        scopeIds(own, other)))
                        .status());
        assertEquals(0, count("orbit_account_scope_snapshot"));
        assertEquals(0, count("orbit_account_scope_member"));
    }

    @Test
    void accountScopeReal50000BoundaryAndOverflowAreNotTruncated() {
        String digits =
                "(SELECT 0 n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9)";
        String numbers =
                "SELECT 1+a.n+10*b.n+100*c.n+1000*d.n+10000*e.n AS n FROM "
                        + digits
                        + " a CROSS JOIN "
                        + digits
                        + " b CROSS JOIN "
                        + digits
                        + " c CROSS JOIN "
                        + digits
                        + " d CROSS JOIN "
                        + digits
                        + " e";
        jdbc.update(
                "INSERT INTO orbit_account_scope_directory(tenant_id,id,external_id,name,currency,account_status,auth_status) SELECT ?,UUID(),CAST(n AS CHAR),'capacity fixture','USD','UNKNOWN','UNKNOWN' FROM ("
                        + numbers
                        + ") all_numbers WHERE n<=50001",
                TENANT);
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().freezeTrusted(TENANT, 1, key(), scopeFilter()))
                        .status());
        assertEquals(0, count("orbit_account_scope_snapshot"));
        jdbc.update(
                "DELETE FROM orbit_account_scope_directory WHERE tenant_id=? AND external_id='50001'",
                TENANT);
        var frozen = scopes().freezeTrusted(TENANT, 1, key(), scopeFilter());
        assertEquals(50000, frozen.snapshot().memberCount);
        assertEquals(50000, frozen.members().size());
        assertEquals(50000, count("orbit_account_scope_member"));
        // 真正走完上限范围的250页，不能用小样本或LIMIT截断代替容量验证。
        List<String> pagedIds = new ArrayList<>();
        String cursor = null;
        for (int i = 0; i < 250; i++) {
            var page = pages().pageTrusted(TENANT, 1, frozen.snapshot().id, null, 200, cursor);
            assertEquals(200, page.items().size());
            assertEquals(frozen.snapshot().createdAt, page.dataAsOf());
            pagedIds.addAll(page.items().stream().map(ScopeMemberPager.Item::accountId).toList());
            cursor = page.nextCursor();
            if (i < 249) assertNotNull(cursor);
        }
        assertNull(cursor);
        assertEquals(frozen.members().stream().map(row -> row.accountId).toList(), pagedIds);
        assertEquals(50000, new HashSet<>(pagedIds).size());
    }

    @Test
    void accountScopeConcurrentReplayOnlyWritesOneSnapshot() throws Exception {
        directoryAccount("1", "one", TENANT, TENANT);
        String request = key();
        var input = scopeFilter();
        var results =
                concurrent(
                        () -> scopes().freezeTrusted(TENANT, 1, request, input),
                        () -> scopes().freezeTrusted(TENANT, 1, request, input));
        assertTrue(results.stream().allMatch(AccountScopeService.Frozen.class::isInstance));
        assertEquals(
                ((AccountScopeService.Frozen) results.get(0)).snapshot().id,
                ((AccountScopeService.Frozen) results.get(1)).snapshot().id);
        assertEquals(1, count("orbit_account_scope_member"));
    }

    @Test
    void accountScopeMemberFailureRollsBackHeaderMembersAndClockReservation() {
        directoryAccount("1", "one", TENANT, TENANT);
        jdbc.execute(
                "CREATE TRIGGER scope_member_fail BEFORE INSERT ON orbit_account_scope_member FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='controlled scope member failure'");
        try {
            assertThrows(
                    RuntimeException.class,
                    () -> scopes().freezeTrusted(TENANT, 1, key(), scopeFilter()));
        } finally {
            jdbc.execute("DROP TRIGGER scope_member_fail");
        }
        assertEquals(0, count("orbit_account_scope_snapshot"));
        assertEquals(0, count("orbit_account_scope_member"));
        assertEquals(0, count("orbit_account_scope_clock"));
    }

    @Test
    void accountScopeReplayRechecksManagedTeamsAndCurrentAccountOwnership() {
        businessUser(900001, TENANT, "TEAM_ADMIN");
        String owner = businessUser(900002, TENANT, "USER"),
                account = directoryAccount("1", "one", owner, TENANT),
                request = key();
        jdbc.update(
                "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) VALUES(?,900001,?)",
                TENANT,
                TENANT);
        scopes().freezeTrusted(TENANT, 900001, request, scopeFilter());
        jdbc.update(
                "UPDATE orbit_business_team_manager SET enabled=0 WHERE manager_user_id=900001");
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        scopes().freezeTrusted(
                                                        TENANT, 900001, request, scopeFilter()))
                        .status());
        jdbc.update(
                "UPDATE orbit_business_team_manager SET enabled=1 WHERE manager_user_id=900001");
        String otherTeam = businessTeam();
        jdbc.update(
                "UPDATE orbit_account_scope_directory SET owner_team_id=? WHERE tenant_id=? AND id=?",
                otherTeam,
                TENANT,
                account);
        assertEquals(
                404,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () ->
                                        scopes().freezeTrusted(
                                                        TENANT, 900001, request, scopeFilter()))
                        .status());
        assertEquals(1, count("orbit_account_scope_snapshot"));
    }

    @Test
    void accountScopeUnknownSourceRevokedAuthAndEmptySetsCannotExecute() {
        String account = directoryAccount("1", "one", TENANT, TENANT), request = key();
        scopes().freezeTrusted(TENANT, 1, request, scopeFilter());
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().requireExecutableTrusted(TENANT, 1, request))
                        .status());
        jdbc.update(
                "UPDATE orbit_account_scope_directory SET auth_status='REVOKED' WHERE tenant_id=? AND id=?",
                TENANT,
                account);
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().requireExecutableTrusted(TENANT, 1, request))
                        .status());
        assertThrows(
                org.springframework.dao.DataAccessException.class,
                () ->
                        jdbc.update(
                                "UPDATE orbit_account_scope_directory SET source_state='META_VERIFIED' WHERE tenant_id=? AND id=?",
                                TENANT,
                                account));
        var changed = scopeFilter();
        ((com.fasterxml.jackson.databind.node.ObjectNode) changed.get("filter"))
                .put("q", "no-match");
        String empty = key();
        assertEquals(0, scopes().freezeTrusted(TENANT, 1, empty, changed).snapshot().memberCount);
        assertEquals(
                422,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().requireExecutableTrusted(TENANT, 1, empty))
                        .status());
        assertEquals(
                409,
                assertThrows(
                                AccountScopeService.Failure.class,
                                () -> scopes().freezeTrusted(TENANT, 1, request, changed))
                        .status());
    }

    private String businessTeam() {
        String id = key();
        jdbc.update(
                "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(?,?,'identity fixture')",
                TENANT,
                id);
        return id;
    }

    private String businessUser(long id, String team, String role) {
        String subject = key();
        jdbc.update(
                "INSERT INTO sys_user(user_id,user_name,nick_name,status,del_flag) VALUES(?,?,'identity fixture','0','0')",
                id,
                "orbit_fixture_" + id);
        jdbc.update(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role,enabled) VALUES(?,?,?,1)",
                id,
                TENANT,
                role);
        jdbc.update(
                "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id) VALUES(?,?,?,?)",
                TENANT,
                subject,
                id,
                team);
        return subject;
    }

    private com.fasterxml.jackson.databind.node.ObjectNode ownedBody(String owner, String team) {
        var body = ruleBody();
        ((com.fasterxml.jackson.databind.node.ObjectNode) body.get("ownership"))
                .put("owner_user_id", owner)
                .put("owner_team_id", team);
        return body;
    }

    @Test
    void ruleOwnershipUserCannotCreateForOthersOrStealExistingRule() {
        String a = businessUser(900001, TENANT, "USER"), b = businessUser(900002, TENANT, "USER");
        drafts().saveTrustedDraft(TENANT, 900001, key(), null, 0, ownedBody(a, TENANT), "本人创建");
        assertEquals(
                404,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        900001,
                                                        key(),
                                                        null,
                                                        0,
                                                        ownedBody(b, TENANT),
                                                        "同团队他人"))
                        .status());
        var other =
                drafts().saveTrustedDraft(
                                TENANT, 900002, key(), null, 0, ownedBody(b, TENANT), "他人创建");
        assertEquals(
                404,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        900001,
                                                        key(),
                                                        other.id,
                                                        1,
                                                        ownedBody(a, TENANT),
                                                        "改owner不能夺取资源"))
                        .status());
        assertEquals(2, count("orbit_rule_draft_event"));
    }

    @Test
    void ruleOwnershipTeamAdminRequiresExplicitManagedTeamAndRechecksReplay() {
        businessUser(900001, TENANT, "TEAM_ADMIN");
        String owner = businessUser(900002, TENANT, "USER");
        String request = key();
        assertEquals(
                404,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        900001,
                                                        request,
                                                        null,
                                                        0,
                                                        ownedBody(owner, TENANT),
                                                        "团队创建"))
                        .status());
        jdbc.update(
                "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) VALUES(?,900001,?)",
                TENANT,
                TENANT);
        drafts().saveTrustedDraft(
                        TENANT, 900001, request, null, 0, ownedBody(owner, TENANT), "团队创建");
        jdbc.update(
                "UPDATE orbit_business_team_manager SET enabled=0 WHERE manager_user_id=900001");
        assertEquals(
                404,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        900001,
                                                        request,
                                                        null,
                                                        0,
                                                        ownedBody(owner, TENANT),
                                                        "团队创建"))
                        .status());
        assertEquals(1, count("orbit_rule_draft_event"));
        assertEquals(1, count("orbit_rule_draft_idempotency"));
    }

    @Test
    void ruleOwnershipTeamAdminCannotUseUnmanagedOtherTeamButSuperCan() {
        businessUser(900001, TENANT, "TEAM_ADMIN");
        String team = businessTeam(), owner = businessUser(900002, team, "USER");
        jdbc.update(
                "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) VALUES(?,900001,?)",
                TENANT,
                TENANT);
        assertEquals(
                404,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        900001,
                                                        key(),
                                                        null,
                                                        0,
                                                        ownedBody(owner, team),
                                                        "其他团队"))
                        .status());
        assertEquals(
                "DRAFT",
                drafts().saveTrustedDraft(
                                TENANT, 1, key(), null, 0, ownedBody(owner, team), "本租户超级管理员")
                        .state);
    }

    @Test
    void ruleOwnershipRevocationsApplyBeforeIdempotentReplay() {
        String request = key();
        drafts().saveTrustedDraft(TENANT, 1, request, null, 0, ruleBody(), "创建");
        List<String[]> changes =
                List.of(
                        new String[] {"sys_user", "status", "'1'", "'0'", "user_id=1"},
                        new String[] {"sys_user", "del_flag", "'2'", "'0'", "user_id=1"},
                        new String[] {"orbit_business_user", "enabled", "0", "1", "user_id=1"},
                        new String[] {
                            "orbit_business_team", "enabled", "0", "1", "id='" + TENANT + "'"
                        },
                        new String[] {"orbit_user_scope", "enabled", "0", "1", "user_id=1"},
                        new String[] {
                            "orbit_user_scope",
                            "data_role",
                            "'UNKNOWN'",
                            "'SUPER_ADMIN'",
                            "user_id=1"
                        });
        for (String[] change : changes) {
            jdbc.update(
                    "UPDATE " + change[0] + " SET " + change[1] + "=" + change[2] + " WHERE "
                            + change[4]);
            try {
                assertEquals(
                        403,
                        assertThrows(
                                        RuleDraftStore.Failure.class,
                                        () ->
                                                drafts().saveTrustedDraft(
                                                                TENANT,
                                                                1,
                                                                request,
                                                                null,
                                                                0,
                                                                ruleBody(),
                                                                "创建"))
                                .status());
            } finally {
                jdbc.update(
                        "UPDATE " + change[0] + " SET " + change[1] + "=" + change[3] + " WHERE "
                                + change[4]);
            }
        }
        assertEquals(1, count("orbit_rule_draft_event"));
    }

    @Test
    void ruleOwnershipNewAssignmentRequiresActiveOwnerAndMatchingMembership() {
        String owner = businessUser(900001, TENANT, "USER"), otherTeam = businessTeam();
        assertEquals(
                422,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        1,
                                                        key(),
                                                        null,
                                                        0,
                                                        ownedBody(owner, otherTeam),
                                                        "团队不匹配"))
                        .status());
        jdbc.update("UPDATE sys_user SET status='1' WHERE user_id=900001");
        assertEquals(
                422,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        1,
                                                        key(),
                                                        null,
                                                        0,
                                                        ownedBody(owner, TENANT),
                                                        "停用owner"))
                        .status());
        assertEquals(
                404,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        1,
                                                        key(),
                                                        null,
                                                        0,
                                                        ownedBody(key(), TENANT),
                                                        "不存在owner"))
                        .status());
        assertEquals(0, count("orbit_rule_draft"));
        assertEquals(0, count("orbit_rule_draft_idempotency"));
    }

    @Test
    void ruleOwnershipMemberTransferDoesNotMoveFrozenRuleToAnotherTeam() {
        businessUser(900001, TENANT, "TEAM_ADMIN");
        String owner = businessUser(900002, TENANT, "USER"), otherTeam = businessTeam();
        jdbc.update(
                "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) VALUES(?,900001,?)",
                TENANT,
                TENANT);
        var rule =
                drafts().saveTrustedDraft(
                                TENANT, 900001, key(), null, 0, ownedBody(owner, TENANT), "原团队规则");
        jdbc.update("UPDATE orbit_business_user SET team_id=? WHERE user_id=900002", otherTeam);
        assertEquals(
                422,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        900001,
                                                        key(),
                                                        rule.id,
                                                        1,
                                                        ownedBody(owner, TENANT),
                                                        "新分配不能沿用旧成员关系"))
                        .status());
        assertEquals(
                "ARCHIVED",
                drafts().transitionTrusted(
                                TENANT, 900001, key(), rule.id, 1, "ARCHIVE", "按冻结团队管理旧规则")
                        .state);
    }

    @Test
    void ruleOwnershipReassignmentRevokesOldUserReplayAccess() {
        String a = businessUser(900001, TENANT, "USER"),
                b = businessUser(900002, TENANT, "USER"),
                request = key();
        var rule =
                drafts().saveTrustedDraft(
                                TENANT, 900001, request, null, 0, ownedBody(a, TENANT), "本人规则");
        drafts().saveTrustedDraft(TENANT, 1, key(), rule.id, 1, ownedBody(b, TENANT), "管理员改归属");
        assertEquals(
                404,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        900001,
                                                        request,
                                                        null,
                                                        0,
                                                        ownedBody(a, TENANT),
                                                        "本人规则"))
                        .status());
        assertEquals(2, count("orbit_rule_draft_event"));
    }

    @Test
    void ruleOwnershipMissingUuidMappingCannotInferAuthorityFromRuoYiUser() {
        jdbc.update(
                "INSERT INTO sys_user(user_id,dept_id,user_name,nick_name,status,del_flag) VALUES(900001,103,'unmapped_fixture','unmapped fixture','0','0')");
        jdbc.update(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(900001,?,'SUPER_ADMIN')",
                TENANT);
        assertEquals(
                403,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        900001,
                                                        key(),
                                                        null,
                                                        0,
                                                        ruleBody(),
                                                        "没有业务身份映射"))
                        .status());
        assertEquals(0, count("orbit_rule_draft"));
    }

    @Test
    void ruleDraftVersionsFreezeAndOldCreateReplayReturnsOriginalVersion() throws Exception {
        var body = ruleBody();
        String key = key();
        var first = drafts().saveTrustedDraft(TENANT, 1, key, null, 0, body, "创建规则");
        assertEquals("DRAFT", first.state);
        assertEquals(1, first.revision);
        assertEquals(
                "PENDING_REFERENCES",
                jdbc.queryForObject(
                        "SELECT reference_status FROM orbit_rule_draft WHERE tenant_id=? AND id=?",
                        String.class,
                        TENANT,
                        first.id));
        var updated =
                drafts().saveTrustedDraft(
                                TENANT,
                                1,
                                key(),
                                first.id,
                                1,
                                ruleBody().put("name", "修订规则"),
                                "修改规则");
        assertEquals(2, updated.revision);
        var replay = drafts().saveTrustedDraft(TENANT, 1, key, null, 0, body, "创建规则");
        assertEquals(first.id, replay.id);
        assertEquals(1, replay.revision);
        assertEquals(first.bodyHash, replay.bodyHash);
        assertEquals("测试规则", new ObjectMapper().readTree(replay.bodyJson).path("name").asText());
        assertEquals(2, count("orbit_rule_draft_version"));
        assertEquals(2, count("orbit_rule_draft_event"));
        assertEquals(
                first.bodyHash,
                HexFormat.of()
                        .formatHex(
                                java.security.MessageDigest.getInstance("SHA-256")
                                        .digest(
                                                first.bodyJson.getBytes(
                                                        java.nio.charset.StandardCharsets.UTF_8))));
    }

    @Test
    void ruleDraftRejectsChangedIdempotencyAndStaleRevisionWithoutResidue() {
        String key = key();
        var first = drafts().saveTrustedDraft(TENANT, 1, key, null, 0, ruleBody(), "创建规则");
        assertEquals(
                409,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        1,
                                                        key,
                                                        null,
                                                        0,
                                                        ruleBody().put("name", "其他规则"),
                                                        "创建规则"))
                        .status());
        drafts().saveTrustedDraft(TENANT, 1, key(), first.id, 1, ruleBody(), "修订规则");
        assertEquals(
                409,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        1,
                                                        key(),
                                                        first.id,
                                                        1,
                                                        ruleBody(),
                                                        "旧版本修订"))
                        .status());
        assertEquals(2, count("orbit_rule_draft_idempotency"));
        assertEquals(2, count("orbit_rule_draft_event"));
    }

    @Test
    void concurrentSameRuleCreateIdempotencyCommitsOneVersionAndEvent() throws Exception {
        String key = key();
        var results =
                concurrent(
                        () ->
                                drafts().saveTrustedDraft(
                                                TENANT, 1, key, null, 0, ruleBody(), "并发创建"),
                        () ->
                                drafts().saveTrustedDraft(
                                                TENANT, 1, key, null, 0, ruleBody(), "并发创建"));
        assertTrue(results.stream().allMatch(RuleDraftStore.Row.class::isInstance));
        assertEquals(
                ((RuleDraftStore.Row) results.get(0)).id, ((RuleDraftStore.Row) results.get(1)).id);
        assertEquals(1, count("orbit_rule_draft"));
        assertEquals(1, count("orbit_rule_draft_version"));
        assertEquals(1, count("orbit_rule_draft_event"));
    }

    @Test
    void concurrentRuleDraftCasOnlyOneEditCommits() throws Exception {
        var first = drafts().saveTrustedDraft(TENANT, 1, key(), null, 0, ruleBody(), "创建");
        var results =
                concurrent(
                        () ->
                                drafts().saveTrustedDraft(
                                                TENANT,
                                                1,
                                                key(),
                                                first.id,
                                                1,
                                                ruleBody().put("name", "版本A"),
                                                "修订"),
                        () ->
                                drafts().saveTrustedDraft(
                                                TENANT,
                                                1,
                                                key(),
                                                first.id,
                                                1,
                                                ruleBody().put("name", "版本B"),
                                                "修订"));
        assertEquals(1, results.stream().filter(RuleDraftStore.Row.class::isInstance).count());
        assertEquals(
                1,
                results.stream()
                        .filter(
                                value ->
                                        value instanceof RuleDraftStore.Failure error
                                                && error.status() == 409)
                        .count());
        assertEquals(2, count("orbit_rule_draft_version"));
        assertEquals(2, count("orbit_rule_draft_idempotency"));
    }

    @Test
    void ruleDraftAuditFailureRollsBackHeadVersionAndIdempotency() {
        jdbc.execute(
                "CREATE TRIGGER rule_event_fail BEFORE INSERT ON orbit_rule_draft_event FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='controlled rule event failure'");
        try {
            assertThrows(
                    RuntimeException.class,
                    () -> drafts().saveTrustedDraft(TENANT, 1, key(), null, 0, ruleBody(), "创建"));
        } finally {
            jdbc.execute("DROP TRIGGER rule_event_fail");
        }
        for (String table :
                List.of(
                        "orbit_rule_draft",
                        "orbit_rule_draft_version",
                        "orbit_rule_draft_event",
                        "orbit_rule_draft_idempotency")) assertEquals(0, count(table));
    }

    @Test
    void ruleDraftRequiresPauseBeforeEditingAndArchiveIsTerminal() {
        var first = drafts().saveTrustedDraft(TENANT, 1, key(), null, 0, ruleBody(), "创建");
        // 仅用SQL布置已启用历史fixture；生产代码没有绕过真实模拟的启用入口。
        jdbc.update(
                "UPDATE orbit_rule_draft SET state='ENABLED',current_simulation_id=? WHERE tenant_id=? AND id=?",
                key(),
                TENANT,
                first.id);
        assertEquals(
                409,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        1,
                                                        key(),
                                                        first.id,
                                                        1,
                                                        ruleBody(),
                                                        "未暂停编辑"))
                        .status());
        assertEquals(
                409,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().transitionTrusted(
                                                        TENANT, 1, key(), first.id, 1, "ARCHIVE",
                                                        "未暂停归档"))
                        .status());
        assertEquals(
                422,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().transitionTrusted(
                                                        TENANT, 1, key(), first.id, 1, "ENABLE",
                                                        "不允许绕过模拟"))
                        .status());
        var paused = drafts().transitionTrusted(TENANT, 1, key(), first.id, 1, "PAUSE", "暂停编辑");
        assertEquals("PAUSED", paused.state);
        jdbc.update(
                "UPDATE orbit_rule_draft SET current_simulation_id=? WHERE tenant_id=? AND id=?",
                key(),
                TENANT,
                first.id);
        var updated =
                drafts().saveTrustedDraft(
                                TENANT, 1, key(), first.id, 2, ruleBody().put("name", "修改后"), "修改");
        assertEquals(3, updated.revision);
        assertNull(
                jdbc.queryForObject(
                        "SELECT current_simulation_id FROM orbit_rule_draft WHERE tenant_id=? AND id=?",
                        String.class,
                        TENANT,
                        first.id));
        assertEquals(
                "ARCHIVED",
                drafts().transitionTrusted(TENANT, 1, key(), first.id, 3, "ARCHIVE", "归档").state);
        assertEquals(
                409,
                assertThrows(
                                RuleDraftStore.Failure.class,
                                () ->
                                        drafts().saveTrustedDraft(
                                                        TENANT,
                                                        1,
                                                        key(),
                                                        first.id,
                                                        4,
                                                        ruleBody(),
                                                        "归档后编辑"))
                        .status());
        assertEquals(4, count("orbit_rule_draft_event"));
    }

    @Test
    void ruleDraftTenantIsolationAndDisabledTenantBlockReplay() {
        String originalKey = key();
        var first = drafts().saveTrustedDraft(TENANT, 1, originalKey, null, 0, ruleBody(), "创建");
        String foreign = key();
        jdbc.update(
                "INSERT INTO orbit_tenant(id,name,enabled) VALUES(?, 'foreign fixture',1)",
                foreign);
        try {
            assertEquals(
                    404,
                    assertThrows(
                                    RuleDraftStore.Failure.class,
                                    () ->
                                            drafts().saveTrustedDraft(
                                                            foreign,
                                                            1,
                                                            key(),
                                                            first.id,
                                                            1,
                                                            ruleBody(),
                                                            "跨租户修订"))
                            .status());
            jdbc.update("UPDATE orbit_tenant SET enabled=0 WHERE id=?", TENANT);
            assertEquals(
                    404,
                    assertThrows(
                                    RuleDraftStore.Failure.class,
                                    () ->
                                            drafts().saveTrustedDraft(
                                                            TENANT,
                                                            1,
                                                            originalKey,
                                                            null,
                                                            0,
                                                            ruleBody(),
                                                            "创建"))
                            .status());
        } finally {
            jdbc.update("UPDATE orbit_tenant SET enabled=1 WHERE id=?", TENANT);
            jdbc.update("DELETE FROM orbit_tenant WHERE id=?", foreign);
        }
        assertEquals(1, count("orbit_rule_draft_idempotency"));
        assertEquals(1, count("orbit_rule_draft_event"));
    }
}

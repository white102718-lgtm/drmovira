package com.adpulse.system.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.yaml.snakeyaml.Yaml;

/** 部署与多环境YAML配置结构测试。 */
class DeploymentConfigurationTest {

    @Test
    void shouldParseAllApplicationProfiles() throws IOException {
        Yaml yaml = new Yaml();
        for (String name :
                List.of("application.yml", "application-test.yml", "application-prod.yml")) {
            try (InputStream input =
                    Files.newInputStream(Path.of("src", "main", "resources", name))) {
                Map<?, ?> document = yaml.loadAs(input, Map.class);
                assertThat(document).as(name).isNotEmpty();
            }
        }
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldEnableDocumentationOnlyInTestProfile() throws IOException {
        Map<String, Object> test = loadYaml("application-test.yml");
        Map<String, Object> prod = loadYaml("application-prod.yml");

        Map<String, Object> testSpringdoc = (Map<String, Object>) test.get("springdoc");
        Map<String, Object> prodSpringdoc = (Map<String, Object>) prod.get("springdoc");
        Map<String, Object> testApiDocs = (Map<String, Object>) testSpringdoc.get("api-docs");
        Map<String, Object> prodApiDocs = (Map<String, Object>) prodSpringdoc.get("api-docs");

        assertThat(testApiDocs.get("enabled")).isEqualTo(true);
        assertThat(prodApiDocs.get("enabled")).isEqualTo(false);
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldExposeRemotePortsAndMountConfiguration() throws IOException {
        Map<String, Object> document;
        try (InputStream input = Files.newInputStream(Path.of("..", "docker-compose.yml"))) {
            document = new Yaml().load(input);
        }
        Map<String, Object> services = (Map<String, Object>) document.get("services");
        Map<String, Object> mysql = (Map<String, Object>) services.get("mysql");
        Map<String, Object> redis = (Map<String, Object>) services.get("redis");

        assertThat((List<String>) mysql.get("ports")).allMatch(port -> port.startsWith("0.0.0.0:"));
        assertThat((List<String>) redis.get("ports")).allMatch(port -> port.startsWith("0.0.0.0:"));
        assertThat((List<String>) mysql.get("volumes"))
                .contains(
                        "/opt/docker/mysql/conf.d:/etc/mysql/conf.d:ro",
                        "/opt/docker/mysql/data:/var/lib/mysql",
                        "/opt/docker/mysql/logs:/var/log/mysql");
        assertThat((List<String>) redis.get("volumes"))
                .contains(
                        "/opt/docker/redis/conf:/usr/local/etc/redis:ro",
                        "/opt/docker/redis/data:/data",
                        "/opt/docker/redis/logs:/var/log/redis");
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldUseProductionJavaLogDirectory() throws IOException {
        Map<String, Object> prod = loadYaml("application-prod.yml");
        Map<String, Object> logging = (Map<String, Object>) prod.get("logging");
        Map<String, Object> file = (Map<String, Object>) logging.get("file");

        assertThat(file.get("name"))
                .isEqualTo(
                        "${APP_LOG_FILE:/opt/docker/java/system/logs/adpulse-system-server.log}");
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldKeepProductionBootstrapAdministratorOptIn() throws IOException {
        Map<String, Object> prod = loadYaml("application-prod.yml");
        Map<String, Object> adpulse = (Map<String, Object>) prod.get("adpulse");
        Map<String, Object> bootstrap = (Map<String, Object>) adpulse.get("bootstrap-admin");

        assertThat(bootstrap.get("enabled")).isEqualTo("${BOOTSTRAP_ADMIN_ENABLED:false}");
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldSupportFileLoggingInEveryProfile() throws IOException {
        Map<String, Object> common = loadYaml("application.yml");
        Map<String, Object> logging = (Map<String, Object>) common.get("logging");
        Map<String, Object> file = (Map<String, Object>) logging.get("file");

        assertThat(file.get("name")).isEqualTo("${APP_LOG_FILE:logs/adpulse-system-server.log}");
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldConfigureShanghaiTimeZoneForJsonAndDatabaseSessions() throws IOException {
        Map<String, Object> common = loadYaml("application.yml");
        Map<String, Object> spring = (Map<String, Object>) common.get("spring");
        Map<String, Object> jackson = (Map<String, Object>) spring.get("jackson");
        Map<String, Object> datasource = (Map<String, Object>) spring.get("datasource");
        Map<String, Object> hikari = (Map<String, Object>) datasource.get("hikari");

        assertThat(jackson.get("time-zone")).isEqualTo("Asia/Shanghai");
        assertThat(hikari.get("connection-init-sql")).isEqualTo("SET time_zone = '+08:00'");
    }

    @Test
    void shouldLeaveDatabaseSchemaChangesToManualScripts() throws IOException {
        Map<String, Object> common = loadYaml("application.yml");
        Map<String, Object> prod = loadYaml("application-prod.yml");
        Map<?, ?> commonSpring = (Map<?, ?>) common.get("spring");
        Map<?, ?> prodSpring = (Map<?, ?>) prod.get("spring");

        assertThat(commonSpring.containsKey("flyway")).isFalse();
        assertThat(prodSpring.containsKey("flyway")).isFalse();
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldConfigureFeishuOAuthRedirectPerEnvironment() throws IOException {
        Map<String, Object> test = loadYaml("application-test.yml");
        Map<String, Object> prod = loadYaml("application-prod.yml");

        Map<String, Object> testAdpulse = (Map<String, Object>) test.get("adpulse");
        Map<String, Object> prodAdpulse = (Map<String, Object>) prod.get("adpulse");
        Map<String, Object> testFeishu = (Map<String, Object>) testAdpulse.get("feishu");
        Map<String, Object> prodFeishu = (Map<String, Object>) prodAdpulse.get("feishu");
        Map<String, Object> testOauth = (Map<String, Object>) testFeishu.get("oauth");
        Map<String, Object> prodOauth = (Map<String, Object>) prodFeishu.get("oauth");

        assertThat(testOauth.get("redirect-uri"))
                .isEqualTo(
                        "${FEISHU_OAUTH_REDIRECT_URI:http://13.115.116.214:5556/auth/feishu/callback}");
        assertThat(prodOauth.get("redirect-uri")).isEqualTo("${FEISHU_OAUTH_REDIRECT_URI}");
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldRequireMpowerFeishuCredentialsInProduction() throws IOException {
        Map<String, Object> prod = loadYaml("application-prod.yml");
        Map<String, Object> mpower = (Map<String, Object>) prod.get("mpower");
        Map<String, Object> feishu = (Map<String, Object>) mpower.get("feishu");

        assertThat(feishu.get("app-id")).isEqualTo("${MPOWER_FEISHU_APP_ID}");
        assertThat(feishu.get("app-secret")).isEqualTo("${MPOWER_FEISHU_APP_SECRET}");
    }

    @Test
    void shouldProvideManualScriptForRemovingLegacyMfaFlag() throws IOException {
        String script =
                Files.readString(
                        Path.of(
                                "src",
                                "main",
                                "resources",
                                "db",
                                "migration",
                                "V4__drop_legacy_mfa_enabled.sql"));

        assertThat(script)
                .contains("DROP CHECK ck_user_mfa_enabled")
                .contains("DROP COLUMN mfa_enabled");
    }

    @Test
    void shouldProvideManualLoginLogSchemaAndPermissionScript() throws IOException {
        String script =
                Files.readString(
                        Path.of(
                                "src",
                                "main",
                                "resources",
                                "db",
                                "migration",
                                "V5__create_login_log.sql"));

        assertThat(script)
                .contains("CREATE TABLE sys_login_log")
                .contains("system:login-log:list")
                .doesNotContain("password_hash", "mfa_secret", "access_token", "challenge_token");
    }

    @Test
    void shouldProvideManualOperationLogSchemaAndPermissionScript() throws IOException {
        String script =
                Files.readString(
                        Path.of(
                                "src",
                                "main",
                                "resources",
                                "db",
                                "migration",
                                "V6__create_operation_log.sql"));

        assertThat(script)
                .contains("CREATE TABLE sys_operation_log")
                .contains("system:operation-log:list")
                .doesNotContain(
                        "request_body",
                        "password_hash",
                        "mfa_secret",
                        "access_token",
                        "challenge_token");
    }

    @Test
    void shouldProvideManualDictionarySchemaAndPermissionScript() throws IOException {
        String script =
                Files.readString(
                        Path.of(
                                "src",
                                "main",
                                "resources",
                                "db",
                                "migration",
                                "V7__create_dictionary_tables.sql"));

        assertThat(script)
                .contains("CREATE TABLE sys_dict_type")
                .contains("CREATE TABLE sys_dict_item")
                .contains("deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0")
                .contains("system:dictionary:list")
                .doesNotContain("FOREIGN KEY");
    }

    private Map<String, Object> loadYaml(String name) throws IOException {
        try (InputStream input = Files.newInputStream(Path.of("src", "main", "resources", name))) {
            return new Yaml().load(input);
        }
    }
}

package com.adpulse.system.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.mybatis.spring.boot.autoconfigure.MybatisAutoConfiguration;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.security.servlet.SecurityAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Knife4j与Spring Boot 3.5运行期兼容性冒烟测试。 */
@SpringBootTest(
        classes = Knife4jSmokeTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "springdoc.api-docs.enabled=true",
            "springdoc.swagger-ui.enabled=true",
            "knife4j.enable=false"
        })
class Knife4jSmokeTest {

    private final TestRestTemplate restTemplate;

    @Autowired
    Knife4jSmokeTest(TestRestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    @Test
    void shouldServeKnife4jUiAndOpenApiDocument() {
        ResponseEntity<String> ui = restTemplate.getForEntity("/doc.html", String.class);
        ResponseEntity<String> apiDocs = restTemplate.getForEntity("/v3/api-docs", String.class);

        assertThat(ui.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(ui.getBody()).contains("Knife4j");
        assertThat(apiDocs.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(apiDocs.getBody()).contains("/smoke/ping");
    }

    /** 只加载文档相关自动配置的测试应用。 */
    @SpringBootConfiguration
    @EnableAutoConfiguration(
            exclude = {
                DataSourceAutoConfiguration.class,
                MybatisAutoConfiguration.class,
                RedisAutoConfiguration.class,
                SecurityAutoConfiguration.class
            })
    @Import(SmokeController.class)
    static class TestApplication {}

    /** 文档生成探针接口。 */
    @RestController
    static class SmokeController {

        /** 返回固定探针值。 */
        @GetMapping("/smoke/ping")
        String ping() {
            return "pong";
        }
    }
}

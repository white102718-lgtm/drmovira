package com.adpulse.system.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

/** 测试环境OpenAPI及JWT调试配置。 */
@Configuration
@Profile("test")
public class OpenApiConfig {

    private static final String BEARER_AUTH = "BearerAuth";

    /** 创建供前端联调使用的OpenAPI元数据和JWT认证入口。 */
    @Bean
    OpenAPI systemManagementOpenApi() {
        SecurityScheme bearerScheme =
                new SecurityScheme()
                        .name("Authorization")
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")
                        .description("登录后填入JWT，Knife4j会自动添加Bearer前缀");
        return new OpenAPI()
                .info(
                        new Info()
                                .title("AdPulse系统管理接口")
                                .description("用户、角色、部门、菜单及认证接口，供测试环境前端联调")
                                .version("v1")
                                .contact(new Contact().name("AdPulse")))
                .components(new Components().addSecuritySchemes(BEARER_AUTH, bearerScheme))
                .addSecurityItem(new SecurityRequirement().addList(BEARER_AUTH));
    }
}

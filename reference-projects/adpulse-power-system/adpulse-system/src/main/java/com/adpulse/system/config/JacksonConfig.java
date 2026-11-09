package com.adpulse.system.config;

import com.fasterxml.jackson.databind.ser.std.ToStringSerializer;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** JSON 序列化约定，避免 JavaScript 丢失 BIGINT 标识精度。 */
@Configuration
public class JacksonConfig {

    /** 将包装类型 Long 统一序列化成字符串。 */
    @Bean
    Jackson2ObjectMapperBuilderCustomizer longAsStringCustomizer() {
        return builder -> builder.serializerByType(Long.class, ToStringSerializer.instance);
    }
}

package com.adpulse.system;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** AdPulse 系统管理服务启动入口。 */
@SpringBootApplication
public class SystemServerApplication {

    /**
     * 启动 Spring Boot 应用。
     *
     * @param args 命令行参数
     */
    public static void main(String[] args) {
        SpringApplication.run(SystemServerApplication.class, args);
    }
}

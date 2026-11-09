package com.adpulse.main;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

/** 主业务微服务启动入口。 */
@SpringBootApplication(scanBasePackages = {"com.adpulse.main", "com.adpulse.system.auth"})
@EnableScheduling
public class MainServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(MainServerApplication.class, args);
    }
}

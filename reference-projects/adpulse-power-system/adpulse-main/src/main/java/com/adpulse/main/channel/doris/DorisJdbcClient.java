package com.adpulse.main.channel.doris;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

/** 持有独立 Doris 连接池，避免被 MyBatis 识别为业务主数据源。 */
public class DorisJdbcClient implements AutoCloseable {
    private final HikariDataSource dataSource;
    private final NamedParameterJdbcTemplate jdbc;

    public DorisJdbcClient(DorisProperties properties) {
        dataSource = new HikariDataSource();
        dataSource.setJdbcUrl(properties.url());
        dataSource.setUsername(properties.username());
        dataSource.setPassword(properties.password());
        dataSource.setMaximumPoolSize(5);
        dataSource.setMinimumIdle(0);
        dataSource.setConnectionTimeout(10_000);
        dataSource.setReadOnly(true);
        dataSource.setPoolName("adpulse-doris");
        jdbc = new NamedParameterJdbcTemplate(dataSource);
    }

    /** 返回仅用于 Doris 查询的命名参数模板。 */
    public NamedParameterJdbcTemplate jdbc() {
        return jdbc;
    }

    /** 关闭 Doris 连接池。 */
    @Override
    public void close() {
        dataSource.close();
    }
}

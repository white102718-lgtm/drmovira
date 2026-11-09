package com.adpulse.main.migration;

import com.adpulse.main.migration.AssetMigrationModels.Source;
import com.adpulse.main.migration.ChannelIncrementModels.LegacyChannel;
import com.adpulse.main.migration.ChannelIncrementModels.LegacyRate;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.LegacyPayment;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.annotation.PreDestroy;
import java.io.InputStream;
import java.util.List;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.springframework.core.io.ClassPathResource;

/** 独立只读来源连接池；不暴露 DataSource Bean，避免替换主库自动配置。 */
public class LegacyAssetReader {
    private final AssetMigrationProperties properties;
    private HikariDataSource pool;
    private SqlSessionFactory factory;

    public LegacyAssetReader(AssetMigrationProperties properties) {
        this.properties = properties;
    }

    /** 渠道和费率必须在同一一致性快照内读取，避免拼接两个时间点的数据。 */
    public synchronized ChannelIncrementModels.SourceSnapshot readChannelSnapshot() {
        initialize();
        try (var session =
                factory.openSession(
                        org.apache.ibatis.session.TransactionIsolationLevel.REPEATABLE_READ)) {
            var mapper = session.getMapper(LegacyAssetMapper.class);
            requireIdentity(mapper);
            var channels = mapper.channels();
            var rates = mapper.rates();
            AssetMigrationService.require(
                    channels.size() <= 10000 && rates.size() <= 10000, "来源渠道或费率超过一万条，请调整迁移规模");
            return new ChannelIncrementModels.SourceSnapshot(channels, rates);
        }
    }

    /** 从老生产一次读取快照；异常只向任务报告类型，不暴露连接凭据。 */
    public synchronized List<Source> read() {
        initialize();
        try (var session = factory.openSession()) {
            var mapper = session.getMapper(LegacyAssetMapper.class);
            var identity = mapper.identity();
            AssetMigrationService.require(
                    properties.getSourceUuid().equals(identity.serverUuid())
                            && properties.getSourceSchema().equals(identity.schemaName()),
                    "来源实例或库名不符");
            var rows = mapper.snapshot();
            AssetMigrationService.require(rows.size() <= 100000, "来源超过十万条，请调整迁移规模");
            return rows;
        }
    }

    /** 从同一只读来源连接读取渠道快照。 */
    public synchronized List<LegacyChannel> readChannels() {
        initialize();
        try (var session = factory.openSession()) {
            var mapper = session.getMapper(LegacyAssetMapper.class);
            requireIdentity(mapper);
            var rows = mapper.channels();
            AssetMigrationService.require(rows.size() <= 10000, "来源渠道超过一万条，请调整迁移规模");
            return rows;
        }
    }

    /** 从同一只读来源连接读取渠道费率快照。 */
    public synchronized List<LegacyRate> readRates() {
        initialize();
        try (var session = factory.openSession()) {
            var mapper = session.getMapper(LegacyAssetMapper.class);
            requireIdentity(mapper);
            var rows = mapper.rates();
            AssetMigrationService.require(rows.size() <= 10000, "来源渠道费率超过一万条，请调整迁移规模");
            return rows;
        }
    }

    /** 从旧库只读连接中取得打款申请快照。 */
    public synchronized List<LegacyPayment> readPayments() {
        initialize();
        try (var session = factory.openSession()) {
            var mapper = session.getMapper(LegacyAssetMapper.class);
            requireIdentity(mapper);
            var rows = mapper.payments();
            AssetMigrationService.require(rows.size() <= 100000, "旧打款申请超过十万条，请拆分迁移范围");
            return rows;
        }
    }

    private void requireIdentity(LegacyAssetMapper mapper) {
        var identity = mapper.identity();
        AssetMigrationService.require(
                properties.getSourceUuid().equals(identity.serverUuid())
                        && properties.getSourceSchema().equals(identity.schemaName()),
                "来源实例或库名不符");
    }

    private void initialize() {
        properties.validateSource();
        if (factory != null) return;
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(properties.getSourceUrl());
        config.setUsername(properties.getSourceUsername());
        config.setPassword(properties.getSourcePassword());
        config.setReadOnly(true);
        config.setConnectionInitSql("SET SESSION TRANSACTION READ ONLY");
        config.setMaximumPoolSize(1);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(10000);
        config.setPoolName("legacy-asset-readonly");
        config.addDataSourceProperty("connectTimeout", "10000");
        config.addDataSourceProperty("socketTimeout", "60000");
        HikariDataSource candidate = new HikariDataSource(config);
        try (InputStream input =
                new ClassPathResource("mapper/migration/LegacyAssetMapper.xml").getInputStream()) {
            Configuration configuration =
                    new Configuration(
                            new Environment(
                                    "legacy-readonly", new JdbcTransactionFactory(), candidate));
            configuration.setDefaultStatementTimeout(60);
            new XMLMapperBuilder(
                            input, configuration, "legacy-assets", configuration.getSqlFragments())
                    .parse();
            factory = new SqlSessionFactoryBuilder().build(configuration);
            pool = candidate;
        } catch (Exception exception) {
            candidate.close();
            throw new IllegalStateException("来源读取组件初始化失败", exception);
        }
    }

    /** 关闭私有来源连接池。 */
    @PreDestroy
    public synchronized void close() {
        if (pool != null) pool.close();
    }
}

package com.adpulse.main.migration;

import com.adpulse.main.migration.AssetMigrationModels.Identity;
import com.adpulse.main.migration.AssetMigrationModels.Source;
import com.adpulse.main.migration.ChannelIncrementModels.LegacyChannel;
import com.adpulse.main.migration.ChannelIncrementModels.LegacyRate;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.LegacyPayment;
import java.util.List;

/** 仅由私有来源 SqlSession 使用，不注册主库 Mapper 代理。 */
public interface LegacyAssetMapper {
    /** 验证来源实例与库名。 */
    Identity identity();

    /** 单个一致性查询读取来源五字段及内部主键，设置规模上限。 */
    List<Source> snapshot();

    /** 读取老库全部渠道，供增量缺口扫描。 */
    List<LegacyChannel> channels();

    /** 读取老库全部渠道费率，执行时只写入所选渠道对应记录。 */
    List<LegacyRate> rates();

    /** 读取全部旧打款申请及人员、渠道显示快照。 */
    List<LegacyPayment> payments();
}

package com.adpulse.system.asset.lifecycle;

import java.time.LocalDateTime;

/**
 * 资产生命周期中的一条脱敏事件快照。
 *
 * <p>生命周期接口只暴露审计所需的人员、时间和来源标识；密码、令牌及原始资产明细始终留在资产服务内部。
 */
public record AssetLifecycleEvent(
        String eventType, String userId, String userName, LocalDateTime occurredAt) {

    /** 为使用区间聚合创建分配或释放事件。 */
    public static AssetLifecycleEvent usage(
            String eventType, String userId, String userName, LocalDateTime occurredAt) {
        return new AssetLifecycleEvent(eventType, userId, userName, occurredAt);
    }
}

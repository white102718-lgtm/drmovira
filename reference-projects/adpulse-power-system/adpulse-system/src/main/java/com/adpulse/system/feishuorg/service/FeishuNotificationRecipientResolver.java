package com.adpulse.system.feishuorg.service;

import com.adpulse.system.feishuorg.client.FeishuOrganizationClient;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationMapper;
import com.adpulse.system.feishuorg.model.FeishuApplicationConfig;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

/** 统一解析飞书通知收件人，并隔离测试环境的固定收件人策略。 */
@Component
public class FeishuNotificationRecipientResolver {
    private final FeishuOrganizationMapper organizationMapper;
    private final FeishuOrganizationClient organizationClient;
    private final String testRecipientPhone;
    private final String contentPrefix;

    public FeishuNotificationRecipientResolver(
            FeishuOrganizationMapper organizationMapper,
            FeishuOrganizationClient organizationClient,
            @Value("${adpulse.feishu.notification.test-recipient-phone:}")
                    String testRecipientPhone,
            @Value("${adpulse.feishu.notification.content-prefix:}") String contentPrefix) {
        this.organizationMapper = organizationMapper;
        this.organizationClient = organizationClient;
        this.testRecipientPhone = testRecipientPhone;
        this.contentPrefix = contentPrefix;
    }

    /**
     * 解析最终收件人。
     *
     * <p>测试环境配置固定手机号后，所有飞书通知只投递至该账号，避免测试消息发给真实业务参与人；生产环境未配置时保留原业务收件人。
     */
    public List<String> resolveOpenIds(List<Long> userIds) {
        if (StringUtils.hasText(testRecipientPhone)) {
            List<String> localOpenIds =
                    organizationMapper.findActiveFeishuOpenIdsByPhone(testRecipientPhone);
            return localOpenIds.isEmpty()
                    ? organizationClient.findOpenIdsByMobile(testRecipientPhone)
                    : localOpenIds;
        }
        return organizationMapper.findActiveFeishuOpenIds(
                userIds.stream().filter(userId -> userId > 0).distinct().toList());
    }

    /**
     * 解析 Mpower 机器人通知的收件人手机号。
     *
     * <p>Mpower 应用必须通过自身凭证把手机号转换为本应用的 open_id，不能复用组织同步应用保存的 open_id，否则飞书会以跨应用收件人拒绝投递。
     */
    public List<String> resolveRecipientPhones(List<Long> userIds) {
        if (StringUtils.hasText(testRecipientPhone)) {
            return List.of(testRecipientPhone);
        }
        return organizationMapper.findActiveUserPhones(
                userIds.stream().filter(userId -> userId > 0).distinct().toList());
    }

    /** 查询飞书应用凭证配置，供通知器获取租户令牌。 */
    public FeishuApplicationConfig findApplicationConfig() {
        return organizationMapper.findApplicationConfig();
    }

    /** 返回测试环境固定收件人手机号；生产环境为空。 */
    public String testRecipientPhone() {
        return testRecipientPhone;
    }

    /** 为测试环境通知添加可见标识，未配置前缀时不改变生产消息内容。 */
    public String decorateContent(String content) {
        return contentPrefix + content;
    }
}

package com.adpulse.system.dailyreport.service;

import com.adpulse.system.feishuorg.service.FeishuMessageNotifier;
import java.util.List;
import org.springframework.stereotype.Component;

/** 日报模块对公共飞书私聊通知能力的兼容封装。 */
@Component
public class FeishuDailyReportNotifier {
    private final FeishuMessageNotifier feishuMessageNotifier;

    public FeishuDailyReportNotifier(FeishuMessageNotifier feishuMessageNotifier) {
        this.feishuMessageNotifier = feishuMessageNotifier;
    }

    /** 飞书投递失败由公共通知器降级处理，不能回滚已保存的日报或站内通知。 */
    public void notifyRecipients(List<Long> userIds, String content) {
        feishuMessageNotifier.notifyUsers(userIds, content);
    }
}

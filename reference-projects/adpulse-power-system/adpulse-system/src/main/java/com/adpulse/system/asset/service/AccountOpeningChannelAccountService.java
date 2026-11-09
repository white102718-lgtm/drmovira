package com.adpulse.system.asset.service;

import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import org.springframework.stereotype.Service;

/** 广告户申请办理时同步广告账户的共享分配关系。 */
@Service
public class AccountOpeningChannelAccountService {
    private final DynamicAssetFlowMapper flowMapper;

    public AccountOpeningChannelAccountService(DynamicAssetFlowMapper flowMapper) {
        this.flowMapper = flowMapper;
    }

    /**
     * 锁定并分配申请办理环节选择的广告账户。
     *
     * <p>申请渠道只用于办理页默认筛选，不限制最终选择范围。广告账户允许跨渠道选择，也允许多个使用人同时使用。
     *
     * @param rawAccountIds 办理页选择的账户 ID，支持分号或换行分隔
     * @param applicationId 当前广告户申请 ID
     * @param assigneeId 账户实际使用人 ID
     * @param assigneeName 账户实际使用人姓名
     * @param operatorId 当前办理人 ID
     */
    public List<SelectedAccount> assignSelectedAccounts(
            String rawAccountIds,
            long applicationId,
            long assigneeId,
            String assigneeName,
            long operatorId) {
        if (applicationId <= 0) throw BusinessException.validation("广告户申请标识不合法");
        if (assigneeId <= 0 || Objects.toString(assigneeName, "").isBlank()) {
            throw BusinessException.validation("广告户申请缺少有效使用人");
        }
        List<String> selectedIds = accountIds(rawAccountIds);
        if (selectedIds.isEmpty()) {
            throw BusinessException.validation("请至少选择一个渠道账户");
        }

        List<SelectedAccount> accounts =
                flowMapper.lockActiveChannelAccounts(selectedIds).stream()
                        .map(
                                account ->
                                        new SelectedAccount(
                                                Objects.toString(account.get("accountId"), ""),
                                                Objects.toString(account.get("channelName"), "")))
                        .toList();
        if (accounts.size() != selectedIds.size()) {
            throw BusinessException.conflict("所选广告账户不存在，请刷新后重试");
        }
        List<String> accountIds = accounts.stream().map(SelectedAccount::accountId).toList();
        LinkedHashSet<String> assignedAccountIds =
                new LinkedHashSet<>(
                        flowMapper.findAssignedChannelAccountIds(accountIds, assigneeId));
        if (!assignedAccountIds.isEmpty()) {
            List<String> duplicateAccountIds =
                    accountIds.stream().filter(assignedAccountIds::contains).toList();
            throw BusinessException.conflict(
                    "以下广告账户已分配给申请人，请勿重复分配：" + String.join("、", duplicateAccountIds));
        }
        if (flowMapper.insertChannelAccountAssignments(
                        accountIds, applicationId, assigneeId, assigneeName.trim(), operatorId)
                != accountIds.size()) {
            throw BusinessException.conflict("渠道账户分配关系保存失败，请刷新后重试");
        }
        if (flowMapper.assignChannelAccounts(
                        accountIds, assigneeId, assigneeName.trim(), operatorId)
                != accountIds.size()) {
            throw BusinessException.conflict("部分渠道账户状态已变化，请刷新后重试");
        }
        return accounts;
    }

    /** 办理结果中用于审计展示的广告账户快照。 */
    public record SelectedAccount(String accountId, String channelName) {}

    private List<String> accountIds(String rawAccountIds) {
        LinkedHashSet<String> ids = new LinkedHashSet<>();
        for (String item : Objects.toString(rawAccountIds, "").split("[;\\n\\r]+")) {
            String id = item.trim();
            if (!id.isBlank()) ids.add(id);
        }
        return List.copyOf(ids);
    }
}

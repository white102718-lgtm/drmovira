package com.adpulse.main.task.service;

import com.adpulse.main.deliveryreport.DeliveryReportMapper;
import com.adpulse.main.integration.security.IntegrationSecretCipher;
import com.adpulse.main.task.dto.TaskRequests;
import com.adpulse.main.task.dto.TaskViews;
import com.adpulse.main.task.mapper.TaskMapper;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Locale;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

/** 根据当前投手负责的任务明细汇总 Doris 与 MySQL 日报数据。 */
@Service
public class TaskDeliverySourceService {
    private final TaskMapper taskMapper;
    private final DeliveryReportMapper reportMapper;
    private final TaskDeliverySourceProvider provider;
    private final IntegrationSecretCipher cipher;
    private final ObjectMapper json;

    public TaskDeliverySourceService(
            TaskMapper taskMapper,
            DeliveryReportMapper reportMapper,
            TaskDeliverySourceProvider provider,
            IntegrationSecretCipher cipher,
            ObjectMapper json) {
        this.taskMapper = taskMapper;
        this.reportMapper = reportMapper;
        this.provider = provider;
        this.cipher = cipher;
        this.json = json;
    }

    /** 日期为闭区间；缺省从计划开始日到今天。 */
    public TaskViews.DeliverySource query(Long taskId, LocalDate startDate, LocalDate endDate) {
        CurrentUser user = currentUser();
        var task = taskMapper.findTask(taskId);
        var detail = taskMapper.findDeliveryDetail(taskId);
        if (task == null || !"DELIVERY".equals(task.getTaskType()) || detail == null) {
            throw new TaskService.TaskException("投放任务不存在");
        }
        if (taskMapper.findActiveAllocationForOperator(taskId, user.userId()) == null) {
            throw new TaskService.TaskException("当前投手没有待交付的执行项");
        }
        String englishName = user.englishNickname();
        if (englishName == null || englishName.isBlank()) {
            throw new TaskService.TaskException("当前用户未配置 English Name");
        }
        LocalDate today = LocalDate.now();
        LocalDate plannedStart = detail.getPlannedStartAt().toLocalDate();
        LocalDate defaultStart = plannedStart.isAfter(today) ? today : plannedStart;
        LocalDate from = startDate == null ? defaultStart : startDate;
        LocalDate to = endDate == null ? today : endDate;
        if (from.isAfter(to) || to.isAfter(today)) {
            throw new TaskService.TaskException("请选择不超过今天的有效日期范围");
        }
        List<TaskRequests.DeliveryItem> ownedItems =
                decode(detail.getItemsCiphertext()).stream()
                        .filter(item -> user.userId().toString().equals(item.operatorId()))
                        .toList();
        if (ownedItems.isEmpty()) throw new TaskService.TaskException("未找到当前投手负责的投放明细");
        List<String> lineNames =
                ownedItems.stream()
                        .map(item -> item.agencyLineName().trim())
                        .distinct()
                        .toList();
        List<String> assignedPlatforms =
                ownedItems.stream()
                        .map(item -> item.platform().trim())
                        .distinct()
                        .toList();
        List<String> queryPlatforms =
                assignedPlatforms.stream()
                        .map(platform -> platform.toLowerCase(Locale.ROOT))
                        .distinct()
                        .toList();
        var facts =
                provider.query(
                        from,
                        to,
                        englishName.trim(),
                        task.getProjectName(),
                        lineNames,
                        queryPlatforms);
        BigDecimal daily =
                reportMapper.sumDailySpendForTask(
                        user.userId(), task.getProjectId(), lineNames, queryPlatforms, from, to);
        return new TaskViews.DeliverySource(
                from,
                to,
                assignedPlatforms,
                facts.accountIds(),
                facts.campaignIds(),
                facts.adsetIds(),
                facts.adIds(),
                facts.actualSpend(),
                daily == null ? BigDecimal.ZERO : daily);
    }

    private List<TaskRequests.DeliveryItem> decode(String ciphertext) {
        try {
            return json.readValue(
                    cipher.decrypt(ciphertext),
                    json.getTypeFactory()
                            .constructCollectionType(List.class, TaskRequests.DeliveryItem.class));
        } catch (JsonProcessingException exception) {
            throw new TaskService.TaskException("投放明细数据格式错误");
        }
    }

    private CurrentUser currentUser() {
        Object principal = SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (!(principal instanceof CurrentUser user)) {
            throw new TaskService.TaskException("当前会话未认证");
        }
        return user;
    }
}

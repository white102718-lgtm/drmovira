package com.adpulse.system.feedback.service;

import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.feedback.dto.FeedbackRequests;
import com.adpulse.system.feedback.dto.FeedbackViews;
import com.adpulse.system.feedback.mapper.FeedbackMapper;
import com.adpulse.system.feedback.model.Feedback;
import com.adpulse.system.feedback.model.FeedbackAttachment;
import com.adpulse.system.feedback.model.FeedbackUserSnapshot;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 产品反馈提交、诊断快照、附件绑定和管理端处理服务。 */
@Service
public class FeedbackService {
    public static final String MANAGE_AUTHORITY = "system:feedback:manage";

    private static final Set<String> CATEGORIES = Set.of("FEATURE", "BUG", "EXPERIENCE");
    private static final Set<String> STATUSES =
            Set.of("PENDING", "PROCESSING", "RESOLVED", "CLOSED");
    private static final Pattern BEARER_PATTERN =
            Pattern.compile("(?i)Bearer\\s+[A-Za-z0-9._~+/=-]+");
    private static final Pattern SENSITIVE_VALUE_PATTERN =
            Pattern.compile(
                    "(?i)((?:access_?token|api[_-]?key|authorization|cookie|credential|password|passwd|refresh_?token|secret|session)\\s*[:=]\\s*)[^,\\s}\\\"']+");

    private final FeedbackMapper mapper;
    private final ObjectMapper objectMapper;

    public FeedbackService(FeedbackMapper mapper, ObjectMapper objectMapper) {
        this.mapper = mapper;
        this.objectMapper = objectMapper;
    }

    /** 提交反馈，并在同一事务内校验和绑定当前用户上传的附件。 */
    @Transactional
    public FeedbackViews.Detail create(
            FeedbackRequests.Create request, String clientIp, String userAgent) {
        CurrentUser user = SecurityContextHelper.currentUser();
        FeedbackUserSnapshot account = mapper.findUserSnapshot(user.userId());
        if (account == null) throw BusinessException.notFound("提交账号");

        List<Long> fileIds = uniqueFileIds(request.attachmentFileIds());
        if (!fileIds.isEmpty()
                && mapper.findOwnedFileIds(fileIds, user.userId()).size() != fileIds.size()) {
            throw BusinessException.conflict("附件不存在、已删除或不属于当前账号");
        }

        Feedback feedback = new Feedback();
        feedback.setCategory(normalizeCategory(request.category()));
        feedback.setTitle(request.title().trim());
        feedback.setContent(request.content().trim());
        feedback.setStatus("PENDING");
        feedback.setSubmittedById(user.userId());
        feedback.setSubmittedByName(account.displayName());
        feedback.setSubmittedByUsername(textOrNull(account.username()));
        feedback.setClientIp(textOrNull(clientIp) == null ? "unknown" : limit(clientIp, 64));
        feedback.setUserAgent(limit(userAgent, 500));
        feedback.setDeviceType(
                request.diagnostics() == null
                        ? null
                        : limit(textOrNull(request.diagnostics().deviceType()), 20));
        feedback.setPageUrl(
                request.diagnostics() == null
                        ? null
                        : limit(textOrNull(request.diagnostics().pageUrl()), 1000));
        feedback.setDiagnosticJson(writeDiagnostics(request.diagnostics()));
        mapper.insertFeedback(feedback);
        if (!fileIds.isEmpty()) {
            mapper.insertAttachments(feedback.getId(), fileIds, user.userId());
        }
        return detail(feedback.getId());
    }

    /** 管理端按关键词、类型和状态分页查询反馈列表。 */
    public PageResult<FeedbackViews.ListItem> page(
            String keyword, String category, String status, int page, int pageSize) {
        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(pageSize, 1), 200);
        String normalizedKeyword = textOrNull(keyword);
        String normalizedCategory = optionalCategory(category);
        String normalizedStatus = optionalStatus(status);
        long total = mapper.countFeedbacks(normalizedKeyword, normalizedCategory, normalizedStatus);
        List<FeedbackViews.ListItem> items =
                mapper
                        .findFeedbacks(
                                normalizedKeyword,
                                normalizedCategory,
                                normalizedStatus,
                                (safePage - 1) * safeSize,
                                safeSize)
                        .stream()
                        .map(this::toListItem)
                        .toList();
        return new PageResult<>(items, total, safePage, safeSize);
    }

    /** 汇总全部有效反馈的处理状态，供管理列表快速判断待办规模。 */
    public FeedbackViews.Summary summary() {
        return new FeedbackViews.Summary(
                mapper.countFeedbacks(null, null, null),
                mapper.countFeedbacks(null, null, "PENDING"),
                mapper.countFeedbacks(null, null, "PROCESSING"),
                mapper.countFeedbacks(null, null, "RESOLVED"),
                mapper.countFeedbacks(null, null, "CLOSED"));
    }

    /** 查询反馈完整信息，包括附件和诊断数据。 */
    public FeedbackViews.Detail detail(Long id) {
        Feedback feedback = mapper.findFeedback(id);
        if (feedback == null) throw BusinessException.notFound("反馈");
        return toDetail(feedback, mapper.findAttachments(id));
    }

    /** 管理端更新反馈状态、负责人和处理说明。 */
    @Transactional
    public FeedbackViews.Detail updateStatus(Long id, FeedbackRequests.UpdateStatus request) {
        if (mapper.findFeedback(id) == null) throw BusinessException.notFound("反馈");
        CurrentUser user = SecurityContextHelper.currentUser();
        String status = normalizeStatus(request.status());
        String reply = textOrNull(request.adminReply());
        FeedbackUserSnapshot owner =
                request.ownerId() == null ? null : mapper.findUserSnapshot(request.ownerId());
        if (request.ownerId() != null && owner == null) {
            throw BusinessException.conflict("负责人不存在或已停用");
        }
        if (mapper.updateStatus(
                        id,
                        status,
                        reply,
                        request.ownerId(),
                        owner == null ? null : owner.displayName(),
                        user.userId(),
                        user.displayName())
                != 1) {
            throw BusinessException.conflict("反馈状态已变化，请刷新后重试");
        }
        return detail(id);
    }

    private FeedbackViews.ListItem toListItem(Feedback feedback) {
        return new FeedbackViews.ListItem(
                feedback.getId().toString(),
                feedback.getCategory(),
                feedback.getTitle(),
                feedback.getContent(),
                feedback.getStatus(),
                feedback.getSubmittedByName(),
                feedback.getSubmittedByUsername(),
                feedback.getClientIp(),
                feedback.getDeviceType(),
                feedback.getOwnerId() == null ? null : feedback.getOwnerId().toString(),
                feedback.getOwnerName(),
                feedback.getAttachmentCount() == null ? 0 : feedback.getAttachmentCount(),
                feedback.getCreatedAt(),
                feedback.getUpdatedAt());
    }

    private FeedbackViews.Detail toDetail(Feedback feedback, List<FeedbackAttachment> attachments) {
        return new FeedbackViews.Detail(
                feedback.getId().toString(),
                feedback.getCategory(),
                feedback.getTitle(),
                feedback.getContent(),
                feedback.getStatus(),
                feedback.getSubmittedById().toString(),
                feedback.getSubmittedByName(),
                feedback.getSubmittedByUsername(),
                feedback.getClientIp(),
                feedback.getUserAgent(),
                feedback.getDeviceType(),
                feedback.getPageUrl(),
                readDiagnostics(feedback.getDiagnosticJson()),
                feedback.getAdminReply(),
                feedback.getOwnerId() == null ? null : feedback.getOwnerId().toString(),
                feedback.getOwnerName(),
                feedback.getProcessedById() == null ? null : feedback.getProcessedById().toString(),
                feedback.getProcessedByName(),
                feedback.getProcessedAt(),
                attachments.stream()
                        .map(
                                attachment ->
                                        new FeedbackViews.Attachment(
                                                attachment.id().toString(),
                                                attachment.originalName(),
                                                attachment.mimeType(),
                                                attachment.fileSize(),
                                                attachment.sortOrder()))
                        .toList(),
                feedback.getCreatedAt(),
                feedback.getUpdatedAt());
    }

    private List<Long> uniqueFileIds(List<Long> fileIds) {
        if (fileIds == null || fileIds.isEmpty()) return List.of();
        LinkedHashSet<Long> unique = new LinkedHashSet<>();
        for (Long fileId : fileIds) {
            if (fileId == null || fileId <= 0) {
                throw BusinessException.validation("附件ID不正确");
            }
            unique.add(fileId);
        }
        if (unique.size() > 5) throw BusinessException.validation("最多上传5个附件");
        return new ArrayList<>(unique);
    }

    private String writeDiagnostics(FeedbackRequests.Diagnostics diagnostics) {
        if (diagnostics == null) return null;
        try {
            String json = objectMapper.writeValueAsString(sanitizeDiagnostics(diagnostics));
            if (json.length() > 250_000) {
                throw BusinessException.validation("诊断信息过大，请减少控制台记录后重试");
            }
            return json;
        } catch (JsonProcessingException exception) {
            throw BusinessException.validation("诊断信息格式不正确");
        }
    }

    /** 服务端再次脱敏客户端诊断，避免绕过前端后写入凭据或会话信息。 */
    private FeedbackRequests.Diagnostics sanitizeDiagnostics(
            FeedbackRequests.Diagnostics diagnostics) {
        List<FeedbackRequests.ConsoleEntry> consoleLogs =
                diagnostics.consoleLogs() == null
                        ? null
                        : diagnostics.consoleLogs().stream()
                                .map(
                                        entry ->
                                                new FeedbackRequests.ConsoleEntry(
                                                        entry.level(),
                                                        entry.timestamp(),
                                                        sanitizeSensitiveText(entry.message())))
                                .toList();
        return new FeedbackRequests.Diagnostics(
                diagnostics.appVersion(),
                sanitizeSensitiveText(diagnostics.pageUrl()),
                diagnostics.routeName(),
                diagnostics.language(),
                diagnostics.timezone(),
                diagnostics.deviceType(),
                diagnostics.operatingSystem(),
                diagnostics.browser(),
                diagnostics.screenResolution(),
                diagnostics.viewportSize(),
                diagnostics.devicePixelRatio(),
                diagnostics.hardwareConcurrency(),
                diagnostics.deviceMemory(),
                diagnostics.networkType(),
                consoleLogs);
    }

    private String sanitizeSensitiveText(String value) {
        if (value == null) return null;
        String redacted = BEARER_PATTERN.matcher(value).replaceAll("Bearer [已脱敏]");
        return SENSITIVE_VALUE_PATTERN.matcher(redacted).replaceAll("$1[已脱敏]");
    }

    private JsonNode readDiagnostics(String json) {
        if (json == null || json.isBlank()) return null;
        try {
            return objectMapper.readTree(json);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("反馈诊断数据无法解析", exception);
        }
    }

    private String normalizeCategory(String category) {
        String value = category == null ? "" : category.trim().toUpperCase(Locale.ROOT);
        if (!CATEGORIES.contains(value)) {
            throw BusinessException.validation("反馈类型不正确");
        }
        return value;
    }

    private String optionalCategory(String category) {
        return textOrNull(category) == null ? null : normalizeCategory(category);
    }

    private String normalizeStatus(String status) {
        String value = status == null ? "" : status.trim().toUpperCase(Locale.ROOT);
        if (!STATUSES.contains(value)) {
            throw BusinessException.validation("反馈状态不正确");
        }
        return value;
    }

    private String optionalStatus(String status) {
        return textOrNull(status) == null ? null : normalizeStatus(status);
    }

    private String textOrNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private String limit(String value, int maxLength) {
        String normalized = textOrNull(value);
        if (normalized == null) return null;
        return normalized.length() <= maxLength ? normalized : normalized.substring(0, maxLength);
    }
}

package com.adpulse.main.google.service;

import com.adpulse.main.google.client.GoogleProviderClient;
import com.adpulse.main.google.dto.GoogleDtos;
import com.adpulse.main.google.mapper.GoogleIntegrationMapper;
import com.adpulse.main.google.model.GoogleModels;
import com.adpulse.main.google.security.GoogleOAuthState;
import com.adpulse.main.integration.security.IntegrationSecretCipher;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Google OAuth账号、Drive/Sheets读取和映射任务服务。 */
@Service
public class GoogleIntegrationService {
    private final GoogleIntegrationMapper mapper;
    private final GoogleProviderClient provider;
    private final GoogleOAuthState oauthState;
    private final IntegrationSecretCipher cipher;
    private final ObjectMapper objectMapper;

    public GoogleIntegrationService(
            GoogleIntegrationMapper mapper,
            GoogleProviderClient provider,
            GoogleOAuthState oauthState,
            IntegrationSecretCipher cipher,
            ObjectMapper objectMapper) {
        this.mapper = mapper;
        this.provider = provider;
        this.oauthState = oauthState;
        this.cipher = cipher;
        this.objectMapper = objectMapper;
    }

    /** 查询全部Google账号及其映射。 */
    public List<GoogleDtos.Account> accounts() {
        return mapper.findAccounts().stream()
                .map(
                        account ->
                                new GoogleDtos.Account(
                                        account.getId().toString(),
                                        account.getEmail(),
                                        account.getPicture(),
                                        account.getAuthStatus(),
                                        account.getAuthorizedAt(),
                                        mapper.findMappingsByAccount(account.getId()).stream()
                                                .map(this::mappingView)
                                                .toList()))
                .toList();
    }

    /** 为当前用户生成签名OAuth授权地址。 */
    public String authorizeUrl() {
        return provider.authorizeUrl(oauthState.issue(actorId()));
    }

    /** 处理Google OAuth回调并以密文保存令牌。 */
    @Transactional
    public void oauthCallback(String code, String state) {
        Long actorId = oauthState.verify(state);
        var token = provider.exchange(code);
        var user = provider.userInfo(token.accessToken());
        if (user.subject().isBlank() || user.email().isBlank())
            throw new GoogleIntegrationException("Google账号资料不完整");
        GoogleModels.Account account = mapper.findAccountBySubject(user.subject());
        if (account == null) account = new GoogleModels.Account();
        account.setGoogleSubject(user.subject());
        account.setEmail(user.email());
        account.setPicture(user.picture());
        account.setAccessTokenCiphertext(cipher.encrypt(token.accessToken()));
        account.setRefreshTokenCiphertext(
                token.refreshToken().isBlank() ? null : cipher.encrypt(token.refreshToken()));
        account.setTokenExpiresAt(LocalDateTime.now().plusSeconds(token.expiresIn()));
        account.setAuthStatus(1);
        account.setAuthorizedAt(LocalDateTime.now());
        account.setUpdatedBy(actorId);
        if (account.getId() == null) {
            account.setCreatedBy(actorId);
            mapper.insertAccount(account);
        } else mapper.updateAccount(account);
    }

    /** 断开Google账号并停用其全部同步。 */
    @Transactional
    public void disconnect(Long id) {
        requireAccount(id);
        mapper.updateAccountStatus(id, 0, actorId());
    }

    /** 软删除Google账号及其全部映射。 */
    @Transactional
    public void deleteAccount(Long id) {
        requireAccount(id);
        long deletedAt = System.currentTimeMillis();
        Long actor = actorId();
        mapper.deleteMappingsByAccount(id, deletedAt, actor);
        mapper.deleteAccount(id, deletedAt, actor);
    }

    /** 查询账号Google Sheets文件。 */
    public List<GoogleDtos.DriveFile> files(Long accountId, String keyword) {
        return provider.files(accessToken(requireAccount(accountId)), keyword);
    }

    /** 查询Spreadsheet子表。 */
    public List<GoogleDtos.SheetTab> sheets(Long accountId, String fileId) {
        return provider.sheets(accessToken(requireAccount(accountId)), fileId);
    }

    /** 查询Sheet第一行字段。 */
    public List<String> columns(Long accountId, String fileId, String sheetName) {
        return provider.columns(accessToken(requireAccount(accountId)), fileId, sheetName);
    }

    /** 创建Google Sheets映射。 */
    @Transactional
    public String createMapping(GoogleDtos.MappingSave request) {
        requireAccount(request.googleAccountId());
        GoogleModels.Mapping item = mappingModel(null, request);
        item.setEnableFlag(1);
        item.setCreatedBy(actorId());
        item.setUpdatedBy(actorId());
        mapper.insertMapping(item);
        mapper.insertSyncJob(item.getId().toString(), item.getCreatedBy(), true);
        return item.getId().toString();
    }

    /** 查询映射详情。 */
    public GoogleDtos.Mapping mapping(Long id) {
        return mappingView(requireMapping(id));
    }

    /** 分页查询指定映射的同步结果。 */
    public GoogleDtos.SyncDataPage syncData(
            Long mappingId,
            String startDate,
            String endDate,
            String taskName,
            Integer page,
            Integer pageSize) {
        requireMapping(mappingId);
        int normalizedPage = page == null || page < 1 ? 1 : page;
        int normalizedPageSize = pageSize == null ? 20 : Math.max(1, Math.min(pageSize, 200));
        String normalizedTaskName = taskName == null ? null : taskName.trim();
        List<GoogleDtos.SyncData> items =
                mapper
                        .findSyncData(
                                mappingId,
                                startDate,
                                endDate,
                                normalizedTaskName,
                                (normalizedPage - 1) * normalizedPageSize,
                                normalizedPageSize)
                        .stream()
                        .map(
                                item ->
                                        new GoogleDtos.SyncData(
                                                item.getId().toString(),
                                                item.getStartDate(),
                                                item.getTaskName(),
                                                item.getSubtaskName(),
                                                item.getSpendAmount(),
                                                item.getReturnAmount(),
                                                item.getImpressions(),
                                                item.getClicks(),
                                                item.getRegistrations(),
                                                item.getPurchases(),
                                                item.getSubscriptions(),
                                                item.getMediaPlacement(),
                                                item.getUpdatedAt()))
                        .toList();
        long total = mapper.countSyncData(mappingId, startDate, endDate, normalizedTaskName);
        return new GoogleDtos.SyncDataPage(items, total, normalizedPage, normalizedPageSize);
    }

    /** 分页查询指定映射的同步任务执行日志。 */
    public GoogleDtos.SyncLogPage syncLogs(Long mappingId, Integer page, Integer pageSize) {
        requireMapping(mappingId);
        int normalizedPage = page == null || page < 1 ? 1 : page;
        int normalizedPageSize = pageSize == null ? 20 : Math.max(1, Math.min(pageSize, 100));
        List<GoogleDtos.SyncLog> items =
                mapper
                        .findSyncLogs(
                                mappingId.toString(),
                                (normalizedPage - 1) * normalizedPageSize,
                                normalizedPageSize)
                        .stream()
                        .map(
                                item ->
                                        new GoogleDtos.SyncLog(
                                                item.getId().toString(),
                                                isFullSync(item.getRequestPayload()),
                                                item.getStatus(),
                                                item.getErrorMessage(),
                                                item.getStartedAt(),
                                                item.getFinishedAt(),
                                                item.getCreatedAt()))
                        .toList();
        long total = mapper.countSyncLogs(mappingId.toString());
        return new GoogleDtos.SyncLogPage(items, total, normalizedPage, normalizedPageSize);
    }

    /** 更新Google Sheets映射。 */
    @Transactional
    public void updateMapping(Long id, GoogleDtos.MappingSave request) {
        GoogleModels.Mapping existing = requireMapping(id);
        requireAccount(request.googleAccountId());
        GoogleModels.Mapping item = mappingModel(id, request);
        item.setEnableFlag(existing.getEnableFlag());
        item.setUpdatedBy(actorId());
        mapper.updateMapping(item);
        if (mapper.countActiveSyncJobs(id.toString()) == 0)
            mapper.insertSyncJob(id.toString(), item.getUpdatedBy(), true);
    }

    /** 更新映射启停状态。 */
    @Transactional
    public void updateStatus(Long id, Integer enableFlag) {
        requireMapping(id);
        if (enableFlag == null || (enableFlag != 0 && enableFlag != 1))
            throw new GoogleIntegrationException("映射状态不合法");
        mapper.updateMappingStatus(id, enableFlag, actorId());
    }

    /** 软删除映射。 */
    @Transactional
    public void deleteMapping(Long id) {
        requireMapping(id);
        mapper.deleteMapping(id, System.currentTimeMillis(), actorId());
    }

    /** 将映射同步写入新服务任务队列。 */
    @Transactional
    public void enqueueSync(Long id) {
        GoogleModels.Mapping mapping = requireMapping(id);
        if (mapping.getEnableFlag() != 1) throw new GoogleIntegrationException("映射配置已停用");
        requireAccount(mapping.getGoogleAccountId());
        if (mapper.countActiveSyncJobs(id.toString()) == 0)
            mapper.insertSyncJob(id.toString(), actorId(), true);
    }

    /** 为后台同步任务取得有效访问令牌。 */
    public String accessTokenForSync(GoogleModels.Mapping mapping) {
        return accessToken(requireAccount(mapping.getGoogleAccountId()), mapping.getUpdatedBy());
    }

    private String accessToken(GoogleModels.Account account) {
        return accessToken(account, actorId());
    }

    private String accessToken(GoogleModels.Account account, Long actor) {
        if (account.getAuthStatus() != 1)
            throw new GoogleIntegrationException("Google账号授权已失效，请重新授权");
        if (account.getTokenExpiresAt() != null
                && account.getTokenExpiresAt().isAfter(LocalDateTime.now().plusMinutes(1)))
            return cipher.decrypt(account.getAccessTokenCiphertext());
        if (account.getRefreshTokenCiphertext() == null)
            throw new GoogleIntegrationException("Google刷新令牌不可用，请重新授权");
        var token = provider.refresh(cipher.decrypt(account.getRefreshTokenCiphertext()));
        account.setAccessTokenCiphertext(cipher.encrypt(token.accessToken()));
        account.setTokenExpiresAt(LocalDateTime.now().plusSeconds(token.expiresIn()));
        account.setAuthStatus(1);
        account.setAuthorizedAt(LocalDateTime.now());
        account.setUpdatedBy(actor);
        mapper.updateAccount(account);
        return token.accessToken();
    }

    private GoogleModels.Account requireAccount(Long id) {
        GoogleModels.Account account = mapper.findAccount(id);
        if (account == null) throw new GoogleIntegrationException("Google账号不存在");
        return account;
    }

    private GoogleModels.Mapping requireMapping(Long id) {
        GoogleModels.Mapping mapping = mapper.findMapping(id);
        if (mapping == null) throw new GoogleIntegrationException("Google映射配置不存在");
        return mapping;
    }

    private GoogleModels.Mapping mappingModel(Long id, GoogleDtos.MappingSave request) {
        GoogleModels.Mapping item = new GoogleModels.Mapping();
        item.setId(id);
        item.setGoogleAccountId(request.googleAccountId());
        item.setName(request.name().trim());
        item.setReportType(request.reportType());
        item.setSpreadsheetId(request.spreadsheetId().trim());
        item.setSpreadsheetName(request.spreadsheetName().trim());
        item.setSpreadsheetModifiedTime(request.spreadsheetModifiedTime());
        item.setSheetNames(json(request.sheetNames()));
        item.setFieldMappings(json(request.fieldMappings()));
        item.setSyncDirection(request.syncDirection());
        item.setConflictStrategy(request.conflictStrategy());
        item.setDateRangeType(request.dateRangeType());
        item.setDateRangeConfig(json(request.dateRangeConfig()));
        item.setSyncFrequency(request.syncFrequency());
        item.setSyncTime(request.syncTime());
        return item;
    }

    private GoogleDtos.Mapping mappingView(GoogleModels.Mapping item) {
        return new GoogleDtos.Mapping(
                item.getId().toString(),
                item.getGoogleAccountId().toString(),
                item.getName(),
                item.getReportType(),
                item.getSpreadsheetId(),
                item.getSpreadsheetName(),
                item.getSpreadsheetModifiedTime(),
                item.getSheetNames(),
                item.getFieldMappings(),
                item.getSyncDirection(),
                item.getConflictStrategy(),
                item.getDateRangeType(),
                item.getDateRangeConfig(),
                item.getSyncFrequency(),
                item.getSyncTime(),
                item.getEnableFlag(),
                item.getLastSyncTime());
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new GoogleIntegrationException("映射配置序列化失败");
        }
    }

    private boolean isFullSync(String payload) {
        if (payload == null || payload.isBlank()) return true;
        try {
            return objectMapper.readTree(payload).path("fullSync").asBoolean(true);
        } catch (JsonProcessingException exception) {
            return true;
        }
    }

    private Long actorId() {
        Object principal = SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (principal instanceof CurrentUser currentUser) return currentUser.userId();
        throw new GoogleIntegrationException("登录状态无效");
    }

    /** 可直接展示的Google数据集成业务异常。 */
    public static class GoogleIntegrationException extends RuntimeException {
        /** 创建Google数据集成业务异常。 */
        public GoogleIntegrationException(String message) {
            super(message);
        }
    }
}

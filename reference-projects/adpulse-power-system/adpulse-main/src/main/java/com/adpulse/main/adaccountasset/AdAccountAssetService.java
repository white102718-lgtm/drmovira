package com.adpulse.main.adaccountasset;

import static com.adpulse.main.adaccountasset.AdAccountAssetRequests.ImportItem;
import static com.adpulse.main.adaccountasset.AdAccountAssetRequests.Save;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.Account;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.AccountAttribute;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.Assignment;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.ImportFailure;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.ImportResult;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.LifecycleChangeValue;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.LifecycleDetail;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.LifecycleEvent;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.LifecycleFieldChange;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.LifecycleValueReference;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.Page;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.UsagePeriod;

import com.adpulse.main.adaccountasset.AdAccountAssetModels.ActiveUser;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAsset;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAssetAssignment;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAssetChangeEvent;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.UserDepartment;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.AccountAttributeSave;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.AssignmentReplace;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.AssignmentSave;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.BatchUpdate;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.BatchUpdateField;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.PageFilter;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.SpreadsheetUpdate;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.SpreadsheetSaveResult;
import com.adpulse.main.channel.mapper.ChannelMapper;
import com.adpulse.main.channel.model.ChannelModels;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Date;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.bson.Document;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 广告账户统一台账服务。
 *
 * <p>账户集合是 MongoDB {@code fb_ad_accounts} 与 MySQL {@code ad_account_asset} 的并集；名称优先使用
 * MongoDB，平台缺少名称时允许 Excel 导入值兜底；平台状态和账户日限额只认 MongoDB，业务资料只认资产表，使用人只认 {@code
 * ad_account_asset_assignment}。
 */
@Service
public class AdAccountAssetService {
    private static final ZoneId BEIJING = ZoneId.of("Asia/Shanghai");
    private static final String BAN_EVENT_COLLECTION = "fb_ad_account_ban_events";
    private static final int MAX_PAGE_SIZE = 1000;
    private static final String INVENTORY_STATUS_ASSIGNED = "ASSIGNED";
    private static final String INVENTORY_STATUS_AVAILABLE = "AVAILABLE";
    private static final String INVENTORY_STATUS_DISABLED = "DISABLED";
    private static final String INVENTORY_STATUS_RETURN_PENDING = "RETURN_PENDING";
    private static final Set<String> INVENTORY_STATUSES =
            Set.of(
                    INVENTORY_STATUS_ASSIGNED,
                    INVENTORY_STATUS_AVAILABLE,
                    INVENTORY_STATUS_DISABLED,
                    INVENTORY_STATUS_RETURN_PENDING);
    private static final String UPDATE_SOURCE_EXCEL_IMPORT = "EXCEL_IMPORT";
    private static final String UPDATE_SOURCE_MANUAL_EDIT = "MANUAL_EDIT";
    private static final String UPDATE_SOURCE_BATCH_EDIT = "BATCH_EDIT";
    private static final String UPDATE_SOURCE_EXCEL_BATCH = "EXCEL_BATCH";
    private static final String UPDATE_SOURCE_MANUAL_CREATE = "MANUAL_CREATE";
    private static final Pattern USAGE_USER_SEPARATOR = Pattern.compile("[、,，;；]");
    public static final String UPDATE_SOURCE_CHANNEL_IMPORT = "CHANNEL_IMPORT";
    public static final String UPDATE_SOURCE_CHANNEL_MANUAL = "CHANNEL_MANUAL";
    public static final String UPDATE_SOURCE_FEISHU_SYNC = "FEISHU_SYNC";
    public static final String UPDATE_SOURCE_MONGO_SYNC = "MONGO_SYNC";
    private static final ObjectMapper AUDIT_JSON = new ObjectMapper();
    private final String collection;
    private final MongoTemplate mongoTemplate;
    private final AdAccountAssetMapper assetMapper;
    private final AdAccountAssetAssignmentMapper assignmentMapper;
    private final AccountAttributeMapper accountAttributeMapper;
    private final AdAccountUserMapper adAccountUserMapper;
    private final ChannelMapper channelMapper;

    public AdAccountAssetService(
            MongoTemplate mongoTemplate,
            AdAccountAssetMapper assetMapper,
            AdAccountAssetAssignmentMapper assignmentMapper,
            AccountAttributeMapper accountAttributeMapper,
            AdAccountUserMapper adAccountUserMapper,
            ChannelMapper channelMapper,
            @Value("${adpulse.mongo.account.collection:fb_ad_accounts}") String collection) {
        this.mongoTemplate = mongoTemplate;
        this.assetMapper = assetMapper;
        this.assignmentMapper = assignmentMapper;
        this.accountAttributeMapper = accountAttributeMapper;
        this.adAccountUserMapper = adAccountUserMapper;
        this.channelMapper = channelMapper;
        this.collection = collection;
    }

    /** 按账户 ID、名称或资产资料分页查询统一台账，主表筛选在分页前完成。 */
    public Page list(String keyword, PageFilter rawFilter, int rawPage, int rawPageSize) {
        int page = Math.max(rawPage, 1);
        int pageSize = Math.min(Math.max(rawPageSize, 1), MAX_PAGE_SIZE);
        String normalizedKeyword = text(keyword);
        PageFilter filter = normalizePageFilter(rawFilter);
        long total = assetMapper.countPage(normalizedKeyword, filter);
        long offset = (long) (page - 1) * pageSize;
        List<AdAccountAsset> assets =
                assetMapper.findPage(normalizedKeyword, filter, offset, pageSize);
        List<String> accountIds = assets.stream().map(AdAccountAsset::getAccountId).toList();
        return new Page(
                viewsFromAssets(assets, mongoDocumentsByAccountIds(accountIds)),
                total,
                page,
                pageSize);
    }

    /** 按分页列表的相同筛选和排序一次返回全部账户，避免客户端逐页重复查询。 */
    public List<Account> listAll(String keyword, PageFilter rawFilter) {
        String normalizedKeyword = text(keyword);
        PageFilter filter = normalizePageFilter(rawFilter);
        List<AdAccountAsset> assets = assetMapper.findAllByFilter(normalizedKeyword, filter);
        List<String> accountIds = assets.stream().map(AdAccountAsset::getAccountId).toList();
        return viewsFromAssets(assets, mongoDocumentsByAccountIds(accountIds));
    }

    /** 统一清理多值查询参数，并对库存状态执行与写入接口相同的枚举校验。 */
    private PageFilter normalizePageFilter(PageFilter source) {
        PageFilter filter = source == null ? PageFilter.EMPTY : source;
        return new PageFilter(
                texts(filter.accountNames()),
                texts(filter.accountIds()),
                integers(filter.accountStatuses()),
                texts(filter.accountTypes()),
                texts(filter.accountAttributes()),
                texts(filter.channelNames()),
                texts(filter.managedBms()),
                texts(filter.managedBmIds()),
                texts(filter.backupManagedBms()),
                texts(filter.backupManagedBmIds()),
                texts(filter.timezones()),
                texts(filter.cardStations()),
                texts(filter.cardNumbers()),
                inventoryStatuses(filter.inventoryStatuses()),
                texts(filter.usageUsers()),
                texts(filter.usageDepartments()),
                texts(filter.inventoryAssigneeNames()));
    }

    private List<Integer> integers(List<Integer> values) {
        if (values == null) return null;
        List<Integer> normalized = values.stream().filter(Objects::nonNull).distinct().toList();
        return normalized.isEmpty() ? null : normalized;
    }

    private List<String> texts(List<String> values) {
        if (values == null) return null;
        List<String> normalized =
                values.stream().map(this::text).filter(Objects::nonNull).distinct().toList();
        return normalized.isEmpty() ? null : normalized;
    }

    private List<String> inventoryStatuses(List<String> values) {
        List<String> normalized = texts(values);
        return normalized == null ? null : normalized.stream().map(this::inventoryStatus).toList();
    }

    /** 按账户 ID 批量读取统一台账；资产表独有的账户同样会返回。 */
    public List<Account> listByAccountIds(List<String> accountIds) {
        Set<String> ids = new java.util.LinkedHashSet<>();
        for (String accountId : accountIds) {
            String normalized = normalizeAccountId(accountId);
            if (normalized != null) ids.add(normalized);
        }
        if (ids.isEmpty()) return List.of();

        List<String> normalizedIds = new ArrayList<>(ids);
        List<AdAccountAsset> assets = assetMapper.findByAccountIds(normalizedIds);
        Map<String, Document> platformById = mongoDocumentsByAccountIds(normalizedIds);
        List<AccountSource> sources = new ArrayList<>();
        for (String accountId : normalizedIds) {
            AdAccountAsset asset = newestByAccountId(assets, accountId);
            Document platformAccount = platformById.get(accountId);
            if (asset != null || platformAccount != null) {
                sources.add(new AccountSource(asset, platformAccount));
            }
        }
        sources.sort(
                Comparator.comparing(
                                (AccountSource source) ->
                                        source.asset() == null
                                                ? LocalDateTime.MIN
                                                : source.asset().getUpdatedAt(),
                                Comparator.nullsFirst(Comparator.naturalOrder()))
                        .reversed());
        return views(sources);
    }

    /** 渠道管理按渠道名称精准查询资产表中的账户。 */
    public List<Account> listByChannelName(String channelName) {
        String normalized = text(channelName);
        if (normalized == null) return List.of();
        List<AdAccountAsset> assets = assetMapper.findByChannelName(normalized);
        return viewsFromAssets(assets, mongoDocumentsById());
    }

    /** 人工更新业务资料；账户名称和平台状态始终忽略客户端输入。 */
    @Transactional
    public Account update(String accountId, Save request) {
        String normalizedId = requiredAccountId(accountId);
        boolean created = assetMapper.findByAccountId(normalizedId) == null;
        Account before = accountOrNull(normalizedId);
        Account after = save(normalizedId, request, UPDATE_SOURCE_MANUAL_EDIT);
        if (created) {
            recordStocked(after, UPDATE_SOURCE_MANUAL_CREATE, false);
        } else {
            recordUpdate(before, after, UPDATE_SOURCE_MANUAL_EDIT);
        }
        return after;
    }

    /** 按字段白名单批量更新账户资料。所有目标、引用数据和使用人会在写入前完成校验，任一账户失败会整体回滚。 */
    @Transactional
    public List<Account> batchUpdate(BatchUpdate request) {
        return batchUpdate(request, UPDATE_SOURCE_BATCH_EDIT);
    }

    private List<Account> batchUpdate(BatchUpdate request, String auditSource) {
        List<String> accountIds =
                request.accountIds().stream().map(this::requiredAccountId).distinct().toList();
        Map<String, Account> beforeById = accountsById(listByAccountIds(accountIds));
        Set<BatchUpdateField> fields = EnumSet.copyOf(request.changedFields());
        BatchUpdateContext context = validateBatchUpdate(request, fields);

        Map<String, AdAccountAsset> existingByAccountId = new HashMap<>();
        for (AdAccountAsset asset : assetMapper.findByAccountIds(accountIds)) {
            AdAccountAsset current = existingByAccountId.get(asset.getAccountId());
            if (current == null
                    || (asset.getUpdatedAt() != null
                            && (current.getUpdatedAt() == null
                                    || asset.getUpdatedAt().isAfter(current.getUpdatedAt())))) {
                existingByAccountId.put(asset.getAccountId(), asset);
            }
        }
        Map<String, Document> platformByAccountId = mongoDocumentsByAccountIds(accountIds);
        List<BatchUpdateTarget> targets = new ArrayList<>();
        Set<String> createdAccountIds = new HashSet<>();
        for (String accountId : accountIds) {
            AdAccountAsset existing = existingByAccountId.get(accountId);
            Document platformAccount = platformByAccountId.get(accountId);
            if (existing == null && platformAccount == null) {
                throw new AdAccountAssetException("广告账户资产不存在：" + accountId);
            }
            targets.add(new BatchUpdateTarget(accountId, existing, platformAccount));
            if (existing == null) createdAccountIds.add(accountId);
        }

        Long operatorId = actorId();
        for (BatchUpdateTarget target : targets) {
            AdAccountAsset asset = copyForBatchUpdate(target, operatorId);
            applyBatchUpdate(asset, request, fields, context.channel());
            if (target.existing() != null
                    && target.platformAccount() != null
                    && !asset.getAccountName().equals(target.existing().getAccountName())) {
                assetMapper.updatePlatformSnapshotByAccountId(asset);
            }
            assetMapper.upsert(asset);
        }
        if (fields.contains(BatchUpdateField.INVENTORY_STATUS)) {
            List<Long> userIds = request.userIds() == null ? List.of() : request.userIds();
            AssignmentReplace assignmentRequest =
                    new AssignmentReplace(
                            userIds, UPDATE_SOURCE_MANUAL_EDIT, context.inventoryStatus());
            for (String accountId : accountIds) {
                replaceAssignments(accountId, assignmentRequest);
            }
        }
        List<Account> updated = listByAccountIds(accountIds);
        for (Account after : updated) {
            if (createdAccountIds.contains(after.accountId())) {
                recordStocked(after, auditSource, false);
            } else {
                recordUpdate(beforeById.get(after.accountId()), after, auditSource);
            }
        }
        return updated;
    }

    /** 原子保存广告账户电子表格；使用人整体替换，并由是否存在使用人推导库存状态。 */
    @Transactional
    public SpreadsheetSaveResult spreadsheetUpdate(SpreadsheetUpdate request) {
        List<String> accountIds =
                request.rows().stream().map(row -> requiredAccountId(row.accountId())).toList();
        if (new HashSet<>(accountIds).size() != accountIds.size()) {
            throw new AdAccountAssetException("同一次保存中不能包含重复的账户 ID");
        }
        int createdCount = 0;
        int updatedCount = 0;
        for (var row : request.rows()) {
            String accountId = requiredAccountId(row.accountId());
            if (assetMapper.findByAccountId(accountId) == null) {
                save(accountId, row.toSave(), UPDATE_SOURCE_EXCEL_BATCH);
                List<Long> userIds =
                        row.userIds() == null
                                ? List.of()
                                : row.userIds().stream().distinct().toList();
                Account after =
                        replaceAssignments(
                                accountId,
                                new AssignmentReplace(
                                        userIds,
                                        UPDATE_SOURCE_EXCEL_BATCH,
                                        userIds.isEmpty()
                                                ? INVENTORY_STATUS_AVAILABLE
                                                : INVENTORY_STATUS_ASSIGNED));
                recordStocked(after, UPDATE_SOURCE_EXCEL_BATCH, false);
                createdCount++;
            } else {
                batchUpdate(row.toSpreadsheetBatchUpdate(), UPDATE_SOURCE_EXCEL_BATCH);
                updatedCount++;
            }
        }
        return new SpreadsheetSaveResult(createdCount, updatedCount, listByAccountIds(accountIds));
    }

    /** 表格导入允许创建资产表独有账户；平台名称优先，平台缺少名称时使用导入名称兜底。 */
    @Transactional
    public ImportResult importAccounts(List<ImportItem> items) {
        List<ImportFailure> failures = new ArrayList<>();
        Map<String, List<ActiveUser>> activeUsersByName = activeUsersByName();
        int successCount = 0;
        for (ImportItem item : items) {
            try {
                validateImportItem(item);
                String normalizedId = requiredAccountId(item.accountId());
                List<ActiveUser> usageUsers =
                        item.usageUsers() == null
                                ? null
                                : resolveImportedUsageUsers(item.usageUsers(), activeUsersByName);
                boolean created = assetMapper.findByAccountId(normalizedId) == null;
                Account before = accountOrNull(normalizedId);
                Account after = save(normalizedId, importedSave(item), UPDATE_SOURCE_EXCEL_IMPORT);
                if (created) {
                    recordStocked(after, UPDATE_SOURCE_EXCEL_IMPORT, false);
                } else if (before != null) {
                    recordUpdate(before, after, UPDATE_SOURCE_EXCEL_IMPORT);
                }
                if (usageUsers != null) {
                    List<Long> usageUserIds =
                            usageUsers.stream().map(ActiveUser::getUserId).toList();
                    replaceAssignments(
                            normalizedId,
                            new AssignmentReplace(
                                    usageUserIds,
                                    UPDATE_SOURCE_EXCEL_IMPORT,
                                    usageUserIds.isEmpty()
                                            ? INVENTORY_STATUS_AVAILABLE
                                            : INVENTORY_STATUS_ASSIGNED),
                            usageUsers.stream()
                                    .collect(
                                            Collectors.toMap(
                                                    ActiveUser::getUserId,
                                                    user -> user,
                                                    (first, ignored) -> first,
                                                    LinkedHashMap::new)));
                }
                successCount++;
            } catch (AdAccountAssetException exception) {
                failures.add(
                        new ImportFailure(item.line(), item.accountId(), exception.getMessage()));
            } catch (DuplicateKeyException exception) {
                failures.add(new ImportFailure(item.line(), item.accountId(), "广告账户保存冲突，请重新导入"));
            }
        }
        return new ImportResult(items.size(), successCount, failures);
    }

    /** 文件与兼容 JSON 导入必须共用服务端字段和字典校验，不能依赖浏览器预检。 */
    private void validateImportItem(ImportItem item) {
        requireMaxLength("账户 ID", item.accountId(), 100);
        requireMaxLength("账户名称", item.accountName(), 255);
        requireMaxLength("账户类型", item.accountType(), 100);
        requireMaxLength("账户属性", item.accountAttribute(), 100);
        requireMaxLength("渠道 ID", item.channelId(), 20);
        requireMaxLength("所属渠道", item.channelName(), 255);
        requireMaxLength("管理 BM", item.managedBm(), 500);
        requireMaxLength("管理 BM ID", item.managedBmId(), 100);
        requireMaxLength("备份 BM", item.backupManagedBm(), 500);
        requireMaxLength("备份 BM ID", item.backupManagedBmId(), 100);
        requireMaxLength("时区", item.timezone(), 100);
        requireMaxLength("卡台", item.cardStation(), 100);
        requireMaxLength("卡号", item.cardNumber(), 100);
        requireMaxLength("备注", item.remark(), 500);
        requireMaxLength("使用人", item.usageUsers(), 2000);
        String accountType = text(item.accountType());
        if (accountType != null && channelMapper.findAccountTypeByName(accountType) == null) {
            throw new AdAccountAssetException("账户类型不存在：" + accountType);
        }
    }

    private Save importedSave(ImportItem item) {
        return new Save(
                item.accountName(),
                item.accountType(),
                item.accountAttribute(),
                resolveImportedChannelId(item),
                item.managedBm(),
                item.managedBmId(),
                item.backupManagedBm(),
                item.backupManagedBmId(),
                item.timezone(),
                item.cardStation(),
                item.cardNumber(),
                item.remark());
    }

    /** 名称来自模板下拉且优先于可能残留的渠道 ID，最终仍转换为稳定 ID 保存。 */
    private String resolveImportedChannelId(ImportItem item) {
        String channelName = text(item.channelName());
        if (channelName != null) {
            var channel = channelMapper.findChannelByName(channelName);
            if (channel == null) {
                throw new AdAccountAssetException("渠道不存在或已停用：" + channelName);
            }
            return String.valueOf(channel.getId());
        }
        return text(item.channelId());
    }

    private void requireMaxLength(String label, String value, int maxLength) {
        if (value != null && value.length() > maxLength) {
            throw new AdAccountAssetException(label + "不能超过 " + maxLength + " 字");
        }
    }

    /** 使用人名称可能重名；导入只能接受唯一命中的有效用户，禁止猜测关联对象。 */
    private List<ActiveUser> resolveImportedUsageUsers(
            String rawUsageUsers, Map<String, List<ActiveUser>> activeUsersByName) {
        String normalized = text(rawUsageUsers);
        if (normalized == null) return List.of();

        Set<String> names = new java.util.LinkedHashSet<>();
        for (String item : USAGE_USER_SEPARATOR.split(normalized)) {
            String name = text(item);
            if (name != null) names.add(name);
        }
        List<ActiveUser> users = new ArrayList<>();
        for (String name : names) {
            List<ActiveUser> matches = activeUsersByName.getOrDefault(name, List.of());
            if (matches.isEmpty()) {
                throw new AdAccountAssetException("使用人不存在或已停用：" + name);
            }
            if (matches.size() > 1) {
                throw new AdAccountAssetException("使用人姓名重复，无法唯一匹配：" + name);
            }
            users.add(matches.getFirst());
        }
        return users;
    }

    private Map<String, List<ActiveUser>> activeUsersByName() {
        Map<String, List<ActiveUser>> result = new LinkedHashMap<>();
        for (ActiveUser user : adAccountUserMapper.findAllActiveUsers()) {
            String displayName = text(user.getDisplayName());
            if (displayName == null || user.getUserId() == null) continue;
            result.computeIfAbsent(displayName, ignored -> new ArrayList<>()).add(user);
        }
        return result;
    }

    /** 渠道新增或绑定账户时写入统一台账；返回值用于调用方在完成后续分配后补记入库快照。 */
    @Transactional
    public boolean upsertChannelAsset(AdAccountAsset asset) {
        boolean created = assetMapper.findByAccountId(asset.getAccountId()) == null;
        assetMapper.upsert(asset);
        return created;
    }

    /** 渠道事务完成全部字段和使用人写入后，为首次建档账户补记一次不可变入库快照。 */
    @Transactional
    public void recordChannelStocked(String accountId, String updateSource) {
        Account account = accountOrNull(requiredAccountId(accountId));
        if (account != null) recordStocked(account, updateSource, false);
    }

    /** 飞书首次建档记录系统入库快照；已有记录只按原同步规则更新，不重复生成入库事件。 */
    @Transactional
    public void syncFeishuAsset(AdAccountAsset asset) {
        boolean created = assetMapper.findByAccountId(asset.getAccountId()) == null;
        assetMapper.upsertFromFeishu(asset);
        if (created) {
            recordStocked(accountOrNull(asset.getAccountId()), UPDATE_SOURCE_FEISHU_SYNC, true);
        }
    }

    /** MongoDB 平台首次建档记录系统入库快照，已有记录继续使用安全的平台字段更新。 */
    @Transactional
    public void syncPlatformAsset(AdAccountAsset snapshot) {
        boolean created = false;
        if (assetMapper.updatePlatformSnapshotByAccountId(snapshot) == 0) {
            created = assetMapper.upsertPlatformSnapshot(snapshot) == 1;
        }
        if (created) {
            recordStocked(accountOrNull(snapshot.getAccountId()), UPDATE_SOURCE_MONGO_SYNC, true);
        }
    }

    /** 清除人工锁定，允许下一轮飞书任务继续更新业务资料。 */
    @Transactional
    public Account resumeAutomaticSync(String accountId) {
        String normalizedId = requiredAccountId(accountId);
        if (assetMapper.resetManualUpdate(normalizedId, actorId()) == 0) {
            throw new AdAccountAssetException("广告账户资产不存在");
        }
        return listByAccountIds(List.of(normalizedId)).stream()
                .findFirst()
                .orElseThrow(() -> new AdAccountAssetException("广告账户资产不存在"));
    }

    /** 为广告账户幂等增加使用人；重复办理只会恢复或刷新同一关系。 */
    @Transactional
    public List<Account> assign(AssignmentSave request) {
        Long operatorId = actorId();
        List<String> accountIds =
                request.accountIds().stream().map(this::requiredAccountId).distinct().toList();
        for (String accountId : accountIds) {
            AdAccountAsset asset = assetMapper.findByAccountId(accountId);
            if (asset == null) {
                throw new AdAccountAssetException("广告账户资产不存在：" + accountId);
            }
            AdAccountAssetAssignment assignment = new AdAccountAssetAssignment();
            assignment.setAdAccountAssetId(asset.getId());
            assignment.setUserId(request.userId());
            assignment.setUserName(request.userName().trim());
            assignment.setUsageTeamName(departmentName(request.userId()));
            assignment.setIsPrimary(request.primary());
            assignment.setAssignmentStatus("ACTIVE");
            assignment.setAssignmentSource(request.source().trim());
            assignment.setApplicationId(request.applicationId());
            assignment.setCreatedBy(operatorId);
            assignment.setUpdatedBy(operatorId);
            assignmentMapper.upsert(assignment);
            assetMapper.updateInventoryStatus(asset.getId(), INVENTORY_STATUS_ASSIGNED, operatorId);
        }
        return listByAccountIds(accountIds);
    }

    /** 原子替换资产管理中维护的使用人，移除关系以 RELEASED 状态保留历史。 */
    @Transactional
    public Account replaceAssignments(String accountId, AssignmentReplace request) {
        return replaceAssignments(accountId, request, Map.of());
    }

    private Account replaceAssignments(
            String accountId, AssignmentReplace request, Map<Long, ActiveUser> preloadedUsers) {
        String normalizedId = requiredAccountId(accountId);
        AdAccountAsset asset = assetMapper.findByAccountId(normalizedId);
        if (asset == null) throw new AdAccountAssetException("广告账户资产不存在");
        Long operatorId = actorId();
        String inventoryStatus = inventoryStatus(request.inventoryStatus());
        if (INVENTORY_STATUS_RETURN_PENDING.equals(inventoryStatus)) {
            throw new AdAccountAssetException("待回收状态请在资源回收流程中变更");
        }
        Set<Long> requestedUserIds = new java.util.LinkedHashSet<>(request.userIds());
        if (INVENTORY_STATUS_ASSIGNED.equals(inventoryStatus) && requestedUserIds.isEmpty()) {
            throw new AdAccountAssetException("已分配状态必须指定至少一位使用人");
        }
        if (!INVENTORY_STATUS_ASSIGNED.equals(inventoryStatus)) requestedUserIds.clear();
        Map<Long, ActiveUser> resolvedUsers = new LinkedHashMap<>();
        for (Long userId : requestedUserIds) {
            ActiveUser user = preloadedUsers.get(userId);
            if (user == null) {
                String userName = adAccountUserMapper.findDisplayName(userId);
                if (userName == null || userName.isBlank()) {
                    throw new AdAccountAssetException("使用人不存在或已停用：" + userId);
                }
                user = new ActiveUser();
                user.setUserId(userId);
                user.setDisplayName(userName);
                user.setDepartmentName(departmentName(userId));
            }
            resolvedUsers.put(userId, user);
        }
        List<AdAccountAssetAssignment> current =
                assignmentMapper.findActiveByAssetIds(List.of(asset.getId()));
        for (AdAccountAssetAssignment assignment : current) {
            if (!requestedUserIds.contains(assignment.getUserId())) {
                assignmentMapper.release(
                        asset.getId(),
                        assignment.getUserId(),
                        operatorId,
                        System.currentTimeMillis());
            }
        }
        int index = 0;
        for (Long userId : requestedUserIds) {
            ActiveUser user = resolvedUsers.get(userId);
            AdAccountAssetAssignment assignment = new AdAccountAssetAssignment();
            assignment.setAdAccountAssetId(asset.getId());
            assignment.setUserId(userId);
            assignment.setUserName(user.getDisplayName());
            assignment.setUsageTeamName(user.getDepartmentName());
            assignment.setIsPrimary(index++ == 0);
            assignment.setAssignmentStatus("ACTIVE");
            assignment.setAssignmentSource(request.source());
            assignment.setCreatedBy(operatorId);
            assignment.setUpdatedBy(operatorId);
            assignmentMapper.upsert(assignment);
        }
        assetMapper.updateInventoryStatus(asset.getId(), inventoryStatus, operatorId);
        return listByAccountIds(List.of(normalizedId)).stream()
                .findFirst()
                .orElseThrow(() -> new AdAccountAssetException("广告账户资产不存在"));
    }

    /** 查询当前登录用户正在使用的广告账户。 */
    public List<Account> listMine() {
        List<Long> assetIds = assignmentMapper.findActiveAssetIdsByUserId(actorId());
        if (assetIds.isEmpty()) return List.of();
        List<AdAccountAsset> assets = assetMapper.findByIds(assetIds);
        List<String> accountIds = assets.stream().map(AdAccountAsset::getAccountId).toList();
        return viewsFromAssets(assets, mongoDocumentsByAccountIds(accountIds));
    }

    /** 返回账户自身台账和全部使用区间；跨服务的申请审批事件由前端向 system 服务并行查询后合并。 */
    public LifecycleDetail lifecycle(String accountId) {
        String normalizedId = requiredAccountId(accountId);
        AdAccountAsset asset = assetMapper.findByAccountId(normalizedId);
        if (asset == null) throw new AdAccountAssetException("广告账户资产不存在");
        Account account =
                listByAccountIds(List.of(normalizedId)).stream()
                        .findFirst()
                        .orElseThrow(() -> new AdAccountAssetException("广告账户资产不存在"));
        List<AdAccountAssetAssignment> assignments =
                assignmentMapper.findHistoryByAssetId(asset.getId());
        List<UsagePeriod> periods =
                assignments.stream()
                        .map(
                                assignment ->
                                        new UsagePeriod(
                                                String.valueOf(assignment.getUserId()),
                                                assignment.getUserName(),
                                                value(assignment.getUsageTeamName()),
                                                assignment.getAssignedAt(),
                                                assignment.getReleasedAt(),
                                                assignment.getReleasedAt() == null
                                                        ? "ACTIVE"
                                                        : "RELEASED",
                                                assignment.getApplicationId() == null
                                                        ? null
                                                        : String.valueOf(
                                                                assignment.getApplicationId()),
                                                assignment.getAssignmentSource()))
                        .toList();
        List<LifecycleEvent> events = new ArrayList<>();
        assignments.forEach(
                assignment -> {
                    events.add(
                            new LifecycleEvent(
                                    "assigned-" + assignment.getId(),
                                    "ASSIGNED",
                                    "ASSIGNED",
                                    historicalUserName(assignment.getCreatedBy(), "系统"),
                                    assignment.getUserName(),
                                    value(assignment.getUsageTeamName()),
                                    assignment.getApplicationId() == null
                                            ? null
                                            : String.valueOf(assignment.getApplicationId()),
                                    assignment.getAssignedAt()));
                    if (assignment.getReleasedAt() != null) {
                        events.add(
                                new LifecycleEvent(
                                        "released-" + assignment.getId(),
                                        "RELEASED",
                                        "AVAILABLE",
                                        historicalUserName(assignment.getUpdatedBy(), "系统"),
                                        assignment.getUserName(),
                                        value(assignment.getUsageTeamName()),
                                        assignment.getApplicationId() == null
                                                ? null
                                                : String.valueOf(assignment.getApplicationId()),
                                        assignment.getReleasedAt()));
                    }
                });
        events.addAll(banEvents(normalizedId, asset.getCreatedAt()));
        boolean hasPersistedStockedEvent = false;
        for (AdAccountAssetChangeEvent changeEvent :
                assetMapper.findChangeEventsByAssetId(asset.getId())) {
            String eventType =
                    text(changeEvent.getEventType()) == null
                            ? "UPDATED"
                            : changeEvent.getEventType();
            hasPersistedStockedEvent |= "STOCKED".equals(eventType);
            events.add(
                    new LifecycleEvent(
                            eventType.toLowerCase(Locale.ROOT) + "-" + changeEvent.getId(),
                            eventType,
                            account.inventoryStatus(),
                            changeEvent.getActorName(),
                            null,
                            null,
                            null,
                            changeEvent.getOccurredAt(),
                            "STOCKED".equals(eventType) ? "资产已入库" : "资产资料已更新",
                            null,
                            null,
                            changeEvent.getUpdateSource(),
                            readChanges(changeEvent.getChangesJson())));
        }
        if (!hasPersistedStockedEvent) {
            events.add(
                    new LifecycleEvent(
                            "stocked-" + asset.getId(),
                            "STOCKED",
                            asset.getInventoryStatus(),
                            historicalUserName(asset.getCreatedBy(), "系统"),
                            null,
                            null,
                            null,
                            asset.getCreatedAt()));
        }
        events.sort(Comparator.comparing(LifecycleEvent::occurredAt).reversed());
        return new LifecycleDetail(account, periods, events);
    }

    /** 查询同步任务确认的“非 2 → 2”状态变化，并作为 Facebook 封户事件加入资产生命周期。 */
    private List<LifecycleEvent> banEvents(String accountId, LocalDateTime stockedAt) {
        Criteria criteria =
                Criteria.where("account_id")
                        .in(accountId, "act_" + accountId)
                        .and("current_status")
                        .in(2, "2");
        if (stockedAt != null) {
            criteria.and("detected_at").gte(Date.from(stockedAt.atZone(BEIJING).toInstant()));
        }
        Query query =
                Query.query(criteria).with(Sort.by(Sort.Direction.DESC, "detected_at", "_id"));
        return mongoTemplate.find(query, Document.class, BAN_EVENT_COLLECTION).stream()
                .map(this::banEvent)
                .filter(java.util.Objects::nonNull)
                .toList();
    }

    private LifecycleEvent banEvent(Document document) {
        LocalDateTime occurredAt = localDateTime(document, "detected_at", "created_at");
        if (occurredAt == null) return null;
        Integer previousStatus = integer(document, "previous_status");
        Integer currentStatus = integer(document, "current_status");
        Document details =
                new Document("previousStatus", previousStatus)
                        .append("currentStatus", currentStatus)
                        .append("disableReason", document.get("disable_reason"))
                        .append("source", text(string(document, "source")));
        return new LifecycleEvent(
                "facebook-ban-" + string(document, "_id"),
                "FACEBOOK_ACCOUNT_BANNED",
                "DISABLED",
                null,
                null,
                null,
                null,
                occurredAt,
                "Facebook 广告账户状态变为封户",
                details.toJson(),
                "FACEBOOK_BAN_EVENT");
    }

    private LocalDateTime localDateTime(Document document, String... names) {
        for (String name : names) {
            Object value = document.get(name);
            if (value instanceof Date date) {
                return LocalDateTime.ofInstant(date.toInstant(), BEIJING);
            }
        }
        return null;
    }

    /** 生命周期必须展示真实操作者；旧数据缺少用户时使用明确的系统兜底。 */
    private String historicalUserName(Long userId, String fallback) {
        if (userId == null) return fallback;
        String userName = adAccountUserMapper.findHistoricalDisplayName(userId);
        return userName == null || userName.isBlank() ? fallback : userName;
    }

    private Account accountOrNull(String accountId) {
        return listByAccountIds(List.of(accountId)).stream().findFirst().orElse(null);
    }

    private Map<String, Account> accountsById(List<Account> accounts) {
        Map<String, Account> result = new HashMap<>();
        for (Account account : accounts) result.put(account.accountId(), account);
        return result;
    }

    /** 按最终持久化视图计算差异；空值是合法的新值，只有归一化后相同才忽略。 */
    private void recordUpdate(Account before, Account after, String updateSource) {
        if (before == null || after == null) return;
        List<LifecycleFieldChange> changes = accountChanges(before, after);
        if (changes.isEmpty()) return;
        AdAccountAsset persisted = assetMapper.findByAccountId(after.accountId());
        if (persisted == null) return;
        Long operatorId = actorId();
        AdAccountAssetChangeEvent event = new AdAccountAssetChangeEvent();
        event.setAdAccountAssetId(persisted.getId());
        event.setAccountId(after.accountId());
        event.setEventType("UPDATED");
        event.setUpdateSource(updateSource);
        event.setActorId(operatorId);
        event.setActorName(historicalUserName(operatorId, "系统"));
        try {
            event.setChangesJson(AUDIT_JSON.writeValueAsString(changes));
        } catch (Exception exception) {
            throw new AdAccountAssetException("资料更新审计序列化失败");
        }
        assetMapper.insertChangeEvent(event);
    }

    /** 首次建档只写一条 STOCKED 事件，快照使用最终持久化视图且忽略空字段。 */
    private void recordStocked(Account account, String updateSource, boolean systemActor) {
        if (account == null) return;
        AdAccountAsset persisted = assetMapper.findByAccountId(account.accountId());
        if (persisted == null
                || assetMapper.countChangeEventsByAssetIdAndType(persisted.getId(), "STOCKED") > 0)
            return;
        List<LifecycleFieldChange> changes = accountInitialChanges(account);
        Long operatorId = systemActor ? null : actorIdOrNull();
        AdAccountAssetChangeEvent event = new AdAccountAssetChangeEvent();
        event.setAdAccountAssetId(persisted.getId());
        event.setAccountId(account.accountId());
        event.setEventType("STOCKED");
        event.setUpdateSource(updateSource);
        event.setActorId(operatorId);
        event.setActorName(systemActor ? "系统" : historicalUserName(operatorId, "系统"));
        try {
            event.setChangesJson(AUDIT_JSON.writeValueAsString(changes));
        } catch (Exception exception) {
            throw new AdAccountAssetException("入库资料快照序列化失败");
        }
        assetMapper.insertChangeEvent(event);
    }

    List<LifecycleFieldChange> accountInitialChanges(Account account) {
        List<LifecycleFieldChange> changes = new ArrayList<>();
        LifecycleChangeValue empty = textValue(null);
        addChange(changes, "accountId", "账户 ID", empty, textValue(account.accountId()));
        addChange(changes, "accountName", "账户名称", empty, textValue(account.accountName()));
        addChange(
                changes,
                "accountStatus",
                "平台状态",
                empty,
                platformStatusValue(account.accountStatus()));
        addChange(
                changes, "inventoryStatus", "库存状态", empty, statusValue(account.inventoryStatus()));
        addChange(changes, "accountType", "账户类型", empty, accountTypeValue(account.accountType()));
        addChange(
                changes,
                "accountAttribute",
                "账户属性",
                empty,
                accountAttributeValue(account.accountAttribute()));
        addChange(
                changes,
                "channel",
                "渠道",
                empty,
                referenceValue(account.channelId(), account.channelName()));
        addChange(
                changes,
                "managedBm",
                "管理 BM",
                empty,
                pairedValue(account.managedBmId(), account.managedBm()));
        addChange(
                changes,
                "backupManagedBm",
                "备用管理 BM",
                empty,
                pairedValue(account.backupManagedBmId(), account.backupManagedBm()));
        addChange(changes, "timezone", "时区", empty, textValue(account.timezone()));
        addChange(changes, "cardStation", "卡台", empty, textValue(account.cardStation()));
        addChange(changes, "cardNumber", "卡号", empty, textValue(account.cardNumber()));
        addChange(changes, "remark", "备注", empty, textValue(account.remark()));
        addChange(changes, "usageUsers", "使用人", empty, usersValue(account.assignments()));
        addChange(changes, "usageTeams", "使用团队", empty, textValue(account.usageDepartmentName()));
        return changes;
    }

    List<LifecycleFieldChange> accountChanges(Account before, Account after) {
        List<LifecycleFieldChange> changes = new ArrayList<>();
        addChange(
                changes,
                "accountType",
                "账户类型",
                accountTypeValue(before.accountType()),
                accountTypeValue(after.accountType()));
        addChange(
                changes,
                "accountAttribute",
                "账户属性",
                accountAttributeValue(before.accountAttribute()),
                accountAttributeValue(after.accountAttribute()));
        addChange(
                changes,
                "channel",
                "渠道",
                referenceValue(before.channelId(), before.channelName()),
                referenceValue(after.channelId(), after.channelName()));
        addChange(
                changes,
                "managedBm",
                "管理 BM",
                pairedValue(before.managedBmId(), before.managedBm()),
                pairedValue(after.managedBmId(), after.managedBm()));
        addChange(
                changes,
                "backupManagedBm",
                "备用管理 BM",
                pairedValue(before.backupManagedBmId(), before.backupManagedBm()),
                pairedValue(after.backupManagedBmId(), after.backupManagedBm()));
        addChange(
                changes,
                "timezone",
                "时区",
                textValue(before.timezone()),
                textValue(after.timezone()));
        addChange(
                changes,
                "cardStation",
                "卡台",
                textValue(before.cardStation()),
                textValue(after.cardStation()));
        addChange(
                changes,
                "cardNumber",
                "卡号",
                textValue(before.cardNumber()),
                textValue(after.cardNumber()));
        addChange(changes, "remark", "备注", textValue(before.remark()), textValue(after.remark()));
        addChange(
                changes,
                "inventoryStatus",
                "库存状态",
                statusValue(before.inventoryStatus()),
                statusValue(after.inventoryStatus()));
        addChange(
                changes,
                "usageUsers",
                "使用人",
                usersValue(before.assignments()),
                usersValue(after.assignments()));
        addChange(
                changes,
                "usageTeams",
                "使用团队",
                textValue(before.usageDepartmentName()),
                textValue(after.usageDepartmentName()));
        return changes;
    }

    private void addChange(
            List<LifecycleFieldChange> changes,
            String key,
            String label,
            LifecycleChangeValue before,
            LifecycleChangeValue after) {
        if (!Objects.equals(before, after)) {
            changes.add(new LifecycleFieldChange(key, label, before, after));
        }
    }

    private LifecycleChangeValue textValue(String display) {
        return new LifecycleChangeValue(text(display), List.of(), false);
    }

    private LifecycleChangeValue referenceValue(String id, String name) {
        String normalizedId = text(id);
        String normalizedName = text(name);
        List<LifecycleValueReference> references =
                normalizedId == null && normalizedName == null
                        ? List.of()
                        : List.of(new LifecycleValueReference(normalizedId, normalizedName));
        return new LifecycleChangeValue(normalizedName, references, false);
    }

    private LifecycleChangeValue pairedValue(String id, String name) {
        return referenceValue(id, name);
    }

    private LifecycleChangeValue accountTypeValue(String name) {
        String normalized = text(name);
        ChannelModels.AccountType type =
                normalized == null ? null : channelMapper.findAccountTypeByName(normalized);
        return referenceValue(type == null ? null : String.valueOf(type.getId()), normalized);
    }

    private LifecycleChangeValue accountAttributeValue(String name) {
        String normalized = text(name);
        var attribute = normalized == null ? null : accountAttributeMapper.findByName(normalized);
        return referenceValue(
                attribute == null ? null : String.valueOf(attribute.getId()), normalized);
    }

    private LifecycleChangeValue statusValue(String status) {
        String normalized = text(status);
        String label =
                switch (normalized == null ? "" : normalized) {
                    case INVENTORY_STATUS_ASSIGNED -> "已分配";
                    case INVENTORY_STATUS_AVAILABLE -> "可用";
                    case INVENTORY_STATUS_DISABLED -> "已停用";
                    case INVENTORY_STATUS_RETURN_PENDING -> "待回收";
                    default -> normalized;
                };
        return referenceValue(normalized, label);
    }

    private LifecycleChangeValue platformStatusValue(Integer status) {
        if (status == null) return textValue(null);
        String code = String.valueOf(status);
        String label =
                switch (status) {
                    case 1 -> "正常";
                    case 2 -> "已禁用";
                    case 3 -> "未结算";
                    case 7 -> "待审核";
                    case 8 -> "待结算";
                    case 9 -> "宽限期";
                    case 100 -> "待关闭";
                    case 101 -> "已关闭";
                    case 201 -> "任意有效状态";
                    case 202 -> "任意关闭状态";
                    default -> "未知";
                };
        return referenceValue(code, label);
    }

    private LifecycleChangeValue usersValue(List<Assignment> assignments) {
        List<LifecycleValueReference> references =
                assignments.stream()
                        .map(
                                item ->
                                        new LifecycleValueReference(
                                                item.userId(), text(item.userName())))
                        .sorted(
                                Comparator.comparing(
                                        LifecycleValueReference::id,
                                        Comparator.nullsFirst(String::compareTo)))
                        .toList();
        String display =
                String.join(
                        "、",
                        references.stream()
                                .map(LifecycleValueReference::name)
                                .filter(Objects::nonNull)
                                .toList());
        return new LifecycleChangeValue(text(display), references, false);
    }

    private List<LifecycleFieldChange> readChanges(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            return AUDIT_JSON.readValue(json, new TypeReference<List<LifecycleFieldChange>>() {});
        } catch (Exception ignored) {
            return List.of();
        }
    }

    /** 渠道管理移除账户时仅解除渠道归属，全局资产和使用历史继续保留。 */
    @Transactional
    public void detachChannel(String accountId) {
        String normalizedId = requiredAccountId(accountId);
        if (assetMapper.clearChannel(normalizedId, actorId()) == 0) {
            throw new AdAccountAssetException("广告账户资产不存在");
        }
    }

    private Account save(String accountId, Save request, String updateSource) {
        String normalizedId = requiredAccountId(accountId);
        AdAccountAsset existing = assetMapper.findByAccountId(normalizedId);
        Document platformAccount =
                mongoTemplate.findOne(queryByAccountId(normalizedId), Document.class, collection);
        validateAccountAttribute(request, existing == null ? null : existing.getAccountAttribute());

        if (existing != null && platformAccount != null) {
            String currentPlatformName = text(platformName(platformAccount));
            if (currentPlatformName != null
                    && !currentPlatformName.equals(existing.getAccountName())) {
                AdAccountAsset platformSnapshot = new AdAccountAsset();
                platformSnapshot.setAccountId(normalizedId);
                platformSnapshot.setAccountName(currentPlatformName);
                platformSnapshot.setAccountStatus(
                        integer(platformAccount, "account_status", "status"));
                assetMapper.updatePlatformSnapshotByAccountId(platformSnapshot);
                existing.setAccountName(currentPlatformName);
            }
        }

        Long operatorId = actorId();
        AdAccountAsset asset = new AdAccountAsset();
        asset.setAccountId(normalizedId);
        asset.setAccountName(
                resolveSavedAccountName(platformAccount, existing, request, updateSource));
        asset.setAccountStatus(
                platformAccount == null
                        ? existing == null ? null : existing.getAccountStatus()
                        : integer(platformAccount, "account_status", "status"));
        asset.setAccountType(text(request.accountType()));
        asset.setAccountAttribute(text(request.accountAttribute()));
        applyChannel(asset, request.channelId());
        asset.setManagedBm(text(request.managedBm()));
        asset.setManagedBmId(text(request.managedBmId()));
        asset.setBackupManagedBm(text(request.backupManagedBm()));
        asset.setBackupManagedBmId(text(request.backupManagedBmId()));
        asset.setTimezone(text(request.timezone()));
        asset.setCardStation(text(request.cardStation()));
        asset.setCardNumber(text(request.cardNumber()));
        asset.setRemark(text(request.remark()));
        asset.setDeliveryDate(existing == null ? null : existing.getDeliveryDate());
        asset.setIsManuallyUpdated(true);
        asset.setManuallyUpdatedAt(LocalDateTime.now());
        asset.setManuallyUpdatedBy(operatorId);
        asset.setLastMongoSyncAt(
                platformAccount == null
                        ? existing == null ? null : existing.getLastMongoSyncAt()
                        : LocalDateTime.now());
        asset.setUpdateSource(updateSource);
        asset.setCreatedBy(operatorId);
        asset.setUpdatedBy(operatorId);
        assetMapper.upsert(asset);
        return listByAccountIds(List.of(normalizedId)).stream()
                .filter(account -> account.accountName().equals(asset.getAccountName()))
                .findFirst()
                .orElseGet(() -> view(asset, platformAccount, List.of(), Map.of()));
    }

    /** 平台名称始终优先；仅 Excel 导入可在平台名称缺失时提供名称，空白导入值不会清除已有快照。 */
    private String resolveSavedAccountName(
            Document platformAccount, AdAccountAsset existing, Save request, String updateSource) {
        String currentPlatformName =
                platformAccount == null ? null : text(platformName(platformAccount));
        if (currentPlatformName != null) return currentPlatformName;

        if (UPDATE_SOURCE_EXCEL_IMPORT.equals(updateSource)
                || UPDATE_SOURCE_EXCEL_BATCH.equals(updateSource)) {
            String importedName = text(request.accountName());
            if (importedName != null) return importedName;
        }
        return existing == null ? "" : value(existing.getAccountName());
    }

    private BatchUpdateContext validateBatchUpdate(
            BatchUpdate request, Set<BatchUpdateField> fields) {
        if (fields.isEmpty()) throw new AdAccountAssetException("请至少选择一个要修改的字段");
        if (fields.contains(BatchUpdateField.ACCOUNT_ATTRIBUTE)) {
            String accountAttribute = text(request.accountAttribute());
            if (accountAttribute != null
                    && accountAttributeMapper.findByName(accountAttribute) == null) {
                throw new AdAccountAssetException("账户属性不存在：" + accountAttribute);
            }
        }
        ChannelModels.Channel channel =
                fields.contains(BatchUpdateField.CHANNEL_ID)
                        ? batchChannel(request.channelId())
                        : null;
        String batchInventoryStatus = null;
        if (fields.contains(BatchUpdateField.INVENTORY_STATUS)) {
            if (text(request.inventoryStatus()) == null) {
                throw new AdAccountAssetException("请选择库存状态");
            }
            batchInventoryStatus = inventoryStatus(request.inventoryStatus());
            if (INVENTORY_STATUS_RETURN_PENDING.equals(batchInventoryStatus)) {
                throw new AdAccountAssetException("待回收状态请在资源回收流程中变更");
            }
            if (INVENTORY_STATUS_ASSIGNED.equals(batchInventoryStatus)
                    && (!fields.contains(BatchUpdateField.USAGE_USER_IDS)
                            || request.userIds() == null
                            || request.userIds().isEmpty())) {
                throw new AdAccountAssetException("已分配状态必须指定至少一位使用人");
            }
        }
        if (fields.contains(BatchUpdateField.USAGE_USER_IDS)) {
            if (!fields.contains(BatchUpdateField.INVENTORY_STATUS)
                    || !INVENTORY_STATUS_ASSIGNED.equals(batchInventoryStatus)) {
                throw new AdAccountAssetException("修改使用人时必须同时将库存状态设为已分配");
            }
            for (Long userId : new java.util.LinkedHashSet<>(request.userIds())) {
                String userName = adAccountUserMapper.findDisplayName(userId);
                if (userName == null || userName.isBlank()) {
                    throw new AdAccountAssetException("使用人不存在或已停用：" + userId);
                }
            }
        }
        return new BatchUpdateContext(channel, batchInventoryStatus);
    }

    private ChannelModels.Channel batchChannel(String channelIdValue) {
        String normalizedChannelId = text(channelIdValue);
        if (normalizedChannelId == null) return null;
        Long channelId;
        try {
            channelId = Long.valueOf(normalizedChannelId);
        } catch (NumberFormatException exception) {
            throw new AdAccountAssetException("渠道ID格式错误");
        }
        ChannelModels.Channel channel = channelMapper.findChannel(channelId);
        if (channel == null || !Integer.valueOf(1).equals(channel.getStatus())) {
            throw new AdAccountAssetException("渠道不存在或已停用");
        }
        return channel;
    }

    private AdAccountAsset copyForBatchUpdate(BatchUpdateTarget target, Long operatorId) {
        AdAccountAsset existing = target.existing();
        Document platformAccount = target.platformAccount();
        AdAccountAsset asset = new AdAccountAsset();
        asset.setId(existing == null ? null : existing.getId());
        asset.setAccountId(target.accountId());
        asset.setAccountName(
                platformAccount == null
                        ? existing == null ? "" : existing.getAccountName()
                        : platformName(platformAccount));
        asset.setAccountStatus(
                platformAccount == null
                        ? existing == null ? null : existing.getAccountStatus()
                        : integer(platformAccount, "account_status", "status"));
        asset.setAccountType(existing == null ? null : existing.getAccountType());
        asset.setAccountAttribute(existing == null ? null : existing.getAccountAttribute());
        asset.setChannelId(existing == null ? null : existing.getChannelId());
        asset.setChannelName(existing == null ? null : existing.getChannelName());
        asset.setManagedBm(existing == null ? null : existing.getManagedBm());
        asset.setManagedBmId(existing == null ? null : existing.getManagedBmId());
        asset.setBackupManagedBm(existing == null ? null : existing.getBackupManagedBm());
        asset.setBackupManagedBmId(existing == null ? null : existing.getBackupManagedBmId());
        asset.setTimezone(existing == null ? null : existing.getTimezone());
        asset.setCardStation(existing == null ? null : existing.getCardStation());
        asset.setCardNumber(existing == null ? null : existing.getCardNumber());
        asset.setRemark(existing == null ? null : existing.getRemark());
        asset.setIsManuallyUpdated(true);
        asset.setManuallyUpdatedAt(LocalDateTime.now());
        asset.setManuallyUpdatedBy(operatorId);
        asset.setLastMongoSyncAt(
                platformAccount == null
                        ? existing == null ? null : existing.getLastMongoSyncAt()
                        : LocalDateTime.now());
        asset.setLastFeishuSyncAt(existing == null ? null : existing.getLastFeishuSyncAt());
        asset.setUpdateSource(UPDATE_SOURCE_MANUAL_EDIT);
        asset.setCreatedBy(existing == null ? operatorId : existing.getCreatedBy());
        asset.setUpdatedBy(operatorId);
        return asset;
    }

    private void applyBatchUpdate(
            AdAccountAsset asset,
            BatchUpdate request,
            Set<BatchUpdateField> fields,
            ChannelModels.Channel channel) {
        if (fields.contains(BatchUpdateField.ACCOUNT_TYPE))
            asset.setAccountType(text(request.accountType()));
        if (fields.contains(BatchUpdateField.ACCOUNT_ATTRIBUTE)) {
            asset.setAccountAttribute(text(request.accountAttribute()));
        }
        if (fields.contains(BatchUpdateField.CHANNEL_ID)) {
            if (channel == null) {
                asset.setChannelId(null);
                asset.setChannelName(null);
            } else {
                asset.setChannelId(channel.getId());
                asset.setChannelName(channel.getChannelName());
            }
        }
        if (fields.contains(BatchUpdateField.MANAGED_BM))
            asset.setManagedBm(text(request.managedBm()));
        if (fields.contains(BatchUpdateField.MANAGED_BM_ID)) {
            asset.setManagedBmId(text(request.managedBmId()));
        }
        if (fields.contains(BatchUpdateField.BACKUP_MANAGED_BM)) {
            asset.setBackupManagedBm(text(request.backupManagedBm()));
        }
        if (fields.contains(BatchUpdateField.BACKUP_MANAGED_BM_ID)) {
            asset.setBackupManagedBmId(text(request.backupManagedBmId()));
        }
        if (fields.contains(BatchUpdateField.TIMEZONE)) asset.setTimezone(text(request.timezone()));
        if (fields.contains(BatchUpdateField.CARD_STATION)) {
            asset.setCardStation(text(request.cardStation()));
        }
        if (fields.contains(BatchUpdateField.CARD_NUMBER)) {
            asset.setCardNumber(text(request.cardNumber()));
        }
        if (fields.contains(BatchUpdateField.REMARK)) asset.setRemark(text(request.remark()));
    }

    private List<Account> unionAccounts() {
        List<Document> platformAccounts = mongoTemplate.findAll(Document.class, collection);
        List<AdAccountAsset> assets = assetMapper.findAll();
        Map<String, Document> platformByIdentity = new LinkedHashMap<>();
        Map<String, Document> platformById = new HashMap<>();
        for (Document document : platformAccounts) {
            String accountId = platformId(document);
            if (accountId == null) continue;
            String accountName = platformName(document);
            platformByIdentity.put(identity(accountId, accountName), document);
            platformById.put(accountId, document);
        }

        Map<String, AdAccountAsset> assetByIdentity = new LinkedHashMap<>();
        for (AdAccountAsset asset : assets) {
            assetByIdentity.put(identity(asset.getAccountId(), asset.getAccountName()), asset);
        }

        List<AccountSource> sources = new ArrayList<>();
        Set<Long> consumedAssetIds = new HashSet<>();
        for (Map.Entry<String, Document> entry : platformByIdentity.entrySet()) {
            Document document = entry.getValue();
            AdAccountAsset asset = assetByIdentity.get(entry.getKey());
            if (asset == null) asset = newestByAccountId(assets, platformId(document));
            if (asset != null) consumedAssetIds.add(asset.getId());
            sources.add(new AccountSource(asset, document));
        }
        for (AdAccountAsset asset : assets) {
            if (!consumedAssetIds.contains(asset.getId())) {
                sources.add(new AccountSource(asset, platformById.get(asset.getAccountId())));
            }
        }
        sources.sort(
                Comparator.comparing(
                                (AccountSource source) ->
                                        source.asset() == null
                                                ? LocalDateTime.MIN
                                                : source.asset().getUpdatedAt(),
                                Comparator.nullsFirst(Comparator.naturalOrder()))
                        .reversed());
        return views(sources);
    }

    private List<Account> viewsFromAssets(
            List<AdAccountAsset> assets, Map<String, Document> platformDocuments) {
        List<AccountSource> sources =
                assets.stream()
                        .map(
                                asset ->
                                        new AccountSource(
                                                asset, platformDocuments.get(asset.getAccountId())))
                        .toList();
        return views(sources);
    }

    private List<Account> views(List<AccountSource> sources) {
        List<Long> assetIds =
                sources.stream()
                        .map(AccountSource::asset)
                        .filter(java.util.Objects::nonNull)
                        .map(AdAccountAsset::getId)
                        .toList();
        Map<Long, List<AdAccountAssetAssignment>> assignmentsByAsset = new HashMap<>();
        if (!assetIds.isEmpty()) {
            for (AdAccountAssetAssignment assignment :
                    assignmentMapper.findActiveByAssetIds(assetIds)) {
                assignmentsByAsset
                        .computeIfAbsent(
                                assignment.getAdAccountAssetId(), ignored -> new ArrayList<>())
                        .add(assignment);
            }
        }
        List<Long> userIds =
                assignmentsByAsset.values().stream()
                        .flatMap(List::stream)
                        .map(AdAccountAssetAssignment::getUserId)
                        .filter(Objects::nonNull)
                        .distinct()
                        .toList();
        Map<Long, String> departmentNamesByUserId = new HashMap<>();
        if (!userIds.isEmpty()) {
            for (UserDepartment department : adAccountUserMapper.findCurrentDepartments(userIds)) {
                departmentNamesByUserId.put(
                        department.getUserId(), value(department.getDepartmentName()));
            }
        }
        return sources.stream()
                .map(
                        source ->
                                view(
                                        source.asset(),
                                        source.platformAccount(),
                                        source.asset() == null
                                                ? List.of()
                                                : assignmentsByAsset.getOrDefault(
                                                        source.asset().getId(), List.of()),
                                        departmentNamesByUserId))
                .toList();
    }

    private Account view(
            AdAccountAsset asset,
            Document platformAccount,
            List<AdAccountAssetAssignment> assignmentModels,
            Map<Long, String> departmentNamesByUserId) {
        String accountId = asset == null ? platformId(platformAccount) : asset.getAccountId();
        String currentPlatformName =
                platformAccount == null ? null : text(platformName(platformAccount));
        String accountName =
                currentPlatformName == null
                        ? asset == null ? "" : value(asset.getAccountName())
                        : currentPlatformName;
        Integer accountStatus =
                platformAccount == null
                        ? asset == null ? null : asset.getAccountStatus()
                        : integer(platformAccount, "account_status", "status");
        BigDecimal accountDailyLimit = decimal(platformAccount, "account_dsl");
        List<Assignment> assignments =
                assignmentModels.stream()
                        .map(
                                assignment ->
                                        new Assignment(
                                                String.valueOf(assignment.getId()),
                                                String.valueOf(assignment.getUserId()),
                                                value(assignment.getUserName()),
                                                Boolean.TRUE.equals(assignment.getIsPrimary()),
                                                assignment.getAssignmentStatus(),
                                                assignment.getAssignmentSource(),
                                                assignment.getApplicationId() == null
                                                        ? null
                                                        : String.valueOf(
                                                                assignment.getApplicationId()),
                                                assignment.getAssignedAt()))
                        .toList();
        String usageUserIds =
                String.join(",", assignments.stream().map(Assignment::userId).toList());
        String usageUserNames =
                String.join("、", assignments.stream().map(Assignment::userName).toList());
        String departmentNames =
                String.join(
                        "、",
                        assignmentModels.stream()
                                .map(AdAccountAssetAssignment::getUserId)
                                .map(userId -> value(departmentNamesByUserId.get(userId)))
                                .filter(name -> !name.isBlank())
                                .distinct()
                                .toList());
        boolean manuallyUpdated =
                asset != null && Boolean.TRUE.equals(asset.getIsManuallyUpdated());
        String syncStatus =
                platformAccount == null
                        ? "PLATFORM_MISSING"
                        : manuallyUpdated ? "MANUAL_LOCKED" : "SYNCED";
        return new Account(
                value(accountId),
                accountName,
                accountStatus,
                accountDailyLimit,
                asset == null
                        ? INVENTORY_STATUS_AVAILABLE
                        : inventoryStatus(asset.getInventoryStatus()),
                asset == null
                        ? string(platformAccount, "account_type", "accountType")
                        : value(asset.getAccountType()),
                asset == null
                        ? string(platformAccount, "account_attribute", "accountAttribute")
                        : value(asset.getAccountAttribute()),
                asset == null
                        ? string(platformAccount, "manage_bm", "managed_bm", "manageBm")
                        : value(asset.getManagedBm()),
                asset == null
                        ? string(platformAccount, "bm_id", "bmId", "manage_bm_id", "manageBmId")
                        : value(asset.getManagedBmId()),
                asset == null
                        ? string(platformAccount, "backup_manage_bm", "backup_managed_bm")
                        : value(asset.getBackupManagedBm()),
                asset == null
                        ? string(platformAccount, "backup_manage_bm_id", "backup_managed_bm_id")
                        : value(asset.getBackupManagedBmId()),
                asset == null
                        ? string(platformAccount, "timezone_name", "timezone")
                        : value(asset.getTimezone()),
                asset == null ? "" : value(asset.getCardStation()),
                asset == null
                        ? string(platformAccount, "card_number", "cardNumber")
                        : value(asset.getCardNumber()),
                asset == null ? "" : value(asset.getRemark()),
                usageUserIds,
                usageUserNames,
                departmentNames,
                asset == null ? null : asset.getDeliveryDate(),
                asset == null || asset.getChannelId() == null
                        ? ""
                        : String.valueOf(asset.getChannelId()),
                asset == null ? "" : value(asset.getChannelName()),
                manuallyUpdated,
                syncStatus,
                asset == null ? null : asset.getCreatedAt(),
                assignments);
    }

    private Map<String, Document> mongoDocumentsById() {
        Map<String, Document> result = new HashMap<>();
        for (Document document : mongoTemplate.findAll(Document.class, collection)) {
            String accountId = platformId(document);
            if (accountId != null) result.put(accountId, document);
        }
        return result;
    }

    private Map<String, Document> mongoDocumentsByAccountIds(List<String> accountIds) {
        if (accountIds.isEmpty()) return Map.of();
        List<Object> variants = new ArrayList<>();
        for (String accountId : accountIds) {
            variants.add(accountId);
            try {
                variants.add(Long.parseLong(accountId));
            } catch (NumberFormatException ignored) {
                // MongoDB 历史 _id 同时存在字符串和 Long，非数字 ID 只按字符串查询。
            }
        }
        Map<String, Document> result = new HashMap<>();
        Query query = Query.query(Criteria.where("_id").in(variants));
        for (Document document : mongoTemplate.find(query, Document.class, collection)) {
            String accountId = platformId(document);
            if (accountId != null) result.put(accountId, document);
        }
        return result;
    }

    private AdAccountAsset newestByAccountId(List<AdAccountAsset> assets, String accountId) {
        return assets.stream()
                .filter(asset -> accountId.equals(asset.getAccountId()))
                .max(
                        Comparator.comparing(
                                AdAccountAsset::getUpdatedAt,
                                Comparator.nullsFirst(Comparator.naturalOrder())))
                .orElse(null);
    }

    private void applyChannel(AdAccountAsset asset, String channelIdValue) {
        String normalizedChannelId = text(channelIdValue);
        if (normalizedChannelId == null) return;
        Long channelId;
        try {
            channelId = Long.valueOf(normalizedChannelId);
        } catch (NumberFormatException exception) {
            throw new AdAccountAssetException("渠道ID格式错误");
        }
        ChannelModels.Channel channel = channelMapper.findChannel(channelId);
        if (channel == null || !Integer.valueOf(1).equals(channel.getStatus())) {
            throw new AdAccountAssetException("渠道不存在或已停用");
        }
        asset.setChannelId(channelId);
        asset.setChannelName(channel.getChannelName());
    }

    /** 查询全部可选账户属性。 */
    public List<AccountAttribute> listAccountAttributes() {
        return accountAttributeMapper.findAll().stream().map(this::attributeView).toList();
    }

    /** 新增账户属性配置。 */
    public AccountAttribute createAccountAttribute(AccountAttributeSave request) {
        com.adpulse.main.adaccountasset.AdAccountAssetModels.AccountAttribute attribute =
                new com.adpulse.main.adaccountasset.AdAccountAssetModels.AccountAttribute();
        attribute.setAccountAttribute(request.accountAttribute().trim());
        attribute.setCreatedBy(actorId());
        try {
            accountAttributeMapper.insert(attribute);
        } catch (DuplicateKeyException exception) {
            throw new AdAccountAssetException("账户属性名称已存在");
        }
        return attributeView(requireAccountAttribute(attribute.getId()));
    }

    /** 修改账户属性配置；账户资产中已保存的历史值不会跟随改名。 */
    public AccountAttribute updateAccountAttribute(Long id, AccountAttributeSave request) {
        com.adpulse.main.adaccountasset.AdAccountAssetModels.AccountAttribute attribute =
                requireAccountAttribute(id);
        attribute.setAccountAttribute(request.accountAttribute().trim());
        try {
            accountAttributeMapper.update(attribute);
        } catch (DuplicateKeyException exception) {
            throw new AdAccountAssetException("账户属性名称已存在");
        }
        return attributeView(requireAccountAttribute(id));
    }

    /** 删除账户属性配置；资产表中的历史值继续保留。 */
    public void deleteAccountAttribute(Long id) {
        requireAccountAttribute(id);
        accountAttributeMapper.softDelete(id, System.currentTimeMillis());
    }

    private void validateAccountAttribute(Save request, String existingAttribute) {
        String accountAttribute = text(request.accountAttribute());
        if (accountAttribute != null
                && accountAttributeMapper.findByName(accountAttribute) == null
                && !accountAttribute.equals(existingAttribute)) {
            throw new AdAccountAssetException("账户属性不存在：" + accountAttribute);
        }
    }

    private AccountAttribute attributeView(
            com.adpulse.main.adaccountasset.AdAccountAssetModels.AccountAttribute attribute) {
        return new AccountAttribute(
                String.valueOf(attribute.getId()),
                attribute.getAccountAttribute(),
                attribute.getCreatedAt());
    }

    private com.adpulse.main.adaccountasset.AdAccountAssetModels.AccountAttribute
            requireAccountAttribute(Long id) {
        com.adpulse.main.adaccountasset.AdAccountAssetModels.AccountAttribute attribute =
                accountAttributeMapper.findById(id);
        if (attribute == null) throw new AdAccountAssetException("账户属性不存在");
        return attribute;
    }

    private Query queryByAccountId(String accountId) {
        List<Object> variants = new ArrayList<>();
        variants.add(accountId);
        try {
            variants.add(Long.parseLong(accountId));
        } catch (NumberFormatException ignored) {
            // MongoDB 历史 _id 同时存在字符串和 Long，非数字 ID 只按字符串查询。
        }
        return Query.query(Criteria.where("_id").in(variants));
    }

    private String platformId(Document document) {
        return text(string(document, "_id", "account_id", "accountId"));
    }

    private String platformName(Document document) {
        return value(text(string(document, "name", "account_name", "accountName")));
    }

    private String identity(String accountId, String accountName) {
        return value(accountId) + '\u0000' + value(accountName);
    }

    private Integer integer(Document document, String... names) {
        for (String name : names) {
            Object rawValue = document == null ? null : document.get(name);
            if (rawValue instanceof Number number) return number.intValue();
            if (rawValue != null) {
                try {
                    return Integer.valueOf(rawValue.toString());
                } catch (NumberFormatException ignored) {
                    return null;
                }
            }
        }
        return null;
    }

    /** Mongo 历史数据可能使用普通数值、Decimal128 或字符串保存金额，统一转换为精确十进制数。 */
    private BigDecimal decimal(Document document, String... names) {
        for (String name : names) {
            Object rawValue = document == null ? null : document.get(name);
            if (rawValue == null) continue;
            try {
                return new BigDecimal(rawValue.toString());
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }

    private String departmentName(Long userId) {
        if (userId == null) return "";
        return value(adAccountUserMapper.findCurrentDepartmentName(userId));
    }

    private String normalizeAccountId(String accountId) {
        String value = text(accountId);
        return value == null ? null : text(value.replaceFirst("^act_", ""));
    }

    private String requiredAccountId(String accountId) {
        String value = normalizeAccountId(accountId);
        if (value == null) throw new AdAccountAssetException("账户ID不能为空");
        return value;
    }

    private String string(Document document, String... names) {
        if (document == null) return "";
        for (String name : names) {
            Object value = document.get(name);
            if (value != null) return value.toString();
        }
        return "";
    }

    private String text(String value) {
        if (value == null) return null;
        String normalized = value.trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private String value(String source) {
        return source == null ? "" : source;
    }

    private String inventoryStatus(String source) {
        String normalized = text(source);
        if (normalized == null) return INVENTORY_STATUS_AVAILABLE;
        normalized = normalized.toUpperCase(Locale.ROOT);
        if (!INVENTORY_STATUSES.contains(normalized)) {
            throw new AdAccountAssetException("库存状态不合法：" + source);
        }
        return normalized;
    }

    private Long actorId() {
        Long actorId = actorIdOrNull();
        if (actorId != null) return actorId;
        throw new AdAccountAssetException("登录状态无效");
    }

    private Long actorIdOrNull() {
        var authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null) return null;
        Object principal = authentication.getPrincipal();
        if (principal instanceof CurrentUser currentUser) return currentUser.userId();
        return null;
    }

    private record AccountSource(AdAccountAsset asset, Document platformAccount) {}

    /** 广告账户台账的可展示业务异常。 */
    private record BatchUpdateContext(ChannelModels.Channel channel, String inventoryStatus) {}

    private record BatchUpdateTarget(
            String accountId, AdAccountAsset existing, Document platformAccount) {}

    public static final class AdAccountAssetException extends RuntimeException {
        public AdAccountAssetException(String message) {
            super(message);
        }
    }
}

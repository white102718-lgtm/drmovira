package com.adpulse.main.task.service;

import com.adpulse.main.integration.security.IntegrationSecretCipher;
import com.adpulse.main.project.service.ProjectService;
import com.adpulse.main.project.service.ProjectService.DeliveryTaskAgencyLineInput;
import com.adpulse.main.project.service.ProjectService.ProjectException;
import com.adpulse.main.task.dto.TaskRequests;
import com.adpulse.main.task.dto.TaskViews;
import com.adpulse.main.task.mapper.TaskMapper;
import com.adpulse.main.task.model.TaskModels;
import com.adpulse.main.task.mongo.MongoMaterialTaskQueryProvider;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 任务创建、确认、类型化交付和验收业务服务。 */
@Service
public class TaskService {
    private static final Set<String> PRIORITIES = Set.of("P0", "P1", "P2");
    private static final Set<String> DELIVERY_STATUSES =
            Set.of("ACTIVE", "PARTIAL", "PAUSED", "FAILED");
    private static final Set<String> OBJECT_TYPES = Set.of("CAMPAIGN", "AD_SET", "AD");

    private static final Set<String> FILE_USAGES =
            Set.of("ATTACHMENT", "REFERENCE", "PROOF", "DATA", "MATERIAL");

    private final TaskMapper mapper;
    private final ObjectMapper objectMapper;
    private final IntegrationSecretCipher cipher;
    private final MongoMaterialTaskQueryProvider materialTasks;
    private final ProjectService projectService;

    @Autowired
    public TaskService(
            TaskMapper mapper,
            ObjectMapper objectMapper,
            IntegrationSecretCipher cipher,
            MongoMaterialTaskQueryProvider materialTasks,
            ProjectService projectService) {
        this.mapper = mapper;
        this.objectMapper = objectMapper;
        this.cipher = cipher;
        this.materialTasks = materialTasks;
        this.projectService = projectService;
    }

    /** 兼容既有只构造任务领域依赖的单元测试。 */
    TaskService(
            TaskMapper mapper,
            ObjectMapper objectMapper,
            IntegrationSecretCipher cipher,
            MongoMaterialTaskQueryProvider materialTasks) {
        this(mapper, objectMapper, cipher, materialTasks, null);
    }

    /** 仅允许可查看来源投放任务的用户读取其关联素材任务。 */
    public TaskViews.Page<TaskViews.RelatedMaterialTask> relatedMaterialTasks(
            Long taskId, int page, int pageSize) {
        TaskModels.Task task = requireVisibleTask(taskId);
        if (!"DELIVERY".equals(task.getTaskType())) {
            throw new TaskException("仅投放任务支持查询关联素材任务");
        }
        return materialTasks.findBySourceTaskId(
                taskId, Math.max(1, page), Math.min(100, Math.max(1, pageSize)));
    }

    /** 分页查询当前用户在指定范围内可见的任务。 */
    public TaskViews.Page<TaskViews.Task> list(
            String taskType, String status, String keyword, String scope, int page, int pageSize) {
        int safePage = Math.max(1, page);
        int safeSize = Math.min(100, Math.max(1, pageSize));
        String normalizedType = optionalUpper(taskType);
        String normalizedStatus = optionalUpper(status);
        String normalizedScope = upper(scope);
        if (!Set.of(
                        "RELATED",
                        "OWNER",
                        "CREATED",
                        "ASSIGNED",
                        "FOLLOWED",
                        "PENDING_ASSIGNMENT",
                        "LEADER",
                        "ALL")
                .contains(normalizedScope)) {
            throw new TaskException("任务查询范围不合法");
        }
        if ("ALL".equals(normalizedScope)
                && (!"DELIVERY".equals(normalizedType) || !isSuperAdmin())) {
            throw new TaskException("仅超级管理员可以查询全部投放任务");
        }
        Long userId = currentUser().userId();
        return new TaskViews.Page<>(
                mapper
                        .findTasks(
                                userId,
                                normalizedScope,
                                normalizedType,
                                normalizedStatus,
                                trimToNull(keyword),
                                (safePage - 1) * safeSize,
                                safeSize)
                        .stream()
                        .map(this::taskView)
                        .toList(),
                mapper.countTasks(
                        userId,
                        normalizedScope,
                        normalizedType,
                        normalizedStatus,
                        trimToNull(keyword)),
                safePage,
                safeSize);
    }

    /** 只查询当前用户任务中心左侧导航数量。 */
    public TaskViews.NavigationCounts navigationCounts() {
        Long userId = currentUser().userId();
        return new TaskViews.NavigationCounts(
                mapper.countTasks(userId, "OWNER", "DELIVERY", null, null),
                mapper.countAssignedTasks(userId),
                mapper.countFollowedTasks(userId),
                mapper.countActivities(userId),
                mapper.countDrafts(userId),
                mapper.countTasks(userId, "RELATED", "DELIVERY", null, null),
                mapper.countTasks(userId, "CREATED", "DELIVERY", null, null),
                0,
                mapper.countTasks(userId, "LEADER", "DELIVERY", "PENDING_ACCEPTANCE", null),
                mapper.countTasks(userId, "RELATED", "DELIVERY", "COMPLETED", null),
                mapper.countFailedTasks(userId, "RELATED", "DELIVERY", null, null));
    }

    /** 查询当前用户可见的任务详情。 */
    public TaskViews.Detail get(Long taskId) {
        TaskModels.Task task = requireVisibleTask(taskId);
        return detail(task);
    }

    /** 查询当前用户作为创建者或负责人的任务历史动态。 */
    public List<TaskViews.Activity> listActivities(int limit) {
        int safeLimit = Math.min(200, Math.max(1, limit));
        return mapper.findActivities(currentUser().userId(), safeLimit).stream()
                .map(this::activityView)
                .toList();
    }

    /** 查询当前用户保存的任务草稿。 */
    public List<TaskViews.Draft> listDrafts() {
        return mapper.findDrafts(currentUser().userId()).stream().map(this::draftView).toList();
    }

    /** 查询当前用户的一项任务草稿。 */
    public TaskViews.Draft getDraft(Long draftId) {
        return draftView(requireOwnedDraft(draftId));
    }

    /** 保存一项新的任务草稿。 */
    @Transactional
    public TaskViews.Draft createDraft(TaskRequests.DraftSave request) {
        CurrentUser creator = currentUser();
        TaskModels.Draft draft = buildDraft(null, request, creator);
        draft.setDraftCode(
                "DRAFT-"
                        + java.util
                                .UUID
                                .randomUUID()
                                .toString()
                                .substring(0, 12)
                                .toUpperCase(Locale.ROOT));
        draft.setCreatorId(creator.userId());
        draft.setCreatorName(creator.displayName());
        draft.setCreatedBy(creator.userId());
        mapper.insertDraft(draft);
        return draftView(mapper.findDraft(draft.getId()));
    }

    /** 更新当前用户的一项任务草稿。 */
    @Transactional
    public TaskViews.Draft updateDraft(Long draftId, TaskRequests.DraftSave request) {
        CurrentUser creator = currentUser();
        requireOwnedDraftForUpdate(draftId, creator.userId());
        TaskModels.Draft draft = buildDraft(draftId, request, creator);
        draft.setCreatorId(creator.userId());
        if (mapper.updateDraft(draft) != 1) throw new TaskException("草稿已被删除，请刷新后重试");
        return draftView(mapper.findDraft(draftId));
    }

    /** 软删除当前用户的一项任务草稿。 */
    @Transactional
    public void deleteDraft(Long draftId) {
        Long userId = currentUser().userId();
        requireOwnedDraftForUpdate(draftId, userId);
        mapper.deleteDraft(draftId, userId, System.currentTimeMillis());
    }

    /** 创建投放任务并锁定项目配置的投放负责人。 */
    @PreAuthorize("hasAuthority('operate:button:add')")
    @Transactional
    public TaskViews.Detail createDelivery(TaskRequests.DeliveryCreate request) {
        CurrentUser creator = currentUser();
        CommonCreate common = validateDeliveryCreate(request.task(), creator);
        TaskModels.ProjectTaskOwners projectOwners =
                mapper.findProjectTaskOwners(common.projectId());
        List<String> platforms = distinctRequired(request.platforms(), "投放平台");
        List<TaskRequests.DeliveryItem> items =
                syncDeliveryAgencyLines(
                        common.projectId(), validateDeliveryItems(request.items(), platforms));
        validateOwnedFiles(request.files(), creator.userId());

        TaskModels.Task task = insertTask("DELIVERY", common, creator);
        TaskModels.DeliveryDetail detail = new TaskModels.DeliveryDetail();
        detail.setTaskId(task.getId());
        detail.setProductUrl(request.productUrl().trim());
        detail.setItemsCiphertext(encodeDeliveryItems(items));
        detail.setRegionValue(request.region().trim());
        detail.setTargetDescription(request.target().trim());
        detail.setPlannedStartAt(request.plannedStartAt());
        detail.setAmUserId(projectOwners == null ? null : projectOwners.getAmUserId());
        detail.setAmUserName(projectOwners == null ? null : projectOwners.getAmUserName());
        mapper.insertDeliveryDetail(detail);
        insertDeliveryOperators(task.getId(), items);
        replaceDeliveryTaskAms(task.getId(), common.projectId(), projectOwners, creator.userId());
        for (int index = 0; index < platforms.size(); index++) {
            mapper.insertDeliveryPlatform(task.getId(), platforms.get(index), index);
        }
        bindFiles(task.getId(), task.getId(), "DELIVERY_TASK", request.files(), creator.userId());
        recordActivity(task, "CREATED", task.getStatus(), creator, "创建了投放任务");
        consumeDraft(request.draftId(), "DELIVERY", creator.userId());
        return detail(task);
    }

    /** 拒绝旧客户端独立分配；投手必须随创建或重新提交表单保存。 */
    @Transactional
    public TaskViews.Detail assignDeliveryAllocations(
            Long taskId, TaskRequests.DeliveryAllocationAssign request) {
        throw new TaskException("独立分配已停用，请在创建或重新提交表单中指定投手");
    }

    /** 创建素材任务及尺寸、参考链接和参考文件。 */
    @Transactional
    public TaskViews.Detail createMaterial(TaskRequests.MaterialCreate request) {
        CurrentUser creator = currentUser();
        CommonCreate common = validateCommon(request.task(), creator);
        List<String> sizes = distinctRequired(request.sizes(), "素材尺寸");
        requireDictionaryValues(
                "MATERIAL_DEMAND_TYPE", List.of(request.demandType().trim()), "素材类型");
        requireDictionaryValues("MATERIAL_SIZE", sizes, "素材尺寸");
        requireDictionaryValues("MATERIAL_LANGUAGE", List.of(request.languageCode().trim()), "语种");
        List<TaskRequests.MaterialRequirement> requirements = request.requirements();
        int quantity =
                requirements.stream().mapToInt(TaskRequests.MaterialRequirement::quantity).sum();
        if (quantity <= 0) throw new TaskException("需求描述交付数量合计必须大于0");
        validateOwnedFiles(request.referenceFiles(), creator.userId());
        if (safe(request.referenceFiles()).stream()
                .anyMatch(file -> !"REFERENCE".equals(upper(file.usageType())))) {
            throw new TaskException("素材参考文件用途必须为REFERENCE");
        }
        for (TaskRequests.MaterialRequirement requirement : requirements) {
            validateOwnedFiles(requirement.files(), creator.userId());
            if (safe(requirement.files()).stream()
                    .anyMatch(file -> !"ATTACHMENT".equals(upper(file.usageType())))) {
                throw new TaskException("需求描述附件用途必须为ATTACHMENT");
            }
        }

        TaskModels.Task task = insertTask("MATERIAL", common, creator);
        TaskModels.DepartmentSnapshot department = mapper.findUserDepartment(creator.userId());
        TaskModels.MaterialDetail detail = new TaskModels.MaterialDetail();
        detail.setTaskId(task.getId());
        detail.setDemandType(request.demandType().trim());
        detail.setLanguageCode(request.languageCode().trim());
        detail.setGreenMaterial(Boolean.TRUE.equals(request.greenMaterial()));
        detail.setDepartmentId(department == null ? null : department.getId());
        detail.setDepartmentName(department == null ? null : department.getName());
        detail.setProductSubName(trimToNull(request.productSubName()));
        detail.setQuantity(quantity);
        detail.setAddToLibrary(false);
        detail.setCountryTags(json(request.countryTags()));
        detail.setThemeTags(json(request.themeTags()));
        detail.setGameplayTags(json(request.gameplayTags()));
        mapper.insertMaterialDetail(detail);
        for (int index = 0; index < sizes.size(); index++) {
            mapper.insertMaterialSize(task.getId(), sizes.get(index), index);
        }
        for (int index = 0; index < requirements.size(); index++) {
            TaskRequests.MaterialRequirement input = requirements.get(index);
            TaskModels.MaterialRequirement requirement = new TaskModels.MaterialRequirement();
            requirement.setTaskId(task.getId());
            requirement.setSortOrder(index);
            requirement.setDescription(input.description().trim());
            requirement.setDurationText(trimToNull(input.duration()));
            requirement.setQuantity(input.quantity());
            requirement.setRelatedLink(trimToNull(input.link()));
            requirement.setRemark(trimToNull(input.remark()));
            requirement.setComplianceRequirement(trimToNull(input.compliance()));
            requirement.setCreatedBy(creator.userId());
            requirement.setUpdatedBy(creator.userId());
            mapper.insertMaterialRequirement(requirement);
            bindFiles(
                    task.getId(),
                    requirement.getId(),
                    "MATERIAL_REQUIREMENT",
                    input.files(),
                    creator.userId());
        }
        bindFiles(
                task.getId(),
                task.getId(),
                "MATERIAL_TASK",
                request.referenceFiles(),
                creator.userId());
        recordActivity(task, "CREATED", task.getStatus(), creator, "创建了素材任务");
        consumeDraft(request.draftId(), "MATERIAL", creator.userId());
        return detail(task);
    }

    /** 查询当前用户关注且仍有权查看的任务ID。 */
    public List<String> listFollowedTaskIds() {
        return mapper.findFollowedTaskIds(currentUser().userId()).stream().map(this::id).toList();
    }

    /** 当前用户关注一项可见任务。 */
    @Transactional
    public void follow(Long taskId) {
        requireVisibleTask(taskId);
        Long userId = currentUser().userId();
        if (mapper.countTaskFollow(taskId, userId) == 0) {
            mapper.insertTaskFollow(taskId, userId);
        }
    }

    /** 当前用户取消关注一项可见任务。 */
    @Transactional
    public void unfollow(Long taskId) {
        requireVisibleTask(taskId);
        mapper.deleteTaskFollow(taskId, currentUser().userId(), System.currentTimeMillis());
    }

    /** 由创建者为待分配任务指定负责人。 */
    @Transactional
    public TaskViews.Detail assign(Long taskId, TaskRequests.Assign request) {
        TaskModels.Task task = requireTaskForUpdate(taskId);
        if ("DELIVERY".equals(task.getTaskType())) throw new TaskException("请在投放任务表单中指定投手");
        Long creatorId = currentUser().userId();
        if (!creatorId.equals(task.getCreatorId())) {
            throw new TaskException("只有任务创建者可以分配负责人");
        }
        Long ownerId = parseId(request.ownerId(), "任务负责人");
        String ownerName = requireActiveUser(ownerId, "任务负责人");
        CurrentUser assigner = currentUser();
        if (mapper.assignTask(
                        taskId,
                        creatorId,
                        ownerId,
                        ownerName,
                        assigner.userId(),
                        assigner.displayName(),
                        LocalDateTime.now(),
                        task.getVersion())
                != 1) {
            throw new TaskException("任务已分配或状态已变化，请刷新后重试");
        }
        recordActivity(task, "ASSIGNED", "PENDING_CONFIRMATION", assigner, "将任务分配给" + ownerName);
        return detail(requireTask(taskId));
    }

    /** 由任务负责人确认接收任务。 */
    @Transactional
    public TaskViews.Detail confirm(Long taskId) {
        TaskModels.Task task = requireTaskForUpdate(taskId);
        Long userId = currentUser().userId();
        if (!userId.equals(task.getOwnerId())) throw new TaskException("只有任务负责人可以确认任务");
        if (!"PENDING_CONFIRMATION".equals(task.getStatus())) throw new TaskException("当前任务不可确认");
        if ("DELIVERY".equals(task.getTaskType())) {
            var detail = mapper.findDeliveryDetail(taskId);
            if (detail == null || decodeDeliveryItems(detail.getItemsCiphertext()).isEmpty()) {
                throw new TaskException("投放任务明细不存在");
            }
        }
        if (mapper.confirmTask(taskId, userId, task.getVersion(), LocalDateTime.now()) != 1) {
            throw new TaskException("任务状态已变化，请刷新后重试");
        }
        recordActivity(task, "CONFIRMED", "PROCESSING", currentUser(), "确认接收了任务");
        return detail(requireTask(taskId));
    }

    /**
     * 由任务负责人驳回尚未开始处理的任务。
     *
     * <p>投放任务由创建人提交后进入待确认，只有指定投放负责人可以确认或驳回。
     */
    @Transactional
    public TaskViews.Detail decline(Long taskId, TaskRequests.Decline request) {
        TaskModels.Task task = requireTaskForUpdate(taskId);
        Long userId = currentUser().userId();
        if (!userId.equals(task.getOwnerId())) throw new TaskException("只有任务负责人可以驳回任务");
        if (!"PENDING_CONFIRMATION".equals(task.getStatus())) {
            throw new TaskException("当前任务状态不可驳回");
        }
        String reason = request.reason().trim();
        if (mapper.declineTask(taskId, userId, task.getVersion(), reason, LocalDateTime.now())
                != 1) {
            throw new TaskException("当前任务状态不可驳回");
        }
        recordActivity(task, "DECLINED", "REJECTED", currentUser(), "驳回了任务：" + reason);
        return detail(requireTask(taskId));
    }

    /** 由创建者撤回尚未被负责人确认的任务。 */
    @Transactional
    public TaskViews.Detail withdraw(Long taskId, TaskRequests.Withdraw request) {
        TaskModels.Task task = requireTaskForUpdate(taskId);
        Long userId = currentUser().userId();
        if (!userId.equals(task.getCreatorId())) throw new TaskException("只有任务创建者可以撤回任务");
        if (mapper.withdrawTask(
                        taskId,
                        userId,
                        task.getVersion(),
                        request.reason().trim(),
                        LocalDateTime.now())
                != 1) {
            throw new TaskException("当前任务状态不可撤回");
        }
        recordActivity(
                task, "WITHDRAWN", "WITHDRAWN", currentUser(), "撤回了任务：" + request.reason().trim());
        return detail(requireTask(taskId));
    }

    /** 创建者重新提交已撤回或被负责人驳回的任务，重新进入待分配状态。 */
    @Transactional
    public TaskViews.Detail resubmit(Long taskId) {
        TaskModels.Task task = requireTaskForUpdate(taskId);
        if ("DELIVERY".equals(task.getTaskType())) throw new TaskException("请补齐投放明细后通过表单重新提交");
        Long userId = currentUser().userId();
        if (!userId.equals(task.getCreatorId())) throw new TaskException("只有任务创建者可以再次提交任务");
        if (mapper.resubmitTask(taskId, userId, task.getVersion(), LocalDateTime.now()) != 1) {
            throw new TaskException("当前任务状态不可再次提交");
        }
        recordActivity(task, "RESUBMITTED", "PENDING_ASSIGNMENT", currentUser(), "再次提交了失败任务");
        return detail(requireTask(taskId));
    }

    /** 创建者修改失败投放任务后重新提交，任务回到待确认并重新锁定投放负责人。 */
    @Transactional
    public TaskViews.Detail resubmitDelivery(Long taskId, TaskRequests.DeliveryCreate request) {
        TaskModels.Task task = requireTaskForUpdate(taskId);
        CurrentUser creator = currentUser();
        if (!creator.userId().equals(task.getCreatorId()))
            throw new TaskException("只有任务创建者可以再次提交任务");
        if (!"DELIVERY".equals(task.getTaskType())
                || !Set.of("REJECTED", "WITHDRAWN").contains(task.getStatus())) {
            throw new TaskException("当前任务状态不可再次提交");
        }
        CommonCreate common = validateDeliveryCreate(request.task(), creator);
        List<String> platforms = distinctRequired(request.platforms(), "投放平台");
        List<TaskRequests.DeliveryItem> items =
                syncDeliveryAgencyLines(
                        common.projectId(), validateDeliveryItems(request.items(), platforms));
        validateOwnedFiles(request.files(), creator.userId());
        LocalDateTime now = LocalDateTime.now();
        if (mapper.updateDeliveryTaskForResubmit(
                        taskId,
                        creator.userId(),
                        common.projectId(),
                        request.task().title().trim(),
                        trimToNull(request.task().description()),
                        common.ownerId(),
                        common.ownerName(),
                        common.priority(),
                        request.task().dueAt(),
                        task.getVersion(),
                        now)
                != 1) {
            throw new TaskException("任务状态已变化，请刷新后重试");
        }
        TaskModels.DeliveryDetail detail = new TaskModels.DeliveryDetail();
        detail.setTaskId(taskId);
        detail.setProductUrl(request.productUrl().trim());
        detail.setItemsCiphertext(encodeDeliveryItems(items));
        detail.setRegionValue(request.region().trim());
        detail.setTargetDescription(request.target().trim());
        detail.setPlannedStartAt(request.plannedStartAt());
        TaskModels.ProjectTaskOwners projectOwners =
                mapper.findProjectTaskOwners(common.projectId());
        detail.setAmUserId(projectOwners == null ? null : projectOwners.getAmUserId());
        detail.setAmUserName(projectOwners == null ? null : projectOwners.getAmUserName());
        mapper.updateDeliveryDetailForResubmit(detail);
        long deletedAt = System.currentTimeMillis();
        mapper.deleteDeliveryTaskAms(taskId, deletedAt);
        replaceDeliveryTaskAms(taskId, common.projectId(), projectOwners, creator.userId());
        mapper.deleteDeliveryPlatforms(taskId, deletedAt);
        mapper.deleteAllocations(taskId, deletedAt);
        insertDeliveryOperators(taskId, items);
        mapper.deleteTaskFiles(taskId, deletedAt);
        for (int index = 0; index < platforms.size(); index++)
            mapper.insertDeliveryPlatform(taskId, platforms.get(index), index);
        bindFiles(taskId, taskId, "DELIVERY_TASK", request.files(), creator.userId());
        recordActivity(task, "RESUBMITTED", "PENDING_CONFIRMATION", creator, "修改后再次提交了失败任务");
        return detail(requireTask(taskId));
    }

    /** 提交一版投放交付并将任务转为待验收。 */
    @Transactional
    public TaskViews.Detail submitDelivery(
            Long taskId, TaskRequests.DeliverySubmissionCreate request) {
        TaskModels.DeliverySubmission existing =
                mapper.findDeliverySubmissionByRequestId(request.requestId().trim());
        if (existing != null) {
            if (!taskId.equals(existing.getTaskId())) throw new TaskException("交付幂等键已被其他任务使用");
            return get(taskId);
        }
        TaskModels.Task task = requireDeliverySubmittableTask(taskId);
        CurrentUser operator = currentUser();
        TaskModels.Allocation allocation =
                mapper.findActiveAllocationForOperator(taskId, operator.userId());
        if (allocation == null) throw new TaskException("当前投手没有待交付的执行项");
        List<String> platforms = distinctRequired(request.platforms(), "投放平台");
        List<String> taskPlatforms = mapper.findDeliveryPlatforms(taskId);
        if (!taskPlatforms.containsAll(platforms)) {
            throw new TaskException("实际投放平台不在任务计划平台范围内");
        }
        List<String> accountIds = distinctRequired(request.accountIds(), "Account ID");
        String deliveryStatus = request.deliveryStatus().trim().toUpperCase(Locale.ROOT);
        if (!DELIVERY_STATUSES.contains(deliveryStatus)) throw new TaskException("投放状态不合法");
        validateDeliveryObjects(request);
        validateOwnedFiles(request.files(), operator.userId());

        LocalDateTime now = LocalDateTime.now();
        TaskModels.DeliverySubmission submission = new TaskModels.DeliverySubmission();
        submission.setTaskId(taskId);
        submission.setAllocationId(allocation.getId());
        submission.setVersionNo(mapper.nextDeliveryVersion(allocation.getId()));
        submission.setRequestId(request.requestId().trim());
        submission.setSubmittedBy(operator.userId());
        submission.setSubmittedByName(operator.displayName());
        submission.setPlatformValue(encodeDeliverySubmissionPlatforms(platforms));
        submission.setAdAccountId(accountIds.getFirst());
        submission.setAdAccountName(trimToNull(request.adAccountName()));
        submission.setActualStartAt(request.actualStartAt());
        submission.setActualBudget(request.actualBudget());
        submission.setActualSpend(request.actualSpend());
        submission.setDailyReportSpend(request.dailyReportSpend());
        submission.setCurrency(request.currency().trim().toUpperCase(Locale.ROOT));
        submission.setCampaignCount(request.campaignCount());
        submission.setAdsetCount(request.adsetCount());
        submission.setAdCount(request.adCount());
        submission.setDeliveryStatus(deliveryStatus);
        submission.setExceptionNote(trimToNull(request.exceptionNote()));
        submission.setSubmissionNote(trimToNull(request.note()));
        submission.setSubmittedAt(now);
        mapper.insertDeliverySubmission(submission);
        for (int index = 0; index < accountIds.size(); index++) {
            mapper.insertDeliveryObject(
                    submission.getId(), "ACCOUNT", accountIds.get(index), null, index);
        }
        for (int index = 0; index < request.objects().size(); index++) {
            TaskRequests.DeliveryObject object = request.objects().get(index);
            mapper.insertDeliveryObject(
                    submission.getId(),
                    object.objectType().trim().toUpperCase(Locale.ROOT),
                    object.objectId().trim(),
                    trimToNull(object.objectName()),
                    accountIds.size() + index);
        }
        bindFiles(
                taskId,
                submission.getId(),
                "DELIVERY_SUBMISSION",
                request.files(),
                operator.userId());
        if (mapper.markAllocationSubmitted(allocation.getId(), operator.userId(), now) != 1) {
            throw new TaskException("执行项状态已变化，请刷新后重试");
        }
        if (mapper.allAllocationsSubmitted(taskId)) markPendingAcceptance(task);
        recordActivity(
                task,
                "DELIVERY_SUBMITTED",
                mapper.allAllocationsSubmitted(taskId) ? "PENDING_ACCEPTANCE" : "PROCESSING",
                operator,
                "提交了投手执行项交付");
        return detail(requireTask(taskId));
    }

    /** 提交一版素材交付并将任务转为待验收。 */
    @Transactional
    public TaskViews.Detail submitMaterial(
            Long taskId, TaskRequests.MaterialSubmissionCreate request) {
        TaskModels.MaterialSubmission existing =
                mapper.findMaterialSubmissionByRequestId(request.requestId().trim());
        if (existing != null) {
            if (!taskId.equals(existing.getTaskId())) throw new TaskException("交付幂等键已被其他任务使用");
            return get(taskId);
        }
        TaskModels.Task task = requireSubmittableTask(taskId, "MATERIAL");
        List<TaskRequests.FileBinding> files = safe(request.files());
        if (files.stream().anyMatch(file -> !"MATERIAL".equals(upper(file.usageType())))) {
            throw new TaskException("素材交付文件用途必须为MATERIAL");
        }
        validateOwnedFiles(files, task.getOwnerId());
        TaskModels.MaterialDetail material = mapper.findMaterialDetail(taskId);
        if (request.deliveredQuantity() != files.size()) {
            throw new TaskException("交付素材数量必须与交付文件数量一致");
        }
        if (request.deliveredQuantity() < material.getQuantity()) {
            throw new TaskException("交付素材数量不能少于任务要求数量");
        }

        TaskModels.MaterialSubmission submission = new TaskModels.MaterialSubmission();
        submission.setTaskId(taskId);
        submission.setVersionNo(mapper.nextMaterialVersion(taskId));
        submission.setRequestId(request.requestId().trim());
        submission.setSubmittedBy(task.getOwnerId());
        submission.setSubmittedByName(task.getOwnerName());
        submission.setDeliveredQuantity(request.deliveredQuantity());
        submission.setSubmissionNote(trimToNull(request.note()));
        submission.setSubmittedAt(LocalDateTime.now());
        submission.setLibraryStatus(material.getAddToLibrary() ? "PENDING" : "NOT_REQUIRED");
        mapper.insertMaterialSubmission(submission);
        bindFiles(taskId, submission.getId(), "MATERIAL_SUBMISSION", files, task.getOwnerId());
        markPendingAcceptance(task);
        recordActivity(
                task, "DELIVERY_SUBMITTED", "PENDING_ACCEPTANCE", currentUser(), "提交了素材任务交付");
        return detail(requireTask(taskId));
    }

    /** 由创建者验收通过指定类型的当前交付。 */
    @Transactional
    public TaskViews.Detail accept(
            Long taskId, Long submissionId, String type, TaskRequests.Review request) {
        return review(taskId, submissionId, type, "ACCEPTED", trimToNull(request.comment()));
    }

    /** 由创建者打回指定类型的当前交付。 */
    @Transactional
    public TaskViews.Detail reject(
            Long taskId, Long submissionId, String type, TaskRequests.Review request) {
        String comment = trimToNull(request.comment());
        if (comment == null) throw new TaskException("打回任务时必须填写原因");
        return review(taskId, submissionId, type, "REJECTED", comment);
    }

    private TaskViews.Detail review(
            Long taskId, Long submissionId, String type, String result, String comment) {
        TaskModels.Task task = requireTaskForUpdate(taskId);
        CurrentUser reviewer = currentUser();
        String normalizedType = upper(type);
        if ("DELIVERY".equals(normalizedType)) {
            return reviewDeliveryAllocation(task, submissionId, result, comment, reviewer);
        }
        if (!reviewer.userId().equals(task.getCreatorId())) {
            throw new TaskException("只有任务创建者可以验收任务");
        }
        if (!"PENDING_ACCEPTANCE".equals(task.getStatus())) {
            throw new TaskException("当前任务不在待验收状态");
        }
        if (!normalizedType.equals(task.getTaskType())) throw new TaskException("交付类型与任务类型不一致");
        LocalDateTime now = LocalDateTime.now();
        int changed;
        {
            TaskModels.MaterialDetail material = mapper.findMaterialDetail(taskId);
            String libraryStatus =
                    "ACCEPTED".equals(result) && material.getAddToLibrary()
                            ? "PENDING"
                            : "NOT_REQUIRED";
            changed =
                    mapper.reviewMaterialSubmission(
                            submissionId,
                            taskId,
                            result,
                            reviewer.userId(),
                            reviewer.displayName(),
                            comment,
                            libraryStatus,
                            now);
        }
        if (changed != 1) throw new TaskException("交付记录不存在或已完成验收");
        int taskChanged =
                "ACCEPTED".equals(result)
                        ? mapper.acceptTask(taskId, reviewer.userId(), task.getVersion(), now)
                        : mapper.rejectTask(taskId, reviewer.userId(), task.getVersion());
        if (taskChanged != 1) throw new TaskException("任务状态已变化，请刷新后重试");
        recordActivity(
                task,
                "ACCEPTED".equals(result) ? "ACCEPTED" : "REJECTED",
                "ACCEPTED".equals(result) ? "COMPLETED" : "PROCESSING",
                reviewer,
                "ACCEPTED".equals(result) ? "验收通过了任务交付" : "打回了任务交付：" + comment);
        return detail(requireTask(taskId));
    }

    /** 投放负责人按投手执行项验收，打回只重开该投手的执行项。 */
    private TaskViews.Detail reviewDeliveryAllocation(
            TaskModels.Task task,
            Long submissionId,
            String result,
            String comment,
            CurrentUser reviewer) {
        if (!reviewer.userId().equals(task.getOwnerId())) {
            throw new TaskException("只有指定投放负责人可以验收投手交付");
        }
        if (!"PENDING_ACCEPTANCE".equals(task.getStatus())) {
            throw new TaskException("尚未收到全部投手交付，不能验收");
        }
        TaskModels.DeliverySubmission submission =
                mapper.findDeliverySubmission(submissionId, task.getId());
        if (submission == null || submission.getAllocationId() == null) {
            throw new TaskException("投手交付不存在");
        }
        LocalDateTime now = LocalDateTime.now();
        int changed =
                mapper.reviewDeliverySubmission(
                        submissionId,
                        task.getId(),
                        result,
                        reviewer.userId(),
                        reviewer.displayName(),
                        comment,
                        now);
        if (changed != 1) throw new TaskException("交付记录不存在或已完成验收");
        int allocationChanged =
                "ACCEPTED".equals(result)
                        ? mapper.acceptDeliveryAllocation(
                                submission.getAllocationId(), task.getId(), now)
                        : mapper.rejectDeliveryAllocation(
                                submission.getAllocationId(), task.getId());
        if (allocationChanged != 1) throw new TaskException("投手执行项状态已变化，请刷新后重试");
        if ("ACCEPTED".equals(result) && mapper.allAllocationsCompleted(task.getId())) {
            if (mapper.completeTaskByDeliveryLeader(
                            task.getId(), reviewer.userId(), task.getVersion(), now)
                    != 1) {
                throw new TaskException("任务状态已变化，请刷新后重试");
            }
        } else if ("REJECTED".equals(result)) {
            if (mapper.reopenTaskByDeliveryLeader(
                            task.getId(), reviewer.userId(), task.getVersion())
                    != 1) {
                throw new TaskException("任务状态已变化，请刷新后重试");
            }
        }
        recordActivity(
                task,
                "ACCEPTED".equals(result) ? "ALLOCATION_ACCEPTED" : "ALLOCATION_REJECTED",
                "ACCEPTED".equals(result) && mapper.allAllocationsCompleted(task.getId())
                        ? "COMPLETED"
                        : "PROCESSING",
                reviewer,
                "ACCEPTED".equals(result) ? "验收通过投手交付" : "打回投手交付：" + comment);
        return detail(requireTask(task.getId()));
    }

    private TaskModels.Task requireDeliverySubmittableTask(Long taskId) {
        TaskModels.Task task = requireTaskForUpdate(taskId);
        if (!"DELIVERY".equals(task.getTaskType()) || !"PROCESSING".equals(task.getStatus())) {
            throw new TaskException("当前任务不可提交交付");
        }
        return task;
    }

    private TaskModels.Task requireSubmittableTask(Long taskId, String type) {
        TaskModels.Task task = requireTaskForUpdate(taskId);
        CurrentUser user = currentUser();
        if (!user.userId().equals(task.getOwnerId())) throw new TaskException("只有任务负责人可以提交交付");
        if (!type.equals(task.getTaskType())) throw new TaskException("交付类型与任务类型不一致");
        if (!"PROCESSING".equals(task.getStatus())) throw new TaskException("当前任务不可提交交付");
        return task;
    }

    private void markPendingAcceptance(TaskModels.Task task) {
        if (mapper.markPendingAcceptance(task.getId(), task.getOwnerId(), task.getVersion()) != 1) {
            throw new TaskException("任务状态已变化，请刷新后重试");
        }
    }

    private TaskModels.Task insertTask(String type, CommonCreate common, CurrentUser creator) {
        TaskModels.Task task = new TaskModels.Task();
        task.setTaskCode(
                "TASK-"
                        + type.charAt(0)
                        + "-"
                        + java.util
                                .UUID
                                .randomUUID()
                                .toString()
                                .substring(0, 12)
                                .toUpperCase(Locale.ROOT));
        task.setTaskType(type);
        task.setProjectId(common.projectId());
        task.setTitle(common.request().title().trim());
        task.setDescription(trimToNull(common.request().description()));
        task.setCreatorId(creator.userId());
        task.setCreatorName(creator.displayName());
        task.setOwnerId(common.ownerId());
        task.setOwnerName(common.ownerName());
        if (common.ownerId() != null) {
            task.setAssignerId(creator.userId());
            task.setAssignerName(creator.displayName());
            task.setAssignedAt(LocalDateTime.now());
        }
        task.setPriority(common.priority());
        task.setStatus(
                "DELIVERY".equals(type)
                        ? "PENDING_CONFIRMATION"
                        : common.ownerId() == null ? "PENDING_ASSIGNMENT" : "PENDING_CONFIRMATION");
        task.setDueAt(common.request().dueAt());
        task.setVersion(0);
        task.setCreatedBy(creator.userId());
        task.setUpdatedBy(creator.userId());
        mapper.insertTask(task);
        return task;
    }

    /** 明细只供任务详情使用，包含令牌，整体加密存储；执行状态独立按投手维护。 */
    private String encodeDeliveryItems(List<TaskRequests.DeliveryItem> items) {
        try {
            return cipher.encrypt(objectMapper.writeValueAsString(items));
        } catch (JsonProcessingException exception) {
            throw new TaskException("投放明细保存失败");
        }
    }

    private List<TaskRequests.DeliveryItem> decodeDeliveryItems(String ciphertext) {
        if (ciphertext == null || ciphertext.isBlank()) return List.of();
        try {
            return objectMapper.readValue(
                    cipher.decrypt(ciphertext),
                    objectMapper
                            .getTypeFactory()
                            .constructCollectionType(List.class, TaskRequests.DeliveryItem.class));
        } catch (JsonProcessingException exception) {
            throw new TaskException("投放明细读取失败");
        }
    }

    private com.fasterxml.jackson.databind.JsonNode decodeDraftPayload(String payload)
            throws JsonProcessingException {
        var node = objectMapper.readTree(payload);
        return node.has("encryptedDeliveryPayload")
                ? objectMapper.readTree(
                        cipher.decrypt(node.get("encryptedDeliveryPayload").asText()))
                : node;
    }

    /** 每页最多 30 条代理线，返回新建任务需要复制的主数据。 */
    public List<TaskViews.AgencyLineOption> deliveryAgencyLines(String keyword, int page) {
        String term = keyword == null ? "" : keyword.trim();
        if (term.length() > 200 || page < 1 || page > 100000) throw new TaskException("代理线搜索参数不合法");
        return mapper.findDeliveryAgencyLines(term, (page - 1) * 30, 30).stream()
                .map(this::deliveryAgencyLineView)
                .toList();
    }

    /** 仅匹配本次文件引用的名称，正式提交仍按 ID 重新校验。 */
    public List<TaskViews.AgencyLineOption> matchDeliveryAgencyLines(List<String> names) {
        if (names == null
                || names.isEmpty()
                || names.size() > 1000
                || names.stream()
                        .anyMatch(name -> name == null || name.isBlank() || name.length() > 200))
            throw new TaskException("请提供 1 至 1000 个有效代理线名称");
        return mapper
                .findDeliveryAgencyLinesByNames(
                        names.stream().map(String::trim).distinct().toList())
                .stream()
                .map(this::deliveryAgencyLineView)
                .toList();
    }

    private List<TaskRequests.DeliveryItem> validateDeliveryItems(
            List<TaskRequests.DeliveryItem> items, List<String> taskPlatforms) {
        if (items == null || items.isEmpty() || items.size() > 1000)
            throw new TaskException("请填写 1 至 1000 条投放明细");
        List<TaskRequests.DeliveryItem> normalized = new java.util.ArrayList<>();
        Set<String> allowedPlatforms =
                taskPlatforms.stream()
                        .map(value -> value.trim().toLowerCase(Locale.ROOT))
                        .collect(java.util.stream.Collectors.toSet());
        Set<String> agencyLineNames = new LinkedHashSet<>();
        try (var factory = jakarta.validation.Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            for (var item : items) {
                if (item == null || !validator.validate(item).isEmpty())
                    throw new TaskException("请补齐投放明细必填字段，每行必须指定投手");
                String platform = item.platform().trim().toLowerCase(Locale.ROOT);
                if (!allowedPlatforms.contains(platform)) {
                    throw new TaskException(
                            "第 " + (normalized.size() + 1) + " 行投放平台不在任务投放范围内");
                }
                String lineName = item.agencyLineName().trim();
                if (!agencyLineNames.add(lineName.toLowerCase(Locale.ROOT))) {
                    throw new TaskException("同一任务中代理线不能重复：" + lineName);
                }
                String operatorId = parseId(item.operatorId(), "投手").toString();
                normalized.add(
                        new TaskRequests.DeliveryItem(
                                trimToNull(item.type()),
                                platform,
                                trimToNull(item.pixelName()),
                                item.pixelId().trim(),
                                item.token().trim(),
                                item.testCode().trim(),
                                null,
                                item.deliveryUrl().trim(),
                                operatorId,
                                trimToNull(item.cloakUrl()),
                                null,
                                item.agencyLineId(),
                                lineName));
            }
        }
        return normalized;
    }

    private List<TaskRequests.DeliveryItem> syncDeliveryAgencyLines(
            Long projectId, List<TaskRequests.DeliveryItem> items) {
        if (projectService == null) return items;
        List<ProjectService.DeliveryTaskAgencyLineResult> results;
        try {
            results =
                    projectService.syncDeliveryTaskAgencyLines(
                            projectId,
                            items.stream()
                                    .map(
                                            item ->
                                                    new DeliveryTaskAgencyLineInput(
                                                            item.agencyLineName(),
                                                            item.platform(),
                                                            item.type(),
                                                            item.pixelName(),
                                                            item.pixelId(),
                                                            item.token(),
                                                            item.testCode(),
                                                            item.deliveryUrl(),
                                                            item.cloakUrl(),
                                                            item.operatorId()))
                                    .toList());
        } catch (ProjectException exception) {
            throw new TaskException(exception.getMessage());
        }
        List<TaskRequests.DeliveryItem> synced = new java.util.ArrayList<>();
        for (int index = 0; index < items.size(); index++) {
            var item = items.get(index);
            var result = results.get(index);
            synced.add(
                    new TaskRequests.DeliveryItem(
                            item.type(),
                            result.platform(),
                            item.pixelName(),
                            item.pixelId(),
                            item.token(),
                            item.testCode(),
                            null,
                            item.deliveryUrl(),
                            item.operatorId(),
                            item.cloakUrl(),
                            null,
                            result.id(),
                            result.name()));
        }
        return synced;
    }

    private TaskViews.AgencyLineOption deliveryAgencyLineView(
            TaskViews.AgencyLineOption line) {
        return new TaskViews.AgencyLineOption(
                line.id(),
                line.name(),
                blankToEmpty(line.type()),
                blankToEmpty(line.pixelName()),
                blankToEmpty(line.pixelId()),
                null,
                decryptAgencyLineToken(line.tokenCiphertext()),
                blankToEmpty(line.testCode()),
                blankToEmpty(line.deliveryUrl()),
                blankToEmpty(line.optimizerId()),
                blankToEmpty(line.optimizerName()),
                blankToEmpty(line.cloakUrl()));
    }

    private String decryptAgencyLineToken(String ciphertext) {
        return ciphertext == null || ciphertext.isBlank() ? "" : cipher.decrypt(ciphertext);
    }

    private String blankToEmpty(String value) {
        return value == null ? "" : value;
    }

    private void insertDeliveryOperators(Long taskId, List<TaskRequests.DeliveryItem> items) {
        Set<Long> operators = new LinkedHashSet<>();
        for (var item : items) {
            Long operatorId = parseId(item.operatorId(), "投手");
            if (!operators.add(operatorId)) continue;
            var allocation = new TaskModels.Allocation();
            allocation.setTaskId(taskId);
            allocation.setTeamCode("");
            allocation.setTeamOwnerId(operatorId);
            allocation.setTeamOwnerName(requireUser(operatorId, "投手"));
            allocation.setPwaLineCount(0);
            allocation.setH5LineCount(0);
            allocation.setSortOrder(operators.size() - 1);
            mapper.insertAllocation(allocation);
        }
    }

    private CommonCreate validateCommon(TaskRequests.BaseCreate request, CurrentUser creator) {
        Long projectId = parseId(request.projectId(), "项目");
        if (mapper.findProjectName(projectId) == null) throw new TaskException("项目不存在或已删除");
        Long ownerId =
                request.ownerId() == null || request.ownerId().isBlank()
                        ? null
                        : parseId(request.ownerId(), "任务负责人");
        String ownerName = ownerId == null ? null : requireActiveUser(ownerId, "任务负责人");
        String priority = upper(request.priority());
        if (!PRIORITIES.contains(priority)) throw new TaskException("任务优先级不合法");
        requireDictionaryValues("TASK_PRIORITY", List.of(priority), "任务优先级");
        if (request.dueAt() != null && request.dueAt().isBefore(LocalDateTime.now()))
            throw new TaskException("任务截止时间不能早于当前时间");
        return new CommonCreate(request, projectId, ownerId, ownerName, priority);
    }

    /** 投放任务优先采用项目负责人；项目未配置时由创建人临时指定并锁定。 */
    private CommonCreate validateDeliveryCreate(
            TaskRequests.BaseCreate request, CurrentUser creator) {
        CommonCreate common = validateCommon(request, creator);
        TaskModels.ProjectTaskOwners configured = mapper.findProjectTaskOwners(common.projectId());
        Long ownerId;
        String ownerName;
        if (configured != null && configured.getDeliveryLeaderId() != null) {
            ownerId = configured.getDeliveryLeaderId();
            ownerName = requireActiveUser(ownerId, "项目投放负责人");
            if (common.ownerId() != null && !ownerId.equals(common.ownerId())) {
                throw new TaskException("项目已配置投放负责人，创建任务时不可修改");
            }
        } else {
            ownerId = common.ownerId();
            if (ownerId == null) throw new TaskException("项目未配置投放负责人，请在创建任务时选择");
            ownerName = requireActiveUser(ownerId, "投放负责人");
        }
        return new CommonCreate(request, common.projectId(), ownerId, ownerName, common.priority());
    }

    private void replaceDeliveryTaskAms(
            Long taskId, Long projectId, TaskModels.ProjectTaskOwners legacy, Long operatorId) {
        List<TaskModels.UserSnapshot> users = mapper.findProjectAms(projectId);
        if ((users == null || users.isEmpty()) && legacy != null && legacy.getAmUserId() != null) {
            TaskModels.UserSnapshot user = new TaskModels.UserSnapshot();
            user.setUserId(legacy.getAmUserId());
            user.setUserName(legacy.getAmUserName());
            users = List.of(user);
        }
        if (users == null) users = List.of();
        for (int index = 0; index < users.size(); index++) {
            TaskModels.UserSnapshot user = users.get(index);
            mapper.insertDeliveryTaskAm(
                    taskId, user.getUserId(), user.getUserName(), index, operatorId);
        }
    }

    private TaskViews.Detail detail(TaskModels.Task task) {
        boolean delivery = "DELIVERY".equals(task.getTaskType());
        TaskModels.DeliveryDetail deliveryDetail =
                delivery ? mapper.findDeliveryDetail(task.getId()) : null;
        TaskModels.MaterialDetail materialDetail =
                delivery ? null : mapper.findMaterialDetail(task.getId());
        return new TaskViews.Detail(
                taskView(task),
                deliveryDetail == null
                        ? null
                        : new TaskViews.Delivery(
                                deliveryDetail.getProductUrl(),
                                deliveryDetail.getRegionValue(),
                                deliveryDetail.getTargetDescription(),
                                deliveryDetail.getPlannedStartAt(),
                                id(deliveryDetail.getAmUserId()),
                                deliveryDetail.getAmUserName(),
                                java.util.Optional.ofNullable(
                                                mapper.findDeliveryTaskAms(task.getId()))
                                        .orElseGet(List::of)
                                        .stream()
                                        .map(
                                                user ->
                                                        new TaskViews.UserAssignment(
                                                                id(user.getUserId()),
                                                                user.getUserName()))
                                        .toList(),
                                visibleDeliveryItems(task, deliveryDetail)),
                delivery ? mapper.findDeliveryPlatforms(task.getId()) : List.of(),
                delivery
                        ? mapper.findAllocations(task.getId()).stream()
                                .map(this::allocationView)
                                .toList()
                        : List.of(),
                materialDetail == null ? null : materialView(materialDetail),
                delivery ? List.of() : mapper.findMaterialSizes(task.getId()),
                delivery
                        ? List.of()
                        : mapper.findMaterialRequirements(task.getId()).stream()
                                .map(this::materialRequirementView)
                                .toList(),
                delivery ? List.of() : mapper.findReferenceLinks(task.getId()),
                mapper.findTaskFiles(task.getId()),
                delivery
                        ? mapper.findDeliverySubmissions(task.getId()).stream()
                                .map(this::deliverySubmissionView)
                                .toList()
                        : List.of(),
                delivery
                        ? List.of()
                        : mapper.findMaterialSubmissions(task.getId()).stream()
                                .map(this::materialSubmissionView)
                                .toList());
    }

    /** 投手只看本人明细；非任务参与人的超级管理员可审阅任务但不能读取代理线令牌。 */
    private List<TaskRequests.DeliveryItem> visibleDeliveryItems(
            TaskModels.Task task, TaskModels.DeliveryDetail detail) {
        var items = decodeDeliveryItems(detail.getItemsCiphertext());
        Long userId = currentUser().userId();
        boolean taskManager = isTaskManager(task, userId);
        boolean deliveryTaskAm = isDeliveryTaskAm(task, userId);
        int allocationCount = mapper.countAllocationForOperator(task.getId(), userId);
        if (isSuperAdmin() && !taskManager && !deliveryTaskAm && allocationCount == 0) {
            return items.stream().map(this::redactDeliveryItemToken).toList();
        }
        if (taskManager || deliveryTaskAm || allocationCount == 0) {
            return items;
        }
        return items.stream().filter(item -> id(userId).equals(item.operatorId())).toList();
    }

    private TaskRequests.DeliveryItem redactDeliveryItemToken(TaskRequests.DeliveryItem item) {
        return new TaskRequests.DeliveryItem(
                item.type(),
                item.platform(),
                item.pixelName(),
                item.pixelId(),
                "******",
                item.testCode(),
                item.channelName(),
                item.deliveryUrl(),
                item.operatorId(),
                item.cloakUrl(),
                item.channelId(),
                item.agencyLineId(),
                item.agencyLineName());
    }

    private boolean isTaskManager(TaskModels.Task task, Long userId) {
        return userId.equals(task.getCreatorId())
                || userId.equals(task.getOwnerId())
                || userId.equals(task.getAssignerId());
    }

    /** AM 关联与列表的可见范围一致，兼容尚未建立多 AM 关联的历史任务。 */
    private boolean isDeliveryTaskAm(TaskModels.Task task, Long userId) {
        if (!"DELIVERY".equals(task.getTaskType())) return false;
        var users = mapper.findDeliveryTaskAms(task.getId());
        if (users != null && !users.isEmpty()) {
            return users.stream().anyMatch(user -> userId.equals(user.getUserId()));
        }
        var detail = mapper.findDeliveryDetail(task.getId());
        return detail != null && userId.equals(detail.getAmUserId());
    }

    private TaskViews.Task taskView(TaskModels.Task row) {
        return new TaskViews.Task(
                id(row.getId()),
                row.getTaskCode(),
                row.getTaskType(),
                id(row.getProjectId()),
                row.getProjectName(),
                row.getTitle(),
                row.getDescription(),
                id(row.getCreatorId()),
                row.getCreatorName(),
                id(row.getOwnerId()),
                row.getOwnerName(),
                id(row.getAssignerId()),
                row.getAssignerName(),
                row.getAssignedAt(),
                row.getPriority(),
                row.getStatus(),
                row.getDueAt(),
                row.getAcceptedAt(),
                row.getCompletedAt(),
                row.getWithdrawnAt(),
                row.getWithdrawReason(),
                row.getRejectedAt(),
                id(row.getRejectedBy()),
                row.getRejectionReason(),
                row.getVersion(),
                row.getCreatedAt(),
                row.getUpdatedAt(),
                Boolean.TRUE.equals(row.getFollowed()),
                Boolean.TRUE.equals(row.getDeliveryOperator()),
                row.getAmNames());
    }

    private TaskViews.Activity activityView(TaskModels.Activity row) {
        return new TaskViews.Activity(
                id(row.getId()),
                id(row.getTaskId()),
                row.getTaskType(),
                id(row.getProjectId()),
                row.getTaskTitle(),
                row.getEventType(),
                row.getState(),
                id(row.getActorId()),
                row.getActorName(),
                row.getDescription(),
                row.getCreatedAt());
    }

    private void recordActivity(
            TaskModels.Task task,
            String eventType,
            String state,
            CurrentUser actor,
            String description) {
        TaskModels.Activity activity = new TaskModels.Activity();
        activity.setTaskId(task.getId());
        activity.setEventType(eventType);
        activity.setState(state);
        activity.setActorId(actor.userId());
        activity.setActorName(actor.displayName());
        activity.setDescription(description);
        mapper.insertActivity(activity);
    }

    private TaskModels.Draft buildDraft(
            Long id, TaskRequests.DraftSave request, CurrentUser creator) {
        String taskType = upper(request.taskType());
        if (!Set.of("DELIVERY", "MATERIAL").contains(taskType)) {
            throw new TaskException("草稿任务类型不合法");
        }
        Long projectId =
                request.projectId() == null || request.projectId().isBlank()
                        ? null
                        : parseId(request.projectId(), "项目");
        if (projectId != null && mapper.findProjectName(projectId) == null) {
            throw new TaskException("项目不存在或已删除");
        }
        TaskModels.Draft draft = new TaskModels.Draft();
        draft.setId(id);
        draft.setTaskType(taskType);
        draft.setTitle(trimToNull(request.title()));
        draft.setProjectId(projectId);
        try {
            String payload = objectMapper.writeValueAsString(request.payload());
            draft.setPayloadJson(
                    "DELIVERY".equals(draft.getTaskType())
                            ? objectMapper.writeValueAsString(
                                    java.util.Map.of(
                                            "encryptedDeliveryPayload", cipher.encrypt(payload)))
                            : payload);
        } catch (JsonProcessingException exception) {
            throw new TaskException("草稿内容格式不正确");
        }
        draft.setUpdatedBy(creator.userId());
        return draft;
    }

    private TaskViews.Draft draftView(TaskModels.Draft row) {
        try {
            return new TaskViews.Draft(
                    id(row.getId()),
                    row.getDraftCode(),
                    row.getTaskType(),
                    id(row.getCreatorId()),
                    row.getCreatorName(),
                    row.getTitle(),
                    id(row.getProjectId()),
                    decodeDraftPayload(row.getPayloadJson()),
                    row.getCreatedAt(),
                    row.getUpdatedAt());
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("任务草稿数据格式错误", exception);
        }
    }

    private TaskModels.Draft requireOwnedDraft(Long draftId) {
        TaskModels.Draft draft = mapper.findDraft(draftId);
        if (draft == null || !currentUser().userId().equals(draft.getCreatorId())) {
            throw new TaskException("草稿不存在或无权访问");
        }
        return draft;
    }

    private TaskModels.Draft requireOwnedDraftForUpdate(Long draftId, Long userId) {
        TaskModels.Draft draft = mapper.findDraftForUpdate(draftId);
        if (draft == null || !userId.equals(draft.getCreatorId())) {
            throw new TaskException("草稿不存在或无权访问");
        }
        return draft;
    }

    private void consumeDraft(String draftId, String taskType, Long userId) {
        if (draftId == null || draftId.isBlank()) return;
        Long id = parseId(draftId, "草稿");
        TaskModels.Draft draft = requireOwnedDraftForUpdate(id, userId);
        if (!taskType.equals(draft.getTaskType())) throw new TaskException("草稿任务类型不匹配");
        mapper.deleteDraft(id, userId, System.currentTimeMillis());
    }

    /** 沿用 teamCode 字段保存部门 ID，旧团队编码只允许历史展示。 */
    private void requireDeliveryDepartment(String team) {
        if (team == null
                || !team.matches("[1-9][0-9]{0,18}")
                || mapper.findActiveDeliveryDepartment(parseId(team, "参与部门")) == null) {
            throw new TaskException("参与部门不存在、已停用或已删除，请重新选择部门");
        }
    }

    private TaskViews.Allocation allocationView(TaskModels.Allocation row) {
        return new TaskViews.Allocation(
                id(row.getId()),
                row.getTeamCode(),
                row.getTeamName(),
                id(row.getTeamOwnerId()),
                row.getTeamOwnerName(),
                row.getPwaLineCount(),
                row.getH5LineCount(),
                row.getSortOrder(),
                row.getStatus(),
                row.getSubmittedAt(),
                row.getCompletedAt());
    }

    private TaskViews.Material materialView(TaskModels.MaterialDetail row) {
        return new TaskViews.Material(
                row.getDemandType(),
                row.getLanguageCode(),
                Boolean.TRUE.equals(row.getGreenMaterial()),
                id(row.getDepartmentId()),
                row.getDepartmentName(),
                row.getProductSubName(),
                row.getQuantity(),
                row.getAddToLibrary(),
                jsonList(row.getCountryTags()),
                jsonList(row.getThemeTags()),
                jsonList(row.getGameplayTags()));
    }

    private TaskViews.MaterialRequirement materialRequirementView(
            TaskModels.MaterialRequirement row) {
        return new TaskViews.MaterialRequirement(
                id(row.getId()),
                row.getSortOrder(),
                row.getDescription(),
                row.getDurationText(),
                row.getQuantity(),
                row.getRelatedLink(),
                row.getRemark(),
                row.getComplianceRequirement());
    }

    private TaskViews.DeliverySubmission deliverySubmissionView(TaskModels.DeliverySubmission row) {
        List<String> platforms = deliverySubmissionPlatforms(row.getPlatformValue());
        List<TaskViews.DeliveryObject> objects = mapper.findDeliveryObjects(row.getId());
        List<String> accountIds =
                objects.stream()
                        .filter(object -> "ACCOUNT".equals(object.objectType()))
                        .map(TaskViews.DeliveryObject::objectId)
                        .toList();
        if (accountIds.isEmpty()) accountIds = List.of(row.getAdAccountId());
        return new TaskViews.DeliverySubmission(
                id(row.getId()),
                id(row.getAllocationId()),
                row.getVersionNo(),
                row.getRequestId(),
                id(row.getSubmittedBy()),
                row.getSubmittedByName(),
                String.join(" / ", platforms),
                platforms,
                String.join(" / ", accountIds),
                accountIds,
                accountIds.size(),
                row.getAdAccountName(),
                row.getActualStartAt(),
                row.getActualBudget(),
                row.getActualSpend(),
                row.getDailyReportSpend(),
                row.getCurrency(),
                row.getCampaignCount(),
                row.getAdsetCount(),
                row.getAdCount(),
                row.getDeliveryStatus(),
                row.getExceptionNote(),
                row.getSubmissionNote(),
                row.getSubmittedAt(),
                row.getReviewStatus(),
                id(row.getReviewerId()),
                row.getReviewerName(),
                row.getReviewComment(),
                row.getReviewedAt(),
                objects);
    }

    /** 新交付以 JSON 保存多平台，同时兼容历史单平台文本。 */
    private List<String> deliverySubmissionPlatforms(String value) {
        if (value == null || value.isBlank()) return List.of();
        if (!value.trim().startsWith("[")) return List.of(value.trim());
        try {
            return objectMapper.readValue(
                    value,
                    objectMapper
                            .getTypeFactory()
                            .constructCollectionType(List.class, String.class));
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("投放交付平台数据格式错误", exception);
        }
    }

    /** 复用现有平台字段保存结构化多选值，并在入库前限制字段长度。 */
    private String encodeDeliverySubmissionPlatforms(List<String> platforms) {
        try {
            String value = objectMapper.writeValueAsString(platforms);
            if (value.length() > 100) throw new TaskException("投放平台内容过长");
            return value;
        } catch (JsonProcessingException exception) {
            throw new TaskException("投放平台格式不正确");
        }
    }

    private TaskViews.MaterialSubmission materialSubmissionView(TaskModels.MaterialSubmission row) {
        return new TaskViews.MaterialSubmission(
                id(row.getId()),
                row.getVersionNo(),
                row.getRequestId(),
                id(row.getSubmittedBy()),
                row.getSubmittedByName(),
                row.getDeliveredQuantity(),
                row.getSubmissionNote(),
                row.getSubmittedAt(),
                row.getReviewStatus(),
                id(row.getReviewerId()),
                row.getReviewerName(),
                row.getReviewComment(),
                row.getReviewedAt(),
                row.getLibraryStatus());
    }

    private List<String> jsonList(String value) {
        if (value == null || value.isBlank()) return List.of();
        try {
            return objectMapper.readValue(
                    value,
                    objectMapper
                            .getTypeFactory()
                            .constructCollectionType(List.class, String.class));
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("任务标签数据格式错误", exception);
        }
    }

    private String id(Long value) {
        return value == null ? null : value.toString();
    }

    private void validateDeliveryObjects(TaskRequests.DeliverySubmissionCreate request) {
        for (TaskRequests.DeliveryObject object : request.objects()) {
            if (!OBJECT_TYPES.contains(upper(object.objectType()))) {
                throw new TaskException("广告对象类型不合法");
            }
        }
        long campaigns =
                request.objects().stream()
                        .filter(row -> "CAMPAIGN".equals(upper(row.objectType())))
                        .count();
        long adsets =
                request.objects().stream()
                        .filter(row -> "AD_SET".equals(upper(row.objectType())))
                        .count();
        long ads =
                request.objects().stream()
                        .filter(row -> "AD".equals(upper(row.objectType())))
                        .count();
        if (campaigns != request.campaignCount()
                || adsets != request.adsetCount()
                || ads != request.adCount()) {
            throw new TaskException("广告对象明细数量与交付汇总数量不一致");
        }
    }

    private void validateOwnedFiles(List<TaskRequests.FileBinding> inputs, Long uploaderId) {
        List<TaskRequests.FileBinding> files = safe(inputs);
        if (files.isEmpty()) return;
        List<Long> ids =
                files.stream().map(file -> parseId(file.fileId(), "文件")).distinct().toList();
        if (ids.size() != files.size()) throw new TaskException("同一文件不能重复绑定");
        if (mapper.countOwnedFiles(ids, uploaderId) != ids.size()) {
            throw new TaskException("文件不存在、已删除或不属于当前提交用户");
        }
        for (TaskRequests.FileBinding file : files) {
            if (!FILE_USAGES.contains(upper(file.usageType()))) throw new TaskException("文件用途不合法");
        }
    }

    private void bindFiles(
            Long taskId,
            Long targetId,
            String targetType,
            List<TaskRequests.FileBinding> inputs,
            Long userId) {
        for (TaskRequests.FileBinding input : safe(inputs)) {
            mapper.insertFileBinding(
                    taskId,
                    parseId(input.fileId(), "文件"),
                    targetType,
                    targetId,
                    upper(input.usageType()),
                    input.sortOrder(),
                    userId);
        }
    }

    private TaskModels.Task requireVisibleTask(Long id) {
        TaskModels.Task task = requireTask(id);
        Long userId = currentUser().userId();
        if (!("DELIVERY".equals(task.getTaskType()) && isSuperAdmin())
                && !isTaskManager(task, userId)
                && !isDeliveryTaskAm(task, userId)
                && mapper.countAllocationForOperator(task.getId(), userId) == 0
                && mapper.countTaskFollow(task.getId(), userId) == 0) {
            throw new TaskException("没有权限查看该任务");
        }
        return task;
    }

    /** 超级管理员只扩展投放任务读取范围，不改变确认、交付和验收等业务身份。 */
    private boolean isSuperAdmin() {
        return currentUser().authorities().stream()
                .anyMatch(authority -> "ROLE_ADMIN".equals(authority.getAuthority()));
    }

    private TaskModels.Task requireTask(Long id) {
        TaskModels.Task task = mapper.findTask(id);
        if (task == null) throw new TaskException("任务不存在或已删除");
        return task;
    }

    private TaskModels.Task requireTaskForUpdate(Long id) {
        TaskModels.Task task = mapper.findTaskForUpdate(id);
        if (task == null) throw new TaskException("任务不存在或已删除");
        return task;
    }

    private String requireActiveUser(Long id, String label) {
        String name = mapper.findActiveUserName(id);
        if (name == null) throw new TaskException(label + "不存在或已停用");
        return name;
    }

    private String requireUser(Long id, String label) {
        String name = mapper.findUserName(id);
        if (name == null) name = mapper.findActiveUserName(id);
        if (name == null) throw new TaskException(label + "不存在或已删除");
        return name;
    }

    private List<String> distinctRequired(List<String> values, String label) {
        List<String> normalized =
                values.stream()
                        .map(String::trim)
                        .filter(value -> !value.isEmpty())
                        .distinct()
                        .toList();
        if (normalized.isEmpty()) throw new TaskException("请至少选择一个" + label);
        if (normalized.size() != values.size()) throw new TaskException(label + "不能重复");
        return normalized;
    }

    private void requireDictionaryValues(String dictCode, List<String> values, String label) {
        List<String> distinct = values.stream().distinct().toList();
        if (mapper.countEnabledDictionaryValues(dictCode, distinct) != distinct.size()) {
            throw new TaskException(label + "包含不存在或已停用的字典值");
        }
    }

    private String json(List<String> values) {
        try {
            return objectMapper.writeValueAsString(values == null ? List.of() : values);
        } catch (JsonProcessingException exception) {
            throw new TaskException("素材标签格式不正确");
        }
    }

    private CurrentUser currentUser() {
        Object principal = SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (!(principal instanceof CurrentUser user)) throw new TaskException("当前会话未认证");
        return user;
    }

    private Long parseId(String value, String label) {
        try {
            long id = Long.parseLong(value == null ? "" : value.trim());
            if (id <= 0) throw new NumberFormatException();
            return id;
        } catch (NumberFormatException exception) {
            throw new TaskException(label + "ID格式不正确");
        }
    }

    private String optionalUpper(String value) {
        return value == null || value.isBlank() ? null : upper(value);
    }

    private String upper(String value) {
        return value.trim().toUpperCase(Locale.ROOT);
    }

    private String trimToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private <T> List<T> safe(List<T> values) {
        return values == null ? List.of() : values;
    }

    private record CommonCreate(
            TaskRequests.BaseCreate request,
            Long projectId,
            Long ownerId,
            String ownerName,
            String priority) {}

    /** 可安全展示给前端的任务业务异常。 */
    public static class TaskException extends RuntimeException {
        public TaskException(String message) {
            super(message);
        }
    }
}

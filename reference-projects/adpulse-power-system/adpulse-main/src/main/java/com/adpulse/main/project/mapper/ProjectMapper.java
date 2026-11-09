package com.adpulse.main.project.mapper;

import com.adpulse.main.project.dto.ProjectViews.Kpi;
import com.adpulse.main.project.model.AgencyLine;
import com.adpulse.main.project.model.Project;
import com.adpulse.main.project.model.ProjectOptionRow;
import com.adpulse.main.project.model.ProjectStatisticsRow;
import com.adpulse.main.project.model.ProjectUserAssignment;
import com.adpulse.main.project.model.RegionCountry;
import java.math.BigDecimal;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 项目与代理线持久化接口。 */
@Mapper
public interface ProjectMapper {
    /** 按当前页项目批量读取关联数据，避免逐项目查询。 */
    List<com.adpulse.main.project.model.ProjectReadRows.Value> findPlatformsByProjectIds(
            @Param("projectIds") List<Long> projectIds);

    /** 按当前页项目批量读取关联数据，避免逐项目查询。 */
    List<com.adpulse.main.project.model.ProjectReadRows.Value> findRegionsByProjectIds(
            @Param("projectIds") List<Long> projectIds);

    /** 按当前页项目批量读取关联数据，避免逐项目查询。 */
    List<com.adpulse.main.project.model.ProjectReadRows.Value> findProductLinksByProjectIds(
            @Param("projectIds") List<Long> projectIds);

    /** 按当前页项目批量读取关联数据，避免逐项目查询。 */
    List<com.adpulse.main.project.model.ProjectReadRows.Value> findOutsourcingTeamsByProjectIds(
            @Param("projectIds") List<Long> projectIds);

    /** 按当前页项目批量读取关联数据，避免逐项目查询。 */
    List<com.adpulse.main.project.model.ProjectReadRows.Kpi> findKpisByProjectIds(
            @Param("projectIds") List<Long> projectIds);

    /** 按当前页项目批量读取关联数据，避免逐项目查询。 */
    List<com.adpulse.main.project.model.ProjectReadRows.User> findProjectAmsByProjectIds(
            @Param("projectIds") List<Long> projectIds);

    /** 按当前页项目批量读取关联数据，避免逐项目查询。 */
    List<com.adpulse.main.project.model.ProjectReadRows.User>
            findProjectDataSpecialistsByProjectIds(@Param("projectIds") List<Long> projectIds);

    /** 读取当前项目已办理完成且未删除的结项记录，不限制申请人。 */
    List<com.adpulse.main.project.dto.ProjectViews.ClosureSettlement> findClosureSettlements(
            @Param("projectId") Long projectId);

    /** 查询项目内投放、素材任务摘要，不沿用个人任务中心的参与者过滤。 */
    List<com.adpulse.main.project.dto.ProjectViews.CompletedTask> findCompletedProjectTasks(
            @Param("projectId") Long projectId,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    int countProjectTasks(
            @Param("projectId") Long projectId, @Param("completedOnly") boolean completedOnly);

    /** 只更新优化师字段，保留其他业务配置并核对项目归属。 */
    int updateAgencyLineOptimizer(AgencyLine line);

    int updateAgencyLineStatus(
            @Param("id") Long id,
            @Param("projectId") Long projectId,
            @Param("status") String status,
            @Param("updatedBy") Long updatedBy);

    ProjectStatisticsRow countProjectStatuses();

    List<ProjectOptionRow> findProjectOptionRows();

    /** 按名称或编码查询轻量项目选项；scopeUserId为空时不应用项目数据范围。 */
    List<com.adpulse.main.project.dto.ProjectViews.ProjectSearchOption>
            findProjectSearchOptions(
                    @Param("keyword") String keyword,
                    @Param("scopeUserId") Long scopeUserId);

    /** 查询项目关联代理线的投放链接轻量选项。 */
    List<com.adpulse.main.project.dto.ProjectViews.ProjectAgencyLineDeliveryOption>
            findProjectAgencyLineDeliveryOptions(
                    @Param("projectId") Long projectId,
                    @Param("scopeUserId") Long scopeUserId,
                    @Param("limit") int limit);

    /** 按查询条件和可选的当前用户部门子树分页查询项目。 */
    List<Project> findProjects(
            @Param("keyword") String keyword,
            @Param("status") String status,
            @Param("platform") String platform,
            @Param("scopeUserId") Long scopeUserId,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    /** 兼容不限制部门数据范围的内部查询。 */
    default List<Project> findProjects(
            String keyword, String status, String platform, int offset, int pageSize) {
        return findProjects(keyword, status, platform, null, offset, pageSize);
    }

    /** 按查询条件和可选的当前用户部门子树统计项目。 */
    long countProjects(
            @Param("keyword") String keyword,
            @Param("status") String status,
            @Param("platform") String platform,
            @Param("scopeUserId") Long scopeUserId);

    /** 兼容不限制部门数据范围的内部统计。 */
    default long countProjects(String keyword, String status, String platform) {
        return countProjects(keyword, status, platform, null);
    }

    Project findProject(@Param("id") Long id);

    int countActiveProjectName(
            @Param("projectName") String projectName, @Param("excludedId") Long excludedId);

    int insertProject(Project project);

    int updateProject(Project project);

    /** 钱包完整落库后写入项目关联，重复写入同一引用保持幂等。 */
    int updateWalletCustomerRefId(
            @Param("id") Long id, @Param("walletCustomerRefId") String walletCustomerRefId);

    int countActiveUser(@Param("id") Long id);

    /** 查询未软删除人员，允许服务层区分停用历史归属与新分配。 */
    com.adpulse.main.project.model.ProjectUserReference findUserReference(@Param("id") Long id);

    int countEnabledDictionaryValue(
            @Param("dictCode") String dictCode, @Param("value") String value);

    List<RegionCountry> findEnabledRegionCountries();

    RegionCountry findEnabledRegionCountry(@Param("countryCode") String countryCode);

    void softDeletePlatforms(
            @Param("projectId") Long projectId, @Param("deletedAt") long deletedAt);

    void softDeleteRegions(@Param("projectId") Long projectId, @Param("deletedAt") long deletedAt);

    void softDeleteKpis(
            @Param("projectId") Long projectId,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);

    void insertPlatform(
            @Param("projectId") Long projectId,
            @Param("value") String value,
            @Param("createdBy") Long createdBy);

    void insertRegion(
            @Param("projectId") Long projectId,
            @Param("regionCountry") RegionCountry regionCountry,
            @Param("createdBy") Long createdBy);

    void insertKpi(
            @Param("projectId") Long projectId,
            @Param("metric") String metric,
            @Param("comparator") String comparator,
            @Param("target") BigDecimal target,
            @Param("targetMax") BigDecimal targetMax,
            @Param("sortOrder") int sortOrder,
            @Param("operatorId") Long operatorId);

    List<String> findPlatforms(@Param("projectId") Long projectId);

    List<String> findRegions(@Param("projectId") Long projectId);

    List<String> findProductLinks(@Param("projectId") Long projectId);

    List<String> findOutsourcingTeams(@Param("projectId") Long projectId);

    List<Kpi> findKpis(@Param("projectId") Long projectId);

    List<ProjectUserAssignment> findProjectAms(@Param("projectId") Long projectId);

    List<ProjectUserAssignment> findProjectDataSpecialists(@Param("projectId") Long projectId);

    void softDeleteProjectAms(
            @Param("projectId") Long projectId, @Param("deletedAt") long deletedAt);

    void softDeleteProjectDataSpecialists(
            @Param("projectId") Long projectId, @Param("deletedAt") long deletedAt);

    void insertProjectAm(
            @Param("projectId") Long projectId,
            @Param("userId") Long userId,
            @Param("userName") String userName,
            @Param("sortOrder") int sortOrder,
            @Param("createdBy") Long createdBy);

    void insertProjectDataSpecialist(
            @Param("projectId") Long projectId,
            @Param("userId") Long userId,
            @Param("userName") String userName,
            @Param("sortOrder") int sortOrder,
            @Param("createdBy") Long createdBy);

    void softDeleteProductLinks(
            @Param("projectId") Long projectId, @Param("deletedAt") long deletedAt);

    void insertProductLink(
            @Param("projectId") Long projectId,
            @Param("url") String url,
            @Param("sortOrder") int sortOrder,
            @Param("createdBy") Long createdBy);

    void softDeleteOutsourcingTeams(
            @Param("projectId") Long projectId, @Param("deletedAt") long deletedAt);

    void insertOutsourcingTeam(
            @Param("projectId") Long projectId,
            @Param("teamName") String teamName,
            @Param("createdBy") Long createdBy);

    /** 查询未删除且未绑定项目的代理线选项，最多返回五十条。 */
    List<com.adpulse.main.project.dto.ProjectViews.AgencyLineOption> findUnboundAgencyLineOptions(
            @Param("keyword") String keyword);

    /** 按查询条件和可选的当前用户部门子树分页查询代理线。 */
    List<AgencyLine> findAgencyLines(
            @Param("keywords") List<String> keywords,
            @Param("lineName") String lineName,
            @Param("platform") String platform,
            @Param("projectId") Long projectId,
            @Param("optimizerId") Long optimizerId,
            @Param("scopeUserId") Long scopeUserId,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    /** 兼容不限制部门数据范围的内部查询。 */
    default List<AgencyLine> findAgencyLines(
            List<String> keywords,
            String lineName,
            String platform,
            Long projectId,
            Long optimizerId,
            int offset,
            int pageSize) {
        return findAgencyLines(
                keywords, lineName, platform, projectId, optimizerId, null, offset, pageSize);
    }

    /** 按查询条件和可选的当前用户部门子树统计代理线。 */
    long countAgencyLines(
            @Param("keywords") List<String> keywords,
            @Param("lineName") String lineName,
            @Param("platform") String platform,
            @Param("projectId") Long projectId,
            @Param("optimizerId") Long optimizerId,
            @Param("scopeUserId") Long scopeUserId);

    /** 兼容不限制部门数据范围的内部统计。 */
    default long countAgencyLines(
            List<String> keywords,
            String lineName,
            String platform,
            Long projectId,
            Long optimizerId) {
        return countAgencyLines(keywords, lineName, platform, projectId, optimizerId, null);
    }

    AgencyLine findAgencyLine(@Param("id") Long id);

    AgencyLine findAgencyLineByRequestId(@Param("requestId") String requestId);

    /** 按数据库唯一性口径锁定同名代理线，供任务提交时安全覆盖。 */
    AgencyLine findAgencyLineByNameForUpdate(@Param("lineName") String lineName);

    /** 按版本倒序读取代理线投放链接历史。 */
    List<com.adpulse.main.project.dto.ProjectViews.AgencyLineDeliveryUrlHistory>
            findAgencyLineDeliveryUrlHistory(@Param("agencyLineId") Long agencyLineId);

    int nextAgencyLineDeliveryUrlVersion(@Param("agencyLineId") Long agencyLineId);

    void insertAgencyLineDeliveryUrlHistory(
            @Param("agencyLineId") Long agencyLineId,
            @Param("versionNo") int versionNo,
            @Param("deliveryUrl") String deliveryUrl,
            @Param("changedBy") Long changedBy,
            @Param("changedByName") String changedByName);

    int insertAgencyLine(AgencyLine line);

    int updateAgencyLine(AgencyLine line);

    int bindAgencyLine(
            @Param("id") Long id,
            @Param("projectId") Long projectId,
            @Param("updatedBy") Long updatedBy);

    int unbindAgencyLine(
            @Param("id") Long id,
            @Param("projectId") Long projectId,
            @Param("updatedBy") Long updatedBy);

    int softDeleteAgencyLine(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);
}

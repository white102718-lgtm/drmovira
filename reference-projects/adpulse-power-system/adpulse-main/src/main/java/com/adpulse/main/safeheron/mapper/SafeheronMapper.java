package com.adpulse.main.safeheron.mapper;

import com.adpulse.main.safeheron.dto.SafeheronRequests.RecordQuery;
import com.adpulse.main.safeheron.model.SafeheronModels.Coin;
import com.adpulse.main.safeheron.model.SafeheronModels.CollectionRecord;
import com.adpulse.main.safeheron.model.SafeheronModels.Department;
import com.adpulse.main.safeheron.model.SafeheronModels.RecordAggregate;
import com.adpulse.main.safeheron.model.SafeheronModels.Rule;
import com.adpulse.main.safeheron.model.SafeheronModels.Team;
import com.adpulse.main.safeheron.model.SafeheronModels.User;
import com.adpulse.main.safeheron.model.SafeheronModels.Wallet;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** Safeheron归集管理持久化接口。 */
@Mapper
public interface SafeheronMapper {
    /** 分页查询归集规则。 */
    List<Rule> findRules(@Param("offset") int offset, @Param("pageSize") int pageSize);

    /** 统计有效归集规则。 */
    long countRules();

    /** 按ID查询有效归集规则。 */
    Rule findRule(@Param("id") Long id);

    /** 新增归集规则。 */
    int insertRule(Rule rule);

    /** 更新归集规则。 */
    int updateRule(Rule rule);

    /** 更新规则启停及生效状态。 */
    int updateRuleStatus(
            @Param("id") Long id,
            @Param("status") Integer status,
            @Param("effectiveStatus") Integer effectiveStatus,
            @Param("updatedBy") Long updatedBy);

    /** 软删除归集规则。 */
    int softDeleteRule(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);

    /** 按稳定标识查询有效钱包。 */
    Wallet findWallet(@Param("accountKey") String accountKey);

    /** 按业务引用查询有效钱包，用于项目创建幂等。 */
    Wallet findWalletByCustomerRefId(@Param("customerRefId") String customerRefId);

    /** 按当前页项目钱包业务引用批量读取有效钱包。 */
    List<Wallet> findWalletsByCustomerRefIds(@Param("customerRefIds") List<String> customerRefIds);

    /** 按钱包集合批量读取有效币种，避免逐钱包查询。 */
    List<Coin> findWalletCoinsByAccountKeys(@Param("accountKeys") List<String> accountKeys);

    /** 保存Safeheron创建的钱包。 */
    int insertWallet(Wallet wallet);

    /** 保存钱包币种及加密后的首个收款地址。 */
    int insertWalletCoin(Coin coin, @Param("accountKey") String accountKey);

    /** 幂等保存外部同步的钱包币种，并更新展示字段及加密地址。 */
    int upsertWalletCoin(Coin coin, @Param("accountKey") String accountKey);

    /** 查询有效钱包列表。 */
    List<Wallet> findWallets();

    /** 查询钱包支持的指定币种。 */
    Coin findWalletCoin(@Param("accountKey") String accountKey, @Param("coinKey") String coinKey);

    /** 查询钱包支持的全部有效币种。 */
    List<Coin> findWalletCoins(@Param("accountKey") String accountKey);

    /** 查询Safeheron团队审批配置。 */
    List<Team> findTeams();

    /** 按稳定标识查询有效团队。 */
    Team findTeam(@Param("teamId") String teamId);

    /** 统计指定标识的有效团队。 */
    int countTeam(@Param("teamId") String teamId);

    /** 新增已加密敏感凭证的Safeheron团队。 */
    int insertTeam(Team team);

    /** 更新团队审批人。 */
    int updateTeamApprover(
            @Param("teamId") String teamId,
            @Param("approverId") Long approverId,
            @Param("updatedBy") Long updatedBy);

    /** 按ID查询有效系统用户。 */
    User findUser(@Param("userId") Long userId);

    /** 查询有效系统用户。 */
    List<User> findUsers();

    /** 按ID查询有效部门。 */
    Department findDepartment(@Param("departmentId") Long departmentId);

    /** 查询有效部门。 */
    List<Department> findDepartments();

    /** 分页查询归集执行记录。 */
    List<CollectionRecord> findRecords(
            @Param("query") RecordQuery query,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    /** 统计筛选范围内的归集执行记录。 */
    long countRecords(@Param("query") RecordQuery query);

    /** 聚合筛选范围内的归集金额、费用和成功数量。 */
    RecordAggregate summarizeRecords(@Param("query") RecordQuery query);
}

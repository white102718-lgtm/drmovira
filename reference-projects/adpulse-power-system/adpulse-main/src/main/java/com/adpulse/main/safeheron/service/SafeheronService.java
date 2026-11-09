package com.adpulse.main.safeheron.service;

import com.adpulse.main.safeheron.dto.SafeheronRequests.ApproverSave;
import com.adpulse.main.safeheron.dto.SafeheronRequests.RecordQuery;
import com.adpulse.main.safeheron.dto.SafeheronRequests.RuleQuery;
import com.adpulse.main.safeheron.dto.SafeheronRequests.RuleSave;
import com.adpulse.main.safeheron.dto.SafeheronRequests.TeamCreate;
import com.adpulse.main.safeheron.dto.SafeheronViews;
import com.adpulse.main.safeheron.mapper.SafeheronMapper;
import com.adpulse.main.safeheron.model.SafeheronModels.CollectionRecord;
import com.adpulse.main.safeheron.model.SafeheronModels.Department;
import com.adpulse.main.safeheron.model.SafeheronModels.RecordAggregate;
import com.adpulse.main.safeheron.model.SafeheronModels.Rule;
import com.adpulse.main.safeheron.model.SafeheronModels.Team;
import com.adpulse.main.safeheron.model.SafeheronModels.User;
import com.adpulse.main.safeheron.model.SafeheronModels.Wallet;
import com.adpulse.main.safeheron.security.SafeheronKeyValidator;
import com.adpulse.main.safeheron.security.SafeheronSecretCipher;
import com.adpulse.system.common.security.CurrentUser;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.URI;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Safeheron归集规则、审批配置与执行记录服务。 */
@Service
public class SafeheronService {
    private static final BigDecimal ZERO = BigDecimal.ZERO;
    private final SafeheronMapper mapper;
    private final SafeheronSecretCipher cipher;

    public SafeheronService(SafeheronMapper mapper, SafeheronSecretCipher cipher) {
        this.mapper = mapper;
        this.cipher = cipher;
    }

    /** 分页查询有效归集规则。 */
    public SafeheronViews.Page<SafeheronViews.Rule> listRules(RuleQuery query) {
        int page = safePage(query == null ? null : query.page());
        int pageSize = safePageSize(query == null ? null : query.pageSize());
        List<SafeheronViews.Rule> items =
                mapper.findRules((page - 1) * pageSize, pageSize).stream()
                        .map(this::ruleView)
                        .toList();
        return new SafeheronViews.Page<>(items, mapper.countRules(), page, pageSize);
    }

    /** 创建归集规则并校验所有逻辑关联。 */
    @Transactional
    public SafeheronViews.Rule createRule(RuleSave request) {
        ResolvedRuleReference reference = validateRuleReferences(request);
        Rule rule = new Rule();
        applyRule(rule, request, reference);
        rule.setCreatedBy(actorId());
        rule.setUpdatedBy(actorId());
        try {
            mapper.insertRule(rule);
        } catch (DuplicateKeyException exception) {
            throw new SafeheronException("同一部门、目标钱包和区块网络的规则已存在");
        }
        return ruleView(requireRule(rule.getId()));
    }

    /** 更新归集规则并重新校验钱包、币种和部门。 */
    @Transactional
    public SafeheronViews.Rule updateRule(Long id, RuleSave request) {
        Rule rule = requireRule(id);
        ResolvedRuleReference reference = validateRuleReferences(request);
        applyRule(rule, request, reference);
        rule.setUpdatedBy(actorId());
        try {
            mapper.updateRule(rule);
        } catch (DuplicateKeyException exception) {
            throw new SafeheronException("同一部门、目标钱包和区块网络的规则已存在");
        }
        return ruleView(requireRule(id));
    }

    /** 启用或停用归集规则。 */
    @Transactional
    public void updateRuleStatus(Long id, Integer status) {
        requireRule(id);
        mapper.updateRuleStatus(id, status, status == 1 ? 1 : 0, actorId());
    }

    /** 软删除归集规则，保留既有归集记录。 */
    @Transactional
    public void deleteRule(Long id) {
        requireRule(id);
        mapper.softDeleteRule(id, System.currentTimeMillis(), actorId());
    }

    /** 查询可作为归集目标的钱包。 */
    public List<SafeheronViews.Wallet> listWallets() {
        return mapper.findWallets().stream()
                .map(
                        item ->
                                new SafeheronViews.Wallet(
                                        item.getAccountKey(),
                                        item.getAccountName(),
                                        item.getTeamId()))
                .toList();
    }

    /** 查询指定钱包已同步的可用币种。 */
    public List<SafeheronViews.Coin> listWalletCoins(String accountKey) {
        requireWallet(accountKey);
        return mapper.findWalletCoins(accountKey).stream()
                .map(item -> new SafeheronViews.Coin(item.getCoinKey(), item.getCoinName()))
                .toList();
    }

    /** 查询Safeheron团队与审批人配置。 */
    public List<SafeheronViews.Team> listTeams() {
        return mapper.findTeams().stream().map(this::teamView).toList();
    }

    /** 新增Safeheron团队配置；私钥在进入持久层前加密，响应不包含凭证。 */
    @Transactional
    public SafeheronViews.Team createTeam(TeamCreate request) {
        String teamId = request.teamId().trim();
        if (mapper.countTeam(teamId) > 0) {
            throw new SafeheronException("Safeheron团队标识已存在");
        }
        Team team = new Team();
        team.setTeamId(teamId);
        team.setTeamName(request.teamName().trim());
        team.setStatus(1);
        team.setBaseUrl(validateBaseUrl(request.baseUrl()));
        team.setApiKey(request.apiKey().trim());
        String privateKey;
        String publicKey;
        try {
            privateKey = SafeheronKeyValidator.privateKey(request.privateKey());
            publicKey = SafeheronKeyValidator.publicKey(request.safeheronPublicKey());
        } catch (IllegalArgumentException exception) {
            throw new SafeheronException(exception.getMessage());
        }
        team.setPrivateKeyCiphertext(cipher.encrypt(privateKey));
        team.setSafeheronPublicKey(publicKey);
        team.setRequestTimeout(
                request.requestTimeout() == null ? 20_000L : request.requestTimeout());
        Long actorId = actorId();
        team.setCreatedBy(actorId);
        team.setUpdatedBy(actorId);
        try {
            mapper.insertTeam(team);
        } catch (DuplicateKeyException exception) {
            throw new SafeheronException("Safeheron团队标识已存在");
        }
        return teamView(team);
    }

    /** 批量更新团队审批人，任一引用无效时整体回滚。 */
    @Transactional
    public void updateApprovers(List<ApproverSave> requests) {
        if (requests == null || requests.isEmpty()) {
            throw new SafeheronException("至少提交一条团队审批人配置");
        }
        for (ApproverSave request : requests) {
            if (mapper.findTeam(request.teamId()) == null) {
                throw new SafeheronException("Safeheron团队不存在：" + request.teamId());
            }
            if (mapper.findUser(request.approverId()) == null) {
                throw new SafeheronException("审批用户不存在或已停用");
            }
        }
        Long actorId = actorId();
        requests.forEach(
                request ->
                        mapper.updateTeamApprover(request.teamId(), request.approverId(), actorId));
    }

    /** 查询可配置为审批人的有效系统用户。 */
    public List<SafeheronViews.User> listUsers() {
        return mapper.findUsers().stream().map(this::userView).toList();
    }

    /** 查询有效部门树。 */
    public List<SafeheronViews.Department> departmentTree() {
        Map<Long, List<Department>> grouped = new HashMap<>();
        mapper.findDepartments()
                .forEach(
                        item ->
                                grouped.computeIfAbsent(
                                                item.getParentId(), ignored -> new ArrayList<>())
                                        .add(item));
        return buildDepartments(0L, grouped);
    }

    /** 分页查询归集执行记录。 */
    public SafeheronViews.Page<SafeheronViews.CollectionRecord> listRecords(RecordQuery query) {
        RecordQuery normalized = normalizeRecordQuery(query);
        int page = safePage(normalized.page());
        int pageSize = safePageSize(normalized.pageSize());
        List<SafeheronViews.CollectionRecord> items =
                mapper.findRecords(normalized, (page - 1) * pageSize, pageSize).stream()
                        .map(this::recordView)
                        .toList();
        return new SafeheronViews.Page<>(items, mapper.countRecords(normalized), page, pageSize);
    }

    /** 统计查询范围；未传日期时按当天统计。 */
    public SafeheronViews.RecordStatistics recordStatistics(RecordQuery query) {
        RecordQuery normalized = normalizeRecordQuery(query);
        if (normalized.startDate() == null && normalized.endDate() == null) {
            LocalDate today = LocalDate.now();
            normalized =
                    new RecordQuery(
                            normalized.teamId(),
                            normalized.deptId(),
                            normalized.status(),
                            normalized.taskId(),
                            today,
                            today,
                            normalized.page(),
                            normalized.pageSize());
        }
        RecordAggregate aggregate = mapper.summarizeRecords(normalized);
        long total =
                aggregate == null || aggregate.getTotalCount() == null
                        ? 0
                        : aggregate.getTotalCount();
        long success =
                aggregate == null || aggregate.getSuccessCount() == null
                        ? 0
                        : aggregate.getSuccessCount();
        BigDecimal rate =
                total == 0
                        ? ZERO
                        : BigDecimal.valueOf(success)
                                .multiply(BigDecimal.valueOf(100))
                                .divide(BigDecimal.valueOf(total), 2, RoundingMode.HALF_UP);
        return new SafeheronViews.RecordStatistics(
                total,
                money(aggregate == null ? null : aggregate.getAmountUsd()),
                money(aggregate == null ? null : aggregate.getGasFee()),
                rate);
    }

    /** 将当前筛选条件下的归集记录导出为XLSX。 */
    public byte[] exportRecords(RecordQuery query) {
        RecordQuery normalized = normalizeRecordQuery(query);
        List<CollectionRecord> records = mapper.findRecords(normalized, 0, 1_000_000);
        try (var workbook = new XSSFWorkbook();
                var output = new ByteArrayOutputStream()) {
            var sheet = workbook.createSheet("归集记录");
            writeRow(
                    sheet.createRow(0),
                    List.of(
                            "时间", "部门", "任务ID", "被归集钱包", "目标钱包", "币种", "数量", "美元估值", "Gas费", "状态",
                            "审批人", "交易哈希", "备注"));
            for (int index = 0; index < records.size(); index++) {
                CollectionRecord item = records.get(index);
                writeRow(
                        sheet.createRow(index + 1),
                        List.of(
                                text(item.getCreatedAt()),
                                text(item.getDepartmentName()),
                                text(item.getTaskId()),
                                text(item.getSourceAccountName()),
                                text(item.getDestAccountName()),
                                text(item.getCoinName()),
                                text(item.getAmount()),
                                text(item.getAmountUsd()),
                                text(item.getGasFee()),
                                statusText(item.getStatus()),
                                text(item.getApproverName()),
                                text(item.getTxHash()),
                                text(item.getRemark())));
            }
            workbook.write(output);
            return output.toByteArray();
        } catch (IOException exception) {
            throw new SafeheronException("归集记录导出失败");
        }
    }

    private ResolvedRuleReference validateRuleReferences(RuleSave request) {
        Department department = mapper.findDepartment(request.deptId());
        if (department == null) throw new SafeheronException("所属部门不存在或已停用");
        Wallet wallet = requireWallet(request.collectAccountKey());
        if (mapper.findWalletCoin(request.collectAccountKey(), request.coinKey()) == null) {
            throw new SafeheronException("目标钱包不支持所选区块网络");
        }
        return new ResolvedRuleReference(department, wallet);
    }

    private Wallet requireWallet(String accountKey) {
        Wallet wallet = mapper.findWallet(accountKey);
        if (wallet == null) throw new SafeheronException("归集目标钱包不存在或已停用");
        return wallet;
    }

    private Rule requireRule(Long id) {
        Rule rule = mapper.findRule(id);
        if (rule == null) throw new SafeheronException("归集规则不存在");
        return rule;
    }

    private void applyRule(Rule rule, RuleSave request, ResolvedRuleReference reference) {
        rule.setDepartmentId(request.deptId());
        rule.setCollectAccountKey(request.collectAccountKey().trim());
        rule.setCollectAccountName(reference.wallet().getAccountName());
        rule.setCoinKey(request.coinKey().trim());
        rule.setThresholdUsd(request.thresholdUsd());
        rule.setFrequency(request.frequency());
        rule.setGasStationEnabled(request.gasStationEnabled());
        rule.setReserveGas(request.reserveGas());
        rule.setMaxTxFee(request.maxTxFee());
        rule.setSigner(trimToNull(request.signer()));
        rule.setStatus(request.status());
        rule.setEffectiveStatus(request.status() == 1 ? 1 : 0);
    }

    private SafeheronViews.Rule ruleView(Rule item) {
        return new SafeheronViews.Rule(
                stringId(item.getId()),
                stringId(item.getDepartmentId()),
                item.getDepartmentName(),
                item.getCollectAccountKey(),
                item.getCollectAccountName(),
                item.getCoinKey(),
                money(item.getThresholdUsd()),
                item.getFrequency(),
                item.getGasStationEnabled(),
                item.getReserveGas(),
                item.getMaxTxFee(),
                item.getSigner(),
                item.getStatus(),
                item.getEffectiveStatus(),
                item.getCreatedAt(),
                item.getUpdatedAt());
    }

    private SafeheronViews.CollectionRecord recordView(CollectionRecord item) {
        return new SafeheronViews.CollectionRecord(
                stringId(item.getId()),
                item.getTeamId(),
                stringId(item.getDepartmentId()),
                item.getDepartmentName(),
                item.getTaskId(),
                item.getSourceAccountName(),
                item.getDestAccountName(),
                item.getCoinKey(),
                item.getCoinName(),
                item.getAmount(),
                item.getAmountUsd(),
                item.getGasFee(),
                item.getStatus(),
                item.getTransactionType(),
                stringId(item.getApproverId()),
                item.getApproverName(),
                item.getApproveResult(),
                item.getTxHash(),
                item.getRemark(),
                item.getCreatedAt());
    }

    private SafeheronViews.User userView(User item) {
        return new SafeheronViews.User(
                stringId(item.getUserId()), item.getUserName(), item.getNickName());
    }

    private SafeheronViews.Team teamView(Team item) {
        return new SafeheronViews.Team(
                item.getTeamId(),
                item.getTeamName(),
                stringId(item.getApproverId()),
                item.getApproverName(),
                item.getStatus());
    }

    private String validateBaseUrl(String raw) {
        String value = trimToNull(raw);
        if (value == null) return "https://api.safeheron.vip";
        try {
            URI uri = URI.create(value);
            if (!("http".equalsIgnoreCase(uri.getScheme())
                    || "https".equalsIgnoreCase(uri.getScheme()))) {
                throw new IllegalArgumentException();
            }
            return value;
        } catch (RuntimeException exception) {
            throw new SafeheronException("Safeheron API地址必须是有效的http(s)地址");
        }
    }

    private List<SafeheronViews.Department> buildDepartments(
            Long parentId, Map<Long, List<Department>> grouped) {
        return grouped.getOrDefault(parentId, List.of()).stream()
                .map(
                        item ->
                                new SafeheronViews.Department(
                                        stringId(item.getId()),
                                        item.getLabel(),
                                        buildDepartments(item.getId(), grouped)))
                .toList();
    }

    private RecordQuery normalizeRecordQuery(RecordQuery query) {
        if (query == null) return new RecordQuery(null, null, null, null, null, null, 1, 20);
        return new RecordQuery(
                trimToNull(query.teamId()),
                query.deptId(),
                query.status(),
                trimToNull(query.taskId()),
                query.startDate(),
                query.endDate(),
                query.page(),
                query.pageSize());
    }

    private void writeRow(Row row, List<String> values) {
        for (int index = 0; index < values.size(); index++) {
            Cell cell = row.createCell(index);
            cell.setCellValue(values.get(index));
        }
    }

    private String statusText(Integer status) {
        if (status != null && status == 1) return "成功";
        if (status != null && status == 2) return "失败";
        return "进行中";
    }

    private int safePage(Integer value) {
        return Math.max(1, value == null ? 1 : value);
    }

    private int safePageSize(Integer value) {
        return Math.min(500, Math.max(1, value == null ? 20 : value));
    }

    private BigDecimal money(BigDecimal value) {
        return value == null ? ZERO : value;
    }

    private String stringId(Long value) {
        return value == null ? null : value.toString();
    }

    private String text(Object value) {
        return value == null ? "" : value.toString();
    }

    private String trimToNull(String value) {
        if (value == null || value.isBlank()) return null;
        return value.trim();
    }

    private Long actorId() {
        Object principal = SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (principal instanceof CurrentUser currentUser) return currentUser.userId();
        throw new SafeheronException("登录状态无效");
    }

    private record ResolvedRuleReference(Department department, Wallet wallet) {}

    /** 可直接展示的Safeheron业务异常。 */
    public static class SafeheronException extends RuntimeException {
        /** 创建可直接展示的Safeheron业务异常。 */
        public SafeheronException(String message) {
            super(message);
        }
    }
}

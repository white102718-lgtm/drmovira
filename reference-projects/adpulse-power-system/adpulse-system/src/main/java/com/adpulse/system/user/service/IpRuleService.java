package com.adpulse.system.user.service;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.user.dto.IpRuleSaveRequest;
import com.adpulse.system.user.mapper.IpRuleMapper;
import com.adpulse.system.user.model.IpRule;
import java.util.List;
import org.springframework.security.web.util.matcher.IpAddressMatcher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 通用IP白名单维护服务。 */
@Service
public class IpRuleService {

    private final IpRuleMapper mapper;

    public IpRuleService(IpRuleMapper mapper) {
        this.mapper = mapper;
    }

    public List<IpRule> listGlobalRules() {
        return mapper.findGlobalRules();
    }

    /** 新增通用IP规则。 */
    @Transactional
    public IpRule create(IpRuleSaveRequest request) {
        validate(request);
        IpRule rule = new IpRule();
        apply(rule, request);
        Long operatorId = SecurityContextHelper.currentUserId();
        rule.setScopeType(1);
        rule.setCreatedBy(operatorId);
        rule.setUpdatedBy(operatorId);
        mapper.insert(rule);
        return mapper.findGlobalById(rule.getId());
    }

    /** 修改通用IP规则。 */
    @Transactional
    public IpRule update(Long id, IpRuleSaveRequest request) {
        validate(request);
        IpRule rule = requireRule(id);
        apply(rule, request);
        rule.setUpdatedBy(SecurityContextHelper.currentUserId());
        mapper.update(rule);
        return mapper.findGlobalById(id);
    }

    /** 软删除通用IP规则。 */
    @Transactional
    public void delete(Long id) {
        requireRule(id);
        mapper.softDelete(id, System.currentTimeMillis(), SecurityContextHelper.currentUserId());
    }

    private IpRule requireRule(Long id) {
        IpRule rule = mapper.findGlobalById(id);
        if (rule == null) {
            throw BusinessException.notFound("通用IP规则");
        }
        return rule;
    }

    private void validate(IpRuleSaveRequest request) {
        try {
            new IpAddressMatcher(request.ipCidr());
        } catch (IllegalArgumentException exception) {
            throw BusinessException.validation("非法IP或CIDR: " + request.ipCidr());
        }
        if (request.status() != 0 && request.status() != 1) {
            throw BusinessException.validation("IP规则状态只能为0或1");
        }
    }

    private void apply(IpRule rule, IpRuleSaveRequest request) {
        rule.setIpCidr(request.ipCidr());
        rule.setRuleName(request.ruleName());
        rule.setStatus(request.status());
        rule.setRemark(request.remark());
    }
}

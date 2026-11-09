package com.adpulse.system.application.service;

import com.adpulse.system.application.dto.ApplicationTypeSaveRequest;
import com.adpulse.system.application.dto.ApplicationTypeView;
import com.adpulse.system.application.mapper.ApplicationTypeMapper;
import com.adpulse.system.application.model.ApplicationType;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 申请类型主数据服务；类型停用后不可再用于新增申请入口。 */
@Service
public class ApplicationTypeService {
    private final ApplicationTypeMapper mapper;

    public ApplicationTypeService(ApplicationTypeMapper mapper) {
        this.mapper = mapper;
    }

    /** 查询资源申请中心可展示的启用类型。 */
    public List<ApplicationTypeView> enabledList() {
        return mapper.findAll(true).stream().map(ApplicationTypeView::from).toList();
    }

    /** 查询申请管理页的全部类型。 */
    public List<ApplicationTypeView> managedList() {
        return mapper.findAll(false).stream().map(ApplicationTypeView::from).toList();
    }

    /** 创建申请类型。 */
    @Transactional
    public ApplicationTypeView create(ApplicationTypeSaveRequest request) {
        ApplicationType type = new ApplicationType();
        apply(type, request);
        Long operatorId = SecurityContextHelper.currentUserId();
        type.setCreatedBy(operatorId);
        type.setUpdatedBy(operatorId);
        mapper.insert(type);
        return view(type.getId());
    }

    /** 修改申请类型。 */
    @Transactional
    public ApplicationTypeView update(Long id, ApplicationTypeSaveRequest request) {
        ApplicationType type = requireType(id);
        apply(type, request);
        type.setUpdatedBy(SecurityContextHelper.currentUserId());
        mapper.update(type);
        return view(id);
    }

    /** 获取启用的申请类型，供申请入口保存时从服务端确定分类。 */
    public ApplicationType requireEnabled(Long id) {
        ApplicationType type = requireType(id);
        if (type.getStatus() != 1) throw BusinessException.conflict("申请类型已停用");
        return type;
    }

    private void apply(ApplicationType type, ApplicationTypeSaveRequest request) {
        String typeName = request.typeName().trim();
        if (mapper.countByName(typeName, type.getId()) > 0) {
            throw BusinessException.conflict("申请类型名称已存在");
        }
        type.setTypeName(typeName);
        type.setDescription(request.description() == null ? "" : request.description().trim());
        type.setIcon(request.icon().trim());
        type.setSortOrder(request.sortOrder());
        type.setStatus(request.status());
    }

    private ApplicationTypeView view(Long id) {
        return ApplicationTypeView.from(requireType(id));
    }

    private ApplicationType requireType(Long id) {
        ApplicationType type = mapper.findById(id);
        if (type == null) throw BusinessException.notFound("申请类型");
        return type;
    }
}

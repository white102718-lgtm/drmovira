package com.adpulse.system.dictionary.service;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.dictionary.dto.DictionaryDetail;
import com.adpulse.system.dictionary.dto.DictionaryItemSaveRequest;
import com.adpulse.system.dictionary.dto.DictionaryItemView;
import com.adpulse.system.dictionary.dto.DictionaryOption;
import com.adpulse.system.dictionary.dto.DictionaryTypeSaveRequest;
import com.adpulse.system.dictionary.dto.DictionaryTypeView;
import com.adpulse.system.dictionary.mapper.DictionaryMapper;
import com.adpulse.system.dictionary.model.DictionaryItem;
import com.adpulse.system.dictionary.model.DictionaryType;
import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 字典类型和字典项配置服务。 */
@Service
public class DictionaryService {

    private final DictionaryMapper mapper;

    public DictionaryService(DictionaryMapper mapper) {
        this.mapper = mapper;
    }

    /** 查询字典类型列表。 */
    public List<DictionaryTypeView> listTypes(String keyword, Integer status) {
        return mapper.findTypes(keyword, status).stream().map(DictionaryTypeView::from).toList();
    }

    /** 查询字典类型及其全部字典项。 */
    public DictionaryDetail detail(Long id) {
        return new DictionaryDetail(
                DictionaryTypeView.from(requireType(id)),
                mapper.findItems(id).stream().map(DictionaryItemView::from).toList());
    }

    /** 按字典编码查询可供业务前端使用的启用选项。 */
    public List<DictionaryOption> options(String dictCode) {
        DictionaryType type = mapper.findEnabledTypeByCode(normalizeCode(dictCode));
        if (type == null) {
            throw BusinessException.notFound("字典类型");
        }
        return mapper.findEnabledItems(type.getId()).stream()
                .map(item -> new DictionaryOption(item.getItemValue(), item.getItemLabel()))
                .toList();
    }

    /** 新增字典类型。 */
    @Transactional
    public DictionaryDetail createType(DictionaryTypeSaveRequest request) {
        DictionaryType type = new DictionaryType();
        apply(type, request);
        Long operatorId = SecurityContextHelper.currentUserId();
        type.setCreatedBy(operatorId);
        type.setUpdatedBy(operatorId);
        mapper.insertType(type);
        return detail(type.getId());
    }

    /** 修改字典类型。 */
    @Transactional
    public DictionaryDetail updateType(Long id, DictionaryTypeSaveRequest request) {
        DictionaryType type = requireType(id);
        apply(type, request);
        type.setUpdatedBy(SecurityContextHelper.currentUserId());
        mapper.updateType(type);
        return detail(id);
    }

    /** 软删除字典类型及其字典项。 */
    @Transactional
    public void deleteType(Long id) {
        requireType(id);
        long deletedAt = System.currentTimeMillis();
        Long operatorId = SecurityContextHelper.currentUserId();
        mapper.softDeleteItemsByType(id, deletedAt, operatorId);
        mapper.softDeleteType(id, deletedAt, operatorId);
    }

    /** 在指定字典类型下新增字典项。 */
    @Transactional
    public DictionaryItemView createItem(Long dictTypeId, DictionaryItemSaveRequest request) {
        requireType(dictTypeId);
        DictionaryItem item = new DictionaryItem();
        item.setDictTypeId(dictTypeId);
        apply(item, request);
        Long operatorId = SecurityContextHelper.currentUserId();
        item.setCreatedBy(operatorId);
        item.setUpdatedBy(operatorId);
        mapper.insertItem(item);
        return DictionaryItemView.from(mapper.findItemById(item.getId()));
    }

    /** 修改字典项，但不允许跨字典类型移动。 */
    @Transactional
    public DictionaryItemView updateItem(Long id, DictionaryItemSaveRequest request) {
        DictionaryItem item = requireItem(id);
        apply(item, request);
        item.setUpdatedBy(SecurityContextHelper.currentUserId());
        mapper.updateItem(item);
        return DictionaryItemView.from(mapper.findItemById(id));
    }

    /** 软删除字典项。 */
    @Transactional
    public void deleteItem(Long id) {
        requireItem(id);
        mapper.softDeleteItem(
                id, System.currentTimeMillis(), SecurityContextHelper.currentUserId());
    }

    private DictionaryType requireType(Long id) {
        DictionaryType type = mapper.findTypeById(id);
        if (type == null) {
            throw BusinessException.notFound("字典类型");
        }
        return type;
    }

    private DictionaryItem requireItem(Long id) {
        DictionaryItem item = mapper.findItemById(id);
        if (item == null) {
            throw BusinessException.notFound("字典项");
        }
        return item;
    }

    private void apply(DictionaryType type, DictionaryTypeSaveRequest request) {
        type.setDictCode(normalizeCode(request.dictCode()));
        type.setDictName(request.dictName().trim());
        type.setStatus(request.status());
        type.setRemark(request.remark());
    }

    private void apply(DictionaryItem item, DictionaryItemSaveRequest request) {
        item.setItemValue(request.value().trim());
        item.setItemLabel(request.label().trim());
        item.setSortOrder(request.sortOrder() == null ? 0 : request.sortOrder());
        item.setStatus(request.status());
        item.setRemark(request.remark());
    }

    private String normalizeCode(String dictCode) {
        return dictCode.trim().toUpperCase(Locale.ROOT);
    }
}

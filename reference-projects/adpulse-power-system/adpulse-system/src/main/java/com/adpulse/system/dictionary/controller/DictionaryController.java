package com.adpulse.system.dictionary.controller;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.dictionary.dto.DictionaryDetail;
import com.adpulse.system.dictionary.dto.DictionaryItemSaveRequest;
import com.adpulse.system.dictionary.dto.DictionaryItemView;
import com.adpulse.system.dictionary.dto.DictionaryOption;
import com.adpulse.system.dictionary.dto.DictionaryTypeSaveRequest;
import com.adpulse.system.dictionary.dto.DictionaryTypeView;
import com.adpulse.system.dictionary.service.DictionaryService;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 字典配置与业务选项查询接口。 */
@RestController
@RequestMapping("/dictionaries")
@Tag(name = "字典管理", description = "字典类型、字典项配置和业务选项查询")
public class DictionaryController {

    private final DictionaryService service;

    public DictionaryController(DictionaryService service) {
        this.service = service;
    }

    @GetMapping("/{dictCode}/options")
    @PreAuthorize("isAuthenticated()")
    public ApiResponse<List<DictionaryOption>> options(@PathVariable String dictCode) {
        return ApiResponse.success(service.options(dictCode));
    }

    @GetMapping
    @PreAuthorize("hasAuthority('system:dictionary:list')")
    public ApiResponse<List<DictionaryTypeView>> list(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status) {
        return ApiResponse.success(service.listTypes(keyword, status));
    }

    @GetMapping("/types/{id}")
    @PreAuthorize("hasAuthority('system:dictionary:list')")
    public ApiResponse<DictionaryDetail> detail(@PathVariable Long id) {
        return ApiResponse.success(service.detail(id));
    }

    @PostMapping("/types")
    @PreAuthorize("hasAuthority('system:dictionary:list')")
    @OperationAudit(
            module = "DICTIONARY",
            type = OperationType.CREATE,
            name = "新增字典类型",
            targetType = "sys_dict_type")
    public ApiResponse<DictionaryDetail> createType(
            @Valid @RequestBody DictionaryTypeSaveRequest request) {
        return ApiResponse.success(service.createType(request));
    }

    @PutMapping("/types/{id}")
    @PreAuthorize("hasAuthority('system:dictionary:list')")
    @OperationAudit(
            module = "DICTIONARY",
            type = OperationType.UPDATE,
            name = "修改字典类型",
            targetType = "sys_dict_type",
            targetIdParameter = "id")
    public ApiResponse<DictionaryDetail> updateType(
            @PathVariable Long id, @Valid @RequestBody DictionaryTypeSaveRequest request) {
        return ApiResponse.success(service.updateType(id, request));
    }

    @DeleteMapping("/types/{id}")
    @PreAuthorize("hasAuthority('system:dictionary:list')")
    @OperationAudit(
            module = "DICTIONARY",
            type = OperationType.DELETE,
            name = "删除字典类型",
            targetType = "sys_dict_type",
            targetIdParameter = "id")
    public ApiResponse<Void> deleteType(@PathVariable Long id) {
        service.deleteType(id);
        return ApiResponse.success();
    }

    @PostMapping("/types/{dictTypeId}/items")
    @PreAuthorize("hasAuthority('system:dictionary:list')")
    @OperationAudit(
            module = "DICTIONARY",
            type = OperationType.CREATE,
            name = "新增字典项",
            targetType = "sys_dict_item")
    public ApiResponse<DictionaryItemView> createItem(
            @PathVariable Long dictTypeId, @Valid @RequestBody DictionaryItemSaveRequest request) {
        return ApiResponse.success(service.createItem(dictTypeId, request));
    }

    @PutMapping("/items/{id}")
    @PreAuthorize("hasAuthority('system:dictionary:list')")
    @OperationAudit(
            module = "DICTIONARY",
            type = OperationType.UPDATE,
            name = "修改字典项",
            targetType = "sys_dict_item",
            targetIdParameter = "id")
    public ApiResponse<DictionaryItemView> updateItem(
            @PathVariable Long id, @Valid @RequestBody DictionaryItemSaveRequest request) {
        return ApiResponse.success(service.updateItem(id, request));
    }

    @DeleteMapping("/items/{id}")
    @PreAuthorize("hasAuthority('system:dictionary:list')")
    @OperationAudit(
            module = "DICTIONARY",
            type = OperationType.DELETE,
            name = "删除字典项",
            targetType = "sys_dict_item",
            targetIdParameter = "id")
    public ApiResponse<Void> deleteItem(@PathVariable Long id) {
        service.deleteItem(id);
        return ApiResponse.success();
    }
}

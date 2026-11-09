package com.adpulse.main.cloak.controller;

import com.adpulse.main.cloak.client.GlobalPwaClient.GlobalPwaClientException;
import com.adpulse.main.cloak.service.CloakService.CloakException;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 斗篷管理第三方服务异常响应映射。 */
@RestControllerAdvice(assignableTypes = CloakController.class)
public class CloakExceptionHandler {
    private static final Pattern BATCH_ITEM_AD_URL_FIELD =
            Pattern.compile("items\\[(\\d+)]\\.adUrl");

    /** 将服务商配置或调用异常转换为可展示的业务错误。 */
    @ExceptionHandler({GlobalPwaClientException.class, CloakException.class})
    public ApiResponse<Void> handleBusiness(RuntimeException exception) {
        return ApiResponse.failure(ApiCode.BUSINESS_CONFLICT, exception.getMessage());
    }

    /** 返回首个批量请求字段校验错误。 */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ApiResponse<Void> handleValidation(MethodArgumentNotValidException exception) {
        String message =
                exception.getBindingResult().getFieldErrors().stream()
                        .findFirst()
                        .map(this::validationMessage)
                        .orElse("请求参数不合法");
        return ApiResponse.failure(ApiCode.VALIDATION_ERROR, message);
    }

    private String validationMessage(FieldError error) {
        Matcher matcher = BATCH_ITEM_AD_URL_FIELD.matcher(error.getField());
        if (matcher.matches()) {
            int itemNumber = Integer.parseInt(matcher.group(1)) + 1;
            return "第" + itemNumber + "条推广链接名称" + error.getDefaultMessage();
        }
        return error.getField() + error.getDefaultMessage();
    }

    /** 将斗篷数据唯一性冲突转换为可直接处理的业务提示。 */
    @ExceptionHandler(DuplicateKeyException.class)
    public ApiResponse<Void> handleDuplicate(DuplicateKeyException exception) {
        String detail = exception.getMostSpecificCause().getMessage();
        if (detail != null
                && (detail.contains("uk_cloak_prefix_domain_deleted")
                        || detail.contains("uk_cloak_prefix_domain_active"))) {
            return ApiResponse.failure(
                    ApiCode.DUPLICATE_DATA, "当前服务商域名下已存在相同的推广链接前缀，请更换前缀后重试");
        }
        if (detail != null && detail.contains("uk_cloak_batch_line_deleted")) {
            return ApiResponse.failure(ApiCode.DUPLICATE_DATA, "同一批次不能重复选择同一代理线");
        }
        if (detail != null && detail.contains("uk_cloak_batch_request_deleted")) {
            return ApiResponse.failure(ApiCode.DUPLICATE_DATA, "该提交正在处理，请勿重复提交");
        }
        if (detail != null && detail.contains("uk_cloak_provider_deleted")) {
            return ApiResponse.failure(ApiCode.DUPLICATE_DATA, "该服务商斗篷记录已存在，请刷新后重试");
        }
        return ApiResponse.failure(ApiCode.DUPLICATE_DATA, "斗篷数据与现有有效记录重复");
    }
}

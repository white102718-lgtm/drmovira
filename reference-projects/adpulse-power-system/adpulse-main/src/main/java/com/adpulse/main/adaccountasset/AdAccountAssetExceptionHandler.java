package com.adpulse.main.adaccountasset;

import com.adpulse.main.adaccountasset.AdAccountAssetService.AdAccountAssetException;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 广告账户台账接口的业务与参数校验错误映射。 */
@RestControllerAdvice(assignableTypes = AdAccountAssetController.class)
public class AdAccountAssetExceptionHandler {
    /** 返回可直接展示的账户台账业务错误。 */
    @ExceptionHandler(AdAccountAssetException.class)
    public ApiResponse<Void> business(AdAccountAssetException exception) {
        return ApiResponse.failure(ApiCode.BUSINESS_CONFLICT, exception.getMessage());
    }

    /** 返回请求字段校验错误。 */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ApiResponse<Void> validation(MethodArgumentNotValidException exception) {
        String message =
                exception.getBindingResult().getFieldErrors().stream()
                        .findFirst()
                        .map(error -> error.getField() + error.getDefaultMessage())
                        .orElse("请求参数不合法");
        return ApiResponse.failure(ApiCode.VALIDATION_ERROR, message);
    }
}

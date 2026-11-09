package com.adpulse.main.cardstation.controller;

import com.adpulse.main.cardstation.service.CardStationService.CardStationException;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 卡台管理异常响应映射。 */
@RestControllerAdvice(assignableTypes = CardStationController.class)
public class CardStationExceptionHandler {
    /** 映射可直接展示的业务异常。 */
    @ExceptionHandler(CardStationException.class)
    public ApiResponse<Void> business(CardStationException exception) {
        return ApiResponse.failure(ApiCode.BUSINESS_CONFLICT, exception.getMessage());
    }

    /** 映射请求字段校验异常。 */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ApiResponse<Void> validation(MethodArgumentNotValidException exception) {
        String message =
                exception.getBindingResult().getFieldErrors().stream()
                        .findFirst()
                        .map(error -> error.getField() + error.getDefaultMessage())
                        .orElse("请求参数不完整");
        return ApiResponse.failure(ApiCode.VALIDATION_ERROR, message);
    }
}

package com.adpulse.main.project.controller;

import com.adpulse.main.project.service.ProjectService.ProjectException;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 项目接口参数及业务错误转换。 */
@RestControllerAdvice(
        assignableTypes = {
            ProjectController.class,
            AgencyLineController.class,
            AgencyLineSyncController.class
        })
public class ProjectExceptionHandler {

    /** 返回可直接展示的项目业务错误。 */
    @ExceptionHandler(ProjectException.class)
    public ApiResponse<Void> handleBusiness(ProjectException exception) {
        return ApiResponse.failure(ApiCode.BUSINESS_CONFLICT, exception.getMessage());
    }

    /** 返回首个请求字段校验错误。 */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ApiResponse<Void> handleValidation(MethodArgumentNotValidException exception) {
        String message =
                exception.getBindingResult().getFieldErrors().stream()
                        .findFirst()
                        .map(error -> error.getField() + error.getDefaultMessage())
                        .orElse("请求参数不合法");
        return ApiResponse.failure(ApiCode.VALIDATION_ERROR, message);
    }
}

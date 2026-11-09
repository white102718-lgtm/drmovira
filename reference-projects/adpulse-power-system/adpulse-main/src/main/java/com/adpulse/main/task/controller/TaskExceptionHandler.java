package com.adpulse.main.task.controller;

import com.adpulse.main.task.service.TaskService.TaskException;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 任务接口参数及业务错误转换。 */
@RestControllerAdvice(assignableTypes = TaskController.class)
public class TaskExceptionHandler {
    /** 返回可直接展示的任务业务错误。 */
    @ExceptionHandler(TaskException.class)
    public ApiResponse<Void> handleBusiness(TaskException exception) {
        return ApiResponse.failure(ApiCode.BUSINESS_CONFLICT, exception.getMessage());
    }

    /** 将并发唯一约束冲突转换为稳定业务提示。 */
    @ExceptionHandler(DuplicateKeyException.class)
    public ApiResponse<Void> handleDuplicate(DuplicateKeyException exception) {
        return ApiResponse.failure(ApiCode.BUSINESS_CONFLICT, "任务数据已变化，请刷新后重试");
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

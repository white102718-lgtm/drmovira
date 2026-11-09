package com.adpulse.main.manualtask;

import com.adpulse.main.manualtask.ManualTaskService.ManualTaskException;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 手动任务业务错误响应转换。 */
@RestControllerAdvice(assignableTypes = ManualTaskController.class)
public class ManualTaskExceptionHandler {
    @ExceptionHandler(ManualTaskException.class)
    public ApiResponse<Void> handle(ManualTaskException exception) {
        return ApiResponse.failure(ApiCode.BUSINESS_CONFLICT, exception.getMessage());
    }
}

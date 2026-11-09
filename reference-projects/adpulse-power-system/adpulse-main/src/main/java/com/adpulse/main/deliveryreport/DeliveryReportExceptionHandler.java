package com.adpulse.main.deliveryreport;

import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

/** 日报固定业务表单的校验异常转换。 */
@RestControllerAdvice(
        assignableTypes = {
            DeliveryReportController.class,
            com.adpulse.main.deliveryreport.google.DeliveryReportGooglePushController.class
        })
public class DeliveryReportExceptionHandler {
    /** 向用户返回明确业务错误。 */
    @ExceptionHandler(DeliveryReportException.class)
    public ApiResponse<Void> business(DeliveryReportException exception) {
        return ApiResponse.failure(ApiCode.BUSINESS_CONFLICT, exception.getMessage());
    }

    /** 参数错误使用统一业务响应。 */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ApiResponse<Void> validation(MethodArgumentNotValidException exception) {
        return ApiResponse.failure(ApiCode.VALIDATION_ERROR, "请检查请求中的必填字段和数据格式");
    }

    /** 缺日期、错误ID和损坏JSON仍返回统一业务响应。 */
    @ExceptionHandler({
        MissingServletRequestParameterException.class,
        MethodArgumentTypeMismatchException.class,
        HttpMessageNotReadableException.class
    })
    public ApiResponse<Void> malformedRequest(Exception exception) {
        return ApiResponse.failure(ApiCode.VALIDATION_ERROR, "请检查请求参数和数据格式");
    }
}

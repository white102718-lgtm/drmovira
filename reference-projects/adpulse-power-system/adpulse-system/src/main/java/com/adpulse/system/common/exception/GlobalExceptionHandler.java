package com.adpulse.system.common.exception;

import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.ConstraintViolationException;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authorization.AuthorizationDeniedException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

/** 将服务端异常转换为稳定的 API 错误结构。 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ApiResponse<Void>> handleBusiness(BusinessException exception) {
        return ResponseEntity.ok(ApiResponse.failure(exception.getCode(), exception.getMessage()));
    }

    /** 将方法级权限校验失败返回为可识别的无权限响应，避免被误报为服务器异常。 */
    @ExceptionHandler(AuthorizationDeniedException.class)
    public ResponseEntity<ApiResponse<Void>> handleAuthorizationDenied(
            AuthorizationDeniedException exception) {
        return ResponseEntity.ok(ApiResponse.failure(ApiCode.ACCESS_DENIED, "没有访问权限"));
    }

    @ExceptionHandler({MethodArgumentNotValidException.class, ConstraintViolationException.class})
    public ResponseEntity<ApiResponse<Void>> handleValidation(Exception exception) {
        String message = exception.getMessage();
        if (exception instanceof MethodArgumentNotValidException validationException) {
            message =
                    validationException.getBindingResult().getFieldErrors().stream()
                            .map(error -> error.getField() + ": " + error.getDefaultMessage())
                            .collect(Collectors.joining("; "));
        }
        return ResponseEntity.ok(ApiResponse.failure(ApiCode.VALIDATION_ERROR, message));
    }

    @ExceptionHandler(DuplicateKeyException.class)
    public ResponseEntity<ApiResponse<Void>> handleDuplicate(DuplicateKeyException exception) {
        // 并发保存可能绕过事前查询，由数据库唯一索引兜底并返回明确提示。
        String detail = exception.getMostSpecificCause().getMessage();
        if (detail != null && detail.contains("uk_user_english_nickname_deleted")) {
            return ResponseEntity.ok(ApiResponse.failure(ApiCode.DUPLICATE_DATA, "英文昵称已存在"));
        }
        return ResponseEntity.ok(ApiResponse.failure(ApiCode.DUPLICATE_DATA, "数据与现有有效记录重复"));
    }

    /** 将Servlet层的上传大小超限转换为可展示的参数错误。 */
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ApiResponse<Void>> handleMaxUploadSize(
            MaxUploadSizeExceededException exception) {
        return ResponseEntity.ok(ApiResponse.failure(ApiCode.VALIDATION_ERROR, "单个文件不能超过100 MB"));
    }

    /** 将不支持的请求媒体类型转换为可展示的参数错误。 */
    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ApiResponse<Void>> handleMediaTypeNotSupported(
            HttpMediaTypeNotSupportedException exception) {
        return ResponseEntity.ok(
                ApiResponse.failure(ApiCode.VALIDATION_ERROR, "请求的 Content-Type 不受支持"));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleUnexpected(Exception exception) {
        log.error("Unhandled server error", exception);
        return ResponseEntity.ok(ApiResponse.failure(ApiCode.SYSTEM_ERROR, "服务器内部错误"));
    }
}

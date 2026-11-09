package com.adpulse.main.migration;

import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 迁移接口沿用 HTTP 200 与三位业务码；数据库错误不向客户端泄露。 */
@RestControllerAdvice(
        assignableTypes = {AssetMigrationController.class, ChannelIncrementController.class})
public class AssetMigrationExceptionHandler {
    /** 需要重新预检的业务冲突。 */
    @ExceptionHandler(AssetMigrationService.Conflict.class)
    public ApiResponse<Void> conflict(AssetMigrationService.Conflict exception) {
        return ApiResponse.failure(ApiCode.BUSINESS_CONFLICT, exception.getMessage());
    }

    /** 操作员白名单拒绝。 */
    @ExceptionHandler(AccessDeniedException.class)
    public ApiResponse<Void> denied() {
        return ApiResponse.failure(ApiCode.ACCESS_DENIED, "没有迁移操作权限");
    }

    /** 屏蔽底层连接、SQL 和源数据异常文本。 */
    @ExceptionHandler(Exception.class)
    public ApiResponse<Void> failure() {
        return ApiResponse.failure(ApiCode.SYSTEM_ERROR, "迁移服务异常，请检查服务端配置及前置表结构");
    }
}

package com.adpulse.system.common.exception;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authorization.AuthorizationDeniedException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

/** 全局异常响应协议测试。 */
class GlobalExceptionHandlerTest {

    private final GlobalExceptionHandler handler = new GlobalExceptionHandler();

    @Test
    void shouldExplainEnglishNicknameConflictFromDatabaseConstraint() {
        var response =
                handler.handleDuplicate(
                        new DuplicateKeyException(
                                "insert failed",
                                new java.sql.SQLException(
                                        "Duplicate entry for key 'sys_user.uk_user_english_nickname_deleted'")));

        assertThat(response.getBody().code()).isEqualTo(ApiCode.DUPLICATE_DATA);
        assertThat(response.getBody().message()).isEqualTo("英文昵称已存在");
    }

    @Test
    void shouldReturnHttp200ForBusinessException() {
        ResponseEntity<ApiResponse<Void>> response =
                handler.handleBusiness(BusinessException.conflict("状态冲突"));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().code()).isEqualTo(ApiCode.BUSINESS_CONFLICT);
    }

    @Test
    void shouldReturnHttp200ForDuplicateAndUnexpectedExceptions() {
        ResponseEntity<ApiResponse<Void>> duplicate =
                handler.handleDuplicate(new DuplicateKeyException("duplicate"));
        ResponseEntity<ApiResponse<Void>> unexpected =
                handler.handleUnexpected(new IllegalStateException("internal detail"));

        assertThat(duplicate.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(duplicate.getBody()).isNotNull();
        assertThat(duplicate.getBody().code()).isEqualTo(ApiCode.DUPLICATE_DATA);
        assertThat(unexpected.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(unexpected.getBody()).isNotNull();
        assertThat(unexpected.getBody().code()).isEqualTo(ApiCode.SYSTEM_ERROR);
    }

    @Test
    void shouldReturnAccessDeniedForMethodAuthorizationFailure() {
        ResponseEntity<ApiResponse<Void>> response =
                handler.handleAuthorizationDenied(new AuthorizationDeniedException("denied"));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().code()).isEqualTo(ApiCode.ACCESS_DENIED);
    }

    @Test
    void shouldReturnValidationErrorForOversizedUpload() {
        ResponseEntity<ApiResponse<Void>> response =
                handler.handleMaxUploadSize(new MaxUploadSizeExceededException(100));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().code()).isEqualTo(ApiCode.VALIDATION_ERROR);
    }

    @Test
    void shouldReturnValidationErrorForUnsupportedMediaType() {
        ResponseEntity<ApiResponse<Void>> response =
                handler.handleMediaTypeNotSupported(
                        new HttpMediaTypeNotSupportedException(MediaType.APPLICATION_JSON_VALUE));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().code()).isEqualTo(ApiCode.VALIDATION_ERROR);
        assertThat(response.getBody().message()).contains("Content-Type");
    }
}

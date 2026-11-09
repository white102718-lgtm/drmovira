package com.adpulse.system.operationlog.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.operationlog.audit.OperationLogContext;
import com.adpulse.system.operationlog.audit.OperationType;
import com.adpulse.system.operationlog.mapper.OperationLogMapper;
import com.adpulse.system.operationlog.model.OperationLog;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

/** 操作日志安全字段和查询枚举测试。 */
class OperationLogServiceTest {

    private final OperationLogMapper mapper = mock(OperationLogMapper.class);
    private final OperationLogService service = new OperationLogService(mapper);

    @Test
    void shouldRecordOperationMetadataWithoutRequestBody() {
        OperationLogContext context =
                new OperationLogContext(
                        1L,
                        "系统管理员",
                        "USER",
                        OperationType.UPDATE,
                        "修改用户",
                        "sys_user",
                        "15",
                        "PUT",
                        "/api/users/15",
                        "127.0.0.1",
                        "agent");

        service.recordSuccess(context);

        ArgumentCaptor<OperationLog> captor = ArgumentCaptor.forClass(OperationLog.class);
        verify(mapper).insert(captor.capture());
        OperationLog log = captor.getValue();
        assertThat(log.getOperatorUserId()).isEqualTo(1L);
        assertThat(log.getOperationType()).isEqualTo("UPDATE");
        assertThat(log.getTargetId()).isEqualTo("15");
        assertThat(log.getOperationResult()).isEqualTo(1);
        assertThat(log.getFailureCode()).isNull();
    }

    @Test
    void shouldUseStableFailureCodeForUnexpectedException() {
        OperationLogContext context =
                new OperationLogContext(
                        1L,
                        "系统管理员",
                        "ROLE",
                        OperationType.DELETE,
                        "删除角色",
                        "sys_role",
                        "8",
                        "DELETE",
                        "/api/roles/8",
                        "127.0.0.1",
                        null);

        service.recordFailure(context, new IllegalStateException("database detail"));

        ArgumentCaptor<OperationLog> captor = ArgumentCaptor.forClass(OperationLog.class);
        verify(mapper).insert(captor.capture());
        assertThat(captor.getValue().getFailureCode()).isEqualTo(ApiCode.SYSTEM_ERROR);
        assertThat(captor.getValue().getFailureReason()).isEqualTo("服务器内部错误");
    }

    @Test
    void shouldRejectUnknownOperationTypeFilter() {
        assertThatThrownBy(() -> service.page(null, null, "UNKNOWN", null, null, null, null, 1, 20))
                .isInstanceOf(BusinessException.class)
                .hasMessage("非法操作类型");
    }
}

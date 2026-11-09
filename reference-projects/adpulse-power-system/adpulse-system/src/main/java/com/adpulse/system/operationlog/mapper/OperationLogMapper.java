package com.adpulse.system.operationlog.mapper;

import com.adpulse.system.operationlog.model.OperationLog;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 操作日志写入和分页查询持久化接口。 */
@Mapper
public interface OperationLogMapper {

    int insert(OperationLog operationLog);

    List<OperationLog> findPage(
            @Param("keyword") String keyword,
            @Param("moduleCode") String moduleCode,
            @Param("operationType") String operationType,
            @Param("operationResult") Integer operationResult,
            @Param("clientIp") String clientIp,
            @Param("startedAt") LocalDateTime startedAt,
            @Param("endedAt") LocalDateTime endedAt,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long count(
            @Param("keyword") String keyword,
            @Param("moduleCode") String moduleCode,
            @Param("operationType") String operationType,
            @Param("operationResult") Integer operationResult,
            @Param("clientIp") String clientIp,
            @Param("startedAt") LocalDateTime startedAt,
            @Param("endedAt") LocalDateTime endedAt);
}

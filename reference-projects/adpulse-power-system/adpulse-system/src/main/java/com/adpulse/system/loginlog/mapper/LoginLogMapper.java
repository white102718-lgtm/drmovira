package com.adpulse.system.loginlog.mapper;

import com.adpulse.system.loginlog.model.LoginLog;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 登录日志写入和分页查询持久化接口。 */
@Mapper
public interface LoginLogMapper {

    int insert(LoginLog loginLog);

    List<LoginLog> findPage(
            @Param("keyword") String keyword,
            @Param("loginResult") Integer loginResult,
            @Param("authStage") Integer authStage,
            @Param("clientIp") String clientIp,
            @Param("startedAt") LocalDateTime startedAt,
            @Param("endedAt") LocalDateTime endedAt,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long count(
            @Param("keyword") String keyword,
            @Param("loginResult") Integer loginResult,
            @Param("authStage") Integer authStage,
            @Param("clientIp") String clientIp,
            @Param("startedAt") LocalDateTime startedAt,
            @Param("endedAt") LocalDateTime endedAt);
}

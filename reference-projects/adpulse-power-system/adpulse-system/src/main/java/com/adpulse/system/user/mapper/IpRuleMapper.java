package com.adpulse.system.user.mapper;

import com.adpulse.system.user.model.IpRule;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 通用IP规则持久化接口。 */
@Mapper
public interface IpRuleMapper {
    List<IpRule> findGlobalRules();

    IpRule findGlobalById(@Param("id") Long id);

    int insert(IpRule rule);

    int update(IpRule rule);

    int softDelete(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);
}

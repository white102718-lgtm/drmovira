package com.adpulse.main.adaccountasset;

import com.adpulse.main.adaccountasset.AdAccountAssetModels.AccountAttribute;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 广告账户属性配置的 MyBatis 持久化接口。 */
@Mapper
public interface AccountAttributeMapper {
    List<AccountAttribute> findAll();

    AccountAttribute findById(@Param("id") Long id);

    AccountAttribute findByName(@Param("accountAttribute") String accountAttribute);

    int insert(AccountAttribute attribute);

    int update(AccountAttribute attribute);

    int softDelete(@Param("id") Long id, @Param("deletedAt") long deletedAt);
}

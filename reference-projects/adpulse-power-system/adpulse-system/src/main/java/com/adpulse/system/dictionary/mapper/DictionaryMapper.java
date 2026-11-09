package com.adpulse.system.dictionary.mapper;

import com.adpulse.system.dictionary.model.DictionaryItem;
import com.adpulse.system.dictionary.model.DictionaryType;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 字典类型和字典项持久化接口。 */
@Mapper
public interface DictionaryMapper {
    List<DictionaryType> findTypes(
            @Param("keyword") String keyword, @Param("status") Integer status);

    DictionaryType findTypeById(@Param("id") Long id);

    DictionaryType findEnabledTypeByCode(@Param("dictCode") String dictCode);

    int insertType(DictionaryType type);

    int updateType(DictionaryType type);

    int softDeleteType(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);

    List<DictionaryItem> findItems(@Param("dictTypeId") Long dictTypeId);

    List<DictionaryItem> findEnabledItems(@Param("dictTypeId") Long dictTypeId);

    DictionaryItem findItemById(@Param("id") Long id);

    int insertItem(DictionaryItem item);

    int updateItem(DictionaryItem item);

    int softDeleteItem(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);

    int softDeleteItemsByType(
            @Param("dictTypeId") Long dictTypeId,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);
}

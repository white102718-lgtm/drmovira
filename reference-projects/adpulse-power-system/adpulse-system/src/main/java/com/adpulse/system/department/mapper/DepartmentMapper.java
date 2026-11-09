package com.adpulse.system.department.mapper;

import com.adpulse.system.department.model.Department;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 部门持久化访问接口。 */
@Mapper
public interface DepartmentMapper {
    List<Department> findAllActive();

    Department findById(@Param("id") Long id);

    int insert(Department department);

    int update(Department department);

    int updateSubtreePath(
            @Param("oldPrefix") String oldPrefix,
            @Param("newPrefix") String newPrefix,
            @Param("levelDelta") int levelDelta,
            @Param("updatedBy") Long updatedBy);

    int countSubtreeUsers(@Param("path") String path);

    int countSubtreeScopes(@Param("path") String path);

    int countActiveUser(@Param("userId") Long userId);

    int softDeleteSubtree(
            @Param("path") String path,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);
}

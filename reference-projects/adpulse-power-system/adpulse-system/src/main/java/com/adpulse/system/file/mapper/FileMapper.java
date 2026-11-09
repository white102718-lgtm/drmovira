package com.adpulse.system.file.mapper;

import com.adpulse.system.file.model.FileObject;
import com.adpulse.system.file.model.StoredFile;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 文件对象和用户文件记录持久化接口。 */
@Mapper
public interface FileMapper {
    FileObject findAvailableObject(
            @Param("contentHash") String contentHash, @Param("fileSize") long fileSize);

    int insertObject(FileObject fileObject);

    int incrementReference(@Param("id") Long id, @Param("operatorId") Long operatorId);

    int decrementReference(@Param("id") Long id, @Param("operatorId") Long operatorId);

    int insertFile(StoredFile file);

    StoredFile findOwnedFile(@Param("id") Long id, @Param("uploaderId") Long uploaderId);

    StoredFile findActiveFile(@Param("id") Long id);

    StoredFile findReadableFile(
            @Param("id") Long id,
            @Param("userId") Long userId,
            @Param("canManageFeedback") boolean canManageFeedback,
            @Param("canReadAllReports") boolean canReadAllReports);

    int countActiveTaskBindings(@Param("fileId") Long fileId);

    int countActiveFeedbackBindings(@Param("fileId") Long fileId);

    /** 已绑定日报的截图须先在日报中解除关联。 */
    int countActiveDeliveryReportBindings(@Param("fileId") Long fileId);

    int softDeleteFile(
            @Param("id") Long id,
            @Param("uploaderId") Long uploaderId,
            @Param("deletedAt") long deletedAt,
            @Param("operatorId") Long operatorId);
}

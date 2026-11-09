package com.adpulse.system.feedback.mapper;

import com.adpulse.system.feedback.model.Feedback;
import com.adpulse.system.feedback.model.FeedbackAttachment;
import com.adpulse.system.feedback.model.FeedbackUserSnapshot;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 产品反馈、附件绑定和账号快照持久化边界。 */
@Mapper
public interface FeedbackMapper {
    FeedbackUserSnapshot findUserSnapshot(@Param("userId") Long userId);

    int insertFeedback(Feedback feedback);

    List<Long> findOwnedFileIds(@Param("fileIds") List<Long> fileIds, @Param("userId") Long userId);

    int insertAttachments(
            @Param("feedbackId") Long feedbackId,
            @Param("fileIds") List<Long> fileIds,
            @Param("userId") Long userId);

    long countFeedbacks(
            @Param("keyword") String keyword,
            @Param("category") String category,
            @Param("status") String status);

    List<Feedback> findFeedbacks(
            @Param("keyword") String keyword,
            @Param("category") String category,
            @Param("status") String status,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    Feedback findFeedback(@Param("id") Long id);

    List<FeedbackAttachment> findAttachments(@Param("feedbackId") Long feedbackId);

    int updateStatus(
            @Param("id") Long id,
            @Param("status") String status,
            @Param("adminReply") String adminReply,
            @Param("ownerId") Long ownerId,
            @Param("ownerName") String ownerName,
            @Param("processedById") Long processedById,
            @Param("processedByName") String processedByName);
}

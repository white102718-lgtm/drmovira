package com.adpulse.main.project.model;

import lombok.Data;

/** 项目关联用户，用于 AM 和数据专员多选关系。 */
@Data
public class ProjectUserAssignment {
    private Long userId;
    private String userName;
    private Integer sortOrder;
}

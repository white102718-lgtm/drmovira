package com.adpulse.main.project.model;

import lombok.Data;

/** 项目轻量选项查询行。 */
@Data
public class ProjectOptionRow {
    private Long id;
    private String projectCode;
    private String projectName;
    private String status;
    private String platformValue;
}

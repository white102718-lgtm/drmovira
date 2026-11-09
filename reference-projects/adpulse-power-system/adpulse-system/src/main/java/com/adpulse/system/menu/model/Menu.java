package com.adpulse.system.menu.model;

import com.adpulse.system.common.model.AuditedEntity;
import java.util.ArrayList;
import java.util.List;
import lombok.Data;
import lombok.EqualsAndHashCode;

/** 菜单和按钮权限树节点。 */
@Data
@EqualsAndHashCode(callSuper = true)
public class Menu extends AuditedEntity {
    private Long parentId;
    private Integer menuType;
    private String menuCode;
    private String menuName;
    private String routePath;
    private String component;
    private String icon;
    private String permissionCode;
    private Integer visible;
    private Integer cacheable;
    private String externalLink;
    private Integer sortOrder;
    private Integer status;
    private String remark;
    private List<Menu> children = new ArrayList<>();
}

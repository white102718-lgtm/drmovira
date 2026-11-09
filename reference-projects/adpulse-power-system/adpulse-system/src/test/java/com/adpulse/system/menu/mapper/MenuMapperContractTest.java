package com.adpulse.system.menu.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

/** 当前用户菜单查询的数据权限约束测试。 */
class MenuMapperContractTest {

    @Test
    void shouldReturnAllNotDeletedMenusForManagementTree() throws IOException {
        String mapperXml = readMapperXml();

        assertThat(mapperXml)
                .containsPattern(
                        "(?s)<select id=\"findAllNotDeleted\".*?WHERE deleted_at = 0\\s+ORDER BY sort_order, id.*?</select>")
                .doesNotContainPattern(
                        "(?s)<select id=\"findAllNotDeleted\".*?status = 1.*?</select>");
    }

    @Test
    void shouldResolveOnlyActiveRoleMenusAndExcludeButtons() throws IOException {
        String mapperXml = readMapperXml();

        assertThat(mapperXml)
                .contains("findAuthorizedNavigationMenus")
                .contains("INNER JOIN sys_user_role")
                .contains("INNER JOIN sys_role r")
                .contains("INNER JOIN sys_role_menu")
                .contains("INNER JOIN authorized_tree child")
                .contains("u.status = 1")
                .contains("r.status = 1")
                .contains("m.status = 1")
                .contains("menu_type IN (1, 2)");
    }

    private String readMapperXml() throws IOException {
        return Files.readString(
                Path.of("src", "main", "resources", "mapper", "menu", "MenuMapper.xml"));
    }
}

package com.adpulse.system.user.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

/** 校验超级管理员授权分支及身份字段不可通过普通写入赋值。 */
class SuperAdminMapperContractTest {
    @Test
    void shouldGrantEnabledResourcesIndependentlyOfRoleAssignments() throws Exception {
        String permissions = sql("auth/AuthMapper", "findPermissionCodes", Map.of("userId", 7L));
        assertThat(permissions)
                .contains("UNION", "u.is_super_admin = 1", "u.status = 1", "u.deleted_at = 0");
        String menus =
                sql("menu/MenuMapper", "findAuthorizedNavigationMenus", Map.of("userId", 7L));
        assertThat(menus)
                .contains(
                        "u.is_super_admin = 1",
                        "u.status = 1",
                        "u.deleted_at = 0",
                        "menu_type IN (1, 2)");
    }

    @Test
    void shouldNeverWriteSuperAdminFlagThroughUserManagement() throws Exception {
        for (String method :
                new String[] {"insert", "update", "updateFeishuLocalFields", "updateProfile"}) {
            assertThat(sql("user/UserMapper", method, Map.of())).doesNotContain("is_super_admin");
        }
        assertThat(sql("user/UserMapper", "findById", Map.of("id", 7L))).contains("is_super_admin");
    }

    @Test
    void shouldGuardSharedRolesAndGlobalMenuResources() throws Exception {
        assertThat(
                        sql(
                                "role/RoleMapper",
                                "hasOtherSuperAdminUser",
                                Map.of("roleId", 3L, "operatorId", 7L)))
                .contains(
                        "ur.deleted_at = 0",
                        "u.deleted_at = 0",
                        "u.is_super_admin = 1",
                        "u.id <> ?");
        assertThat(sql("menu/MenuMapper", "isMenuMaintenanceForbidden", Map.of("operatorId", 7L)))
                .contains("AND NOT EXISTS", "id = ?", "is_super_admin = 1", "status = 1");
    }

    private String sql(String mapper, String method, Map<String, Object> parameters)
            throws Exception {
        Configuration configuration = new Configuration();
        String resource = "mapper/" + mapper + ".xml";
        try (var input = getClass().getClassLoader().getResourceAsStream(resource)) {
            new XMLMapperBuilder(input, configuration, resource, configuration.getSqlFragments())
                    .parse();
        }
        return configuration
                .getMappedStatement(method)
                .getBoundSql(parameters)
                .getSql()
                .replaceAll("\\s+", " ");
    }
}

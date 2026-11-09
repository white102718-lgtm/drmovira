package com.adpulse.system.application.service;

import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.application.mapper.ApplicationDefinitionMapper;
import com.adpulse.system.application.model.ApplicationDefinition;
import com.adpulse.system.common.security.CurrentUser;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 申请入口删除行为测试。 */
@ExtendWith(MockitoExtension.class)
class ApplicationDefinitionServiceTest {

    @Mock private ApplicationDefinitionMapper mapper;
    @Mock private ApplicationTypeService applicationTypeService;
    @InjectMocks private ApplicationDefinitionService service;

    @BeforeEach
    void setCurrentUser() {
        CurrentUser user = new CurrentUser(7L, "session", "测试用户", Set.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", Set.of()));
    }

    @AfterEach
    void clearCurrentUser() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldSoftDeleteExistingDefinition() {
        ApplicationDefinition definition = new ApplicationDefinition();
        definition.setId(18L);
        when(mapper.findById(18L)).thenReturn(definition);

        service.delete(18L);

        verify(mapper).softDelete(eq(18L), anyLong(), eq(7L));
    }
}

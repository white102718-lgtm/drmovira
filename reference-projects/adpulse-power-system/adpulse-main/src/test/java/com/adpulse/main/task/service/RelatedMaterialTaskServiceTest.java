package com.adpulse.main.task.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

import com.adpulse.main.integration.security.IntegrationSecretCipher;
import com.adpulse.main.task.dto.TaskViews;
import com.adpulse.main.task.mapper.TaskMapper;
import com.adpulse.main.task.model.TaskModels;
import com.adpulse.main.task.mongo.MongoMaterialTaskQueryProvider;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 关联素材任务必须继承来源投放任务的查看权限。 */
class RelatedMaterialTaskServiceTest {
    private final TaskMapper mapper = mock(TaskMapper.class);
    private final MongoMaterialTaskQueryProvider provider =
            mock(MongoMaterialTaskQueryProvider.class);
    private final TaskService service =
            new TaskService(
                    mapper, new ObjectMapper(), mock(IntegrationSecretCipher.class), provider);

    @BeforeEach
    void authenticate() {
        var user = new CurrentUser(9L, "session", "创建人", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", List.of()));
    }

    @AfterEach
    void clearAuthentication() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void returnsMongoTasksAndBoundsPagination() {
        when(mapper.findTask(1L)).thenReturn(task("DELIVERY", 9L));
        var result = new TaskViews.Page<TaskViews.RelatedMaterialTask>(List.of(), 0, 1, 100);
        when(provider.findBySourceTaskId(1L, 1, 100)).thenReturn(result);
        assertThat(service.relatedMaterialTasks(1L, -1, 200)).isSameAs(result);
    }

    @Test
    void rejectsInvisibleTaskBeforeQueryingMongo() {
        when(mapper.findTask(1L)).thenReturn(task("DELIVERY", 10L));
        assertThatThrownBy(() -> service.relatedMaterialTasks(1L, 1, 20))
                .hasMessageContaining("没有权限");
        verifyNoInteractions(provider);
    }

    @Test
    void rejectsMissingTaskBeforeQueryingMongo() {
        assertThatThrownBy(() -> service.relatedMaterialTasks(1L, 1, 20))
                .hasMessageContaining("不存在");
        verifyNoInteractions(provider);
    }

    @Test
    void rejectsMaterialSourceTask() {
        when(mapper.findTask(1L)).thenReturn(task("MATERIAL", 9L));
        assertThatThrownBy(() -> service.relatedMaterialTasks(1L, 1, 20))
                .hasMessageContaining("仅投放任务");
        verifyNoInteractions(provider);
    }

    private TaskModels.Task task(String type, Long creatorId) {
        var task = new TaskModels.Task();
        task.setId(1L);
        task.setTaskType(type);
        task.setCreatorId(creatorId);
        return task;
    }
}

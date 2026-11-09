package com.adpulse.main.manualtask;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.manualtask.ManualTaskModels.AssignmentResult;
import com.adpulse.main.manualtask.ManualTaskModels.UserCandidate;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

/** 飞书广告账户使用人手动同步规则测试。 */
@ExtendWith(MockitoExtension.class)
class FeishuAdAccountUserSyncTaskTest {
    @Mock private MongoTemplate mongoTemplate;
    @Mock private ManualTaskMapper mapper;
    @Mock private FeishuAdAccountAssignmentWriter writer;

    @Test
    void shouldScanEveryRecordWithoutFilteringInUseAndNormalizeAccountId() {
        Document inactive =
                new Document("account_id", "act_123")
                        .append("user_name", "张三，李四")
                        .append("in_use", false);
        when(mongoTemplate.find(
                        any(Query.class), eq(Document.class), eq("feishu_account_used_record")))
                .thenReturn(List.of(inactive));
        UserCandidate zhang = user(1L, "张三");
        UserCandidate li = user(2L, "李四");
        when(mapper.findUsersByNames(any())).thenReturn(List.of(zhang, li));
        when(writer.append(eq("123"), any(), eq(7L))).thenReturn(new AssignmentResult(true, 2, 0));

        var task = new FeishuAdAccountUserSyncTask(mongoTemplate, mapper, writer);
        task.execute(new ManualTaskContext(9L, 7L, new ManualTaskLog(9L, mapper)));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate)
                .find(query.capture(), eq(Document.class), eq("feishu_account_used_record"));
        assertThat(query.getValue().getQueryObject()).isEmpty();
        verify(writer).append(eq("123"), eq(List.of(zhang, li)), eq(7L));
    }

    private UserCandidate user(Long id, String name) {
        UserCandidate user = new UserCandidate();
        user.setId(id);
        user.setRealName(name);
        user.setDisplayName(name);
        return user;
    }
}

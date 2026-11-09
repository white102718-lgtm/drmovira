package com.adpulse.main.manualtask;

import com.adpulse.main.manualtask.ManualTaskModels.Execution;
import com.adpulse.main.manualtask.ManualTaskViews.Page;
import com.adpulse.main.manualtask.ManualTaskViews.Task;
import com.adpulse.system.common.security.CurrentUser;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

/** 手动任务目录、触发事件和历史记录服务。 */
@Service
public class ManualTaskService {
    private final ManualTaskMapper mapper;
    private final Map<String, ManualTaskDefinition> definitions;

    public ManualTaskService(ManualTaskMapper mapper, List<ManualTaskDefinition> definitions) {
        this.mapper = mapper;
        this.definitions =
                definitions.stream()
                        .collect(
                                Collectors.toMap(
                                        ManualTaskDefinition::code,
                                        Function.identity(),
                                        (a, b) -> a,
                                        LinkedHashMap::new));
    }

    public List<Task> tasks() {
        return definitions.values().stream()
                .filter(this::canAccess)
                .map(
                        d ->
                                new Task(
                                        d.code(),
                                        d.name(),
                                        d.description(),
                                        mapper.countActive(d.code()) > 0,
                                        d.actions().stream()
                                                .map(
                                                        action ->
                                                                new ManualTaskViews.Action(
                                                                        action.code(),
                                                                        action.name(),
                                                                        action.description(),
                                                                        action.dangerous(),
                                                                        action.confirmationText()))
                                                .toList()))
                .toList();
    }

    public ManualTaskViews.Execution trigger(
            String taskCode, ManualTaskViews.TriggerRequest request) {
        ManualTaskDefinition definition = definitions.get(taskCode);
        if (definition == null) throw new ManualTaskException("未知的手动任务：" + taskCode);
        if (!canAccess(definition)) throw new ManualTaskException("当前账号无权执行该任务");
        String actionCode =
                request == null || request.actionCode() == null || request.actionCode().isBlank()
                        ? "EXECUTE"
                        : request.actionCode();
        ManualTaskAction action =
                definition.actions().stream()
                        .filter(item -> item.code().equals(actionCode))
                        .findFirst()
                        .orElseThrow(() -> new ManualTaskException("任务不支持该操作：" + actionCode));
        if (action.dangerous()
                && !java.util.Objects.equals(
                        action.confirmationText(),
                        request == null ? null : request.confirmationText())) {
            throw new ManualTaskException("确认文字不正确，请重新输入");
        }
        CurrentUser user = currentUser();
        Execution execution = new Execution();
        execution.setTaskCode(definition.code());
        execution.setTaskName(definition.name());
        execution.setActionCode(action.code());
        execution.setActionName(action.name());
        execution.setTriggeredBy(user.userId());
        execution.setTriggeredByName(
                user.displayName() == null ? user.getUsername() : user.displayName());
        try {
            mapper.insertExecution(execution);
        } catch (DuplicateKeyException exception) {
            throw new ManualTaskException("该任务正在排队或执行中，请稍后再试");
        }
        return view(mapper.findExecution(execution.getId()), true);
    }

    public Page executions(String taskCode, int page, int pageSize) {
        ManualTaskDefinition requestedDefinition = definitions.get(taskCode);
        if (requestedDefinition != null && !canAccess(requestedDefinition)) {
            throw new ManualTaskException("当前账号无权查看该任务");
        }
        List<String> excludedTaskCodes = inaccessibleTaskCodes();
        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(pageSize, 1), 100);
        List<ManualTaskViews.Execution> items =
                mapper
                        .findExecutions(
                                taskCode,
                                excludedTaskCodes,
                                (long) (safePage - 1) * safeSize,
                                safeSize)
                        .stream()
                        .map(e -> view(e, false))
                        .toList();
        return new Page(
                items, mapper.countExecutions(taskCode, excludedTaskCodes), safePage, safeSize);
    }

    public ManualTaskViews.Execution execution(Long id) {
        Execution execution = mapper.findExecution(id);
        if (execution == null) throw new ManualTaskException("执行记录不存在");
        ManualTaskDefinition definition = definitions.get(execution.getTaskCode());
        if (definition != null && !canAccess(definition)) {
            throw new ManualTaskException("当前账号无权查看该任务");
        }
        return view(execution, true);
    }

    ManualTaskDefinition definition(String code) {
        return definitions.get(code);
    }

    /** worker 只能领取当前实例实际注册的任务，避免滚动发布期间旧实例误领新任务。 */
    List<String> definitionCodes() {
        return List.copyOf(definitions.keySet());
    }

    private boolean canAccess(ManualTaskDefinition definition) {
        if (definition.requiredAuthority() == null || definition.requiredAuthority().isBlank()) {
            return true;
        }
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        return authentication != null
                && authentication.getAuthorities().stream()
                        .anyMatch(
                                authority ->
                                        definition
                                                .requiredAuthority()
                                                .equals(authority.getAuthority()))
                && authentication.getAuthorities().stream()
                        .anyMatch(
                                authority ->
                                        "system:manual-task:execute"
                                                .equals(authority.getAuthority()));
    }

    private List<String> inaccessibleTaskCodes() {
        return definitions.values().stream()
                .filter(definition -> !canAccess(definition))
                .map(ManualTaskDefinition::code)
                .toList();
    }

    private CurrentUser currentUser() {
        Object principal = SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (!(principal instanceof CurrentUser user)) throw new ManualTaskException("当前登录会话无效");
        return user;
    }

    private ManualTaskViews.Execution view(Execution e, boolean includeLog) {
        return new ManualTaskViews.Execution(
                String.valueOf(e.getId()),
                e.getTaskCode(),
                e.getTaskName(),
                e.getActionCode(),
                e.getActionName(),
                e.getStatus(),
                String.valueOf(e.getTriggeredBy()),
                e.getTriggeredByName(),
                e.getTriggeredAt(),
                e.getStartedAt(),
                e.getFinishedAt(),
                includeLog ? e.getLogContent() : null);
    }

    /** 可直接展示给管理员的手动任务业务异常。 */
    public static class ManualTaskException extends RuntimeException {
        public ManualTaskException(String message) {
            super(message);
        }
    }
}

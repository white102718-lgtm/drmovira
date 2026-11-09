package com.adpulse.main.manualtask;

import java.util.List;

/** 可由管理员重复触发的手动任务定义。 */
public interface ManualTaskDefinition {
    String code();

    String name();

    String description();

    void execute(ManualTaskContext context);

    /** 返回任务支持的操作；普通任务保持单一执行动作。 */
    default List<ManualTaskAction> actions() {
        return List.of(ManualTaskAction.execute());
    }

    /** 返回任务额外要求的权限；普通任务不增加额外限制。 */
    default String requiredAuthority() {
        return null;
    }

    /** 按操作执行任务；旧任务仅接受默认执行动作。 */
    default void execute(ManualTaskContext context, String actionCode) {
        if (!"EXECUTE".equals(actionCode)) {
            throw new IllegalArgumentException("任务不支持该操作：" + actionCode);
        }
        execute(context);
    }
}

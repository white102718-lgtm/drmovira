package com.adpulse.main.manualtask;

/** 手动任务可触发操作及其确认要求。 */
public record ManualTaskAction(
        String code, String name, String description, boolean dangerous, String confirmationText) {
    /** 普通手动任务的默认操作。 */
    public static ManualTaskAction execute() {
        return new ManualTaskAction("EXECUTE", "执行任务", "确认执行该手动任务。", false, null);
    }
}

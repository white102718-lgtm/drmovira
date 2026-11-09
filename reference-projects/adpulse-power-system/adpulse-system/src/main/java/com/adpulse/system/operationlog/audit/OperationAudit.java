package com.adpulse.system.operationlog.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** 标记必须与业务写入一起记录的系统管理操作。 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface OperationAudit {

    String module();

    OperationType type();

    String name();

    String targetType();

    String targetIdParameter() default "";
}

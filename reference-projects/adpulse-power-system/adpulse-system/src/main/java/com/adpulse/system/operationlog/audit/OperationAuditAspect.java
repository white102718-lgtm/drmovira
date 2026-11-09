package com.adpulse.system.operationlog.audit;

import com.adpulse.system.auth.security.ClientIpResolver;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.operationlog.service.OperationLogService;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Objects;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.util.StringUtils;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/** 将受标记的系统管理写接口与成功审计日志放在同一数据库事务中。 */
@Aspect
@Component
public class OperationAuditAspect {

    private final OperationLogService operationLogService;
    private final ClientIpResolver clientIpResolver;
    private final TransactionTemplate transactionTemplate;

    public OperationAuditAspect(
            OperationLogService operationLogService,
            ClientIpResolver clientIpResolver,
            PlatformTransactionManager transactionManager) {
        this.operationLogService = operationLogService;
        this.clientIpResolver = clientIpResolver;
        this.transactionTemplate = new TransactionTemplate(transactionManager);
    }

    /** 执行业务写入并记录成功；业务失败回滚后另开事务记录失败。 */
    @Around("@annotation(audit)")
    public Object audit(ProceedingJoinPoint joinPoint, OperationAudit audit) throws Throwable {
        OperationLogContext context = buildContext(joinPoint, audit);
        try {
            return transactionTemplate.execute(status -> executeInTransaction(joinPoint, context));
        } catch (OperationInvocationException exception) {
            Throwable cause = Objects.requireNonNull(exception.getCause());
            try {
                operationLogService.recordFailure(context, cause);
            } catch (RuntimeException auditFailure) {
                cause.addSuppressed(auditFailure);
            }
            throw cause;
        }
    }

    private Object executeInTransaction(
            ProceedingJoinPoint joinPoint, OperationLogContext context) {
        try {
            Object result = joinPoint.proceed();
            operationLogService.recordSuccess(context);
            return result;
        } catch (Throwable failure) {
            throw new OperationInvocationException(failure);
        }
    }

    private OperationLogContext buildContext(ProceedingJoinPoint joinPoint, OperationAudit audit) {
        HttpServletRequest request = currentRequest();
        CurrentUser currentUser = currentUser();
        return new OperationLogContext(
                currentUser == null ? null : currentUser.userId(),
                currentUser == null ? null : currentUser.displayName(),
                audit.module(),
                audit.type(),
                audit.name(),
                audit.targetType(),
                resolveTargetId(joinPoint, audit.targetIdParameter()),
                request == null ? "UNKNOWN" : request.getMethod(),
                request == null ? "UNKNOWN" : request.getRequestURI(),
                request == null ? "UNKNOWN" : clientIpResolver.resolve(request),
                request == null ? null : request.getHeader("User-Agent"));
    }

    private String resolveTargetId(ProceedingJoinPoint joinPoint, String parameterName) {
        if (!StringUtils.hasText(parameterName)) {
            return null;
        }
        MethodSignature signature = (MethodSignature) joinPoint.getSignature();
        String[] parameterNames = signature.getParameterNames();
        Object[] arguments = joinPoint.getArgs();
        if (parameterNames == null) {
            return null;
        }
        for (int index = 0; index < parameterNames.length; index++) {
            if (parameterName.equals(parameterNames[index]) && arguments[index] != null) {
                return arguments[index].toString();
            }
        }
        return null;
    }

    private HttpServletRequest currentRequest() {
        if (RequestContextHolder.getRequestAttributes()
                instanceof ServletRequestAttributes attributes) {
            return attributes.getRequest();
        }
        return null;
    }

    private CurrentUser currentUser() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication != null && authentication.getPrincipal() instanceof CurrentUser user) {
            return user;
        }
        return null;
    }

    private static final class OperationInvocationException extends RuntimeException {

        private OperationInvocationException(Throwable cause) {
            super(cause);
        }
    }
}

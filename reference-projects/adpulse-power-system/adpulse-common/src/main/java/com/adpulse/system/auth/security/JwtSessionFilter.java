package com.adpulse.system.auth.security;

import com.adpulse.system.auth.model.ServerSession;
import com.adpulse.system.auth.service.JwtService;
import com.adpulse.system.auth.service.SessionStore;
import com.adpulse.system.common.security.CurrentUser;
import io.jsonwebtoken.Claims;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** 同时校验 JWT 和 Redis 权威会话的认证过滤器。 */
@Component
public class JwtSessionFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(JwtSessionFilter.class);

    private final JwtService jwtService;
    private final SessionStore sessionStore;
    private final SessionUserValidator sessionUserValidator;
    private final ClientIpResolver clientIpResolver;

    public JwtSessionFilter(
            JwtService jwtService,
            SessionStore sessionStore,
            SessionUserValidator sessionUserValidator,
            ClientIpResolver clientIpResolver) {
        this.jwtService = jwtService;
        this.sessionStore = sessionStore;
        this.sessionUserValidator = sessionUserValidator;
        this.clientIpResolver = clientIpResolver;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ")) {
            filterChain.doFilter(request, response);
            return;
        }

        try {
            Claims claims = jwtService.parse(header.substring(7));
            String sessionId = claims.get("sid", String.class);
            Long userId = Long.valueOf(claims.getSubject());
            ServerSession session = sessionStore.find(sessionId).orElseThrow();
            if (!session.userId().equals(userId)) {
                throw new IllegalStateException("会话用户与令牌主体不一致");
            }
            String clientIp = clientIpResolver.resolve(request);
            SessionUserValidator.ValidatedUser user =
                    sessionUserValidator.validate(userId, clientIp).orElse(null);
            if (user == null) {
                sessionStore.delete(sessionId, userId);
                throw new IllegalStateException("用户状态或IP策略已变化");
            }
            var authorities = createAuthorities(session);
            CurrentUser principal =
                    new CurrentUser(
                            userId,
                            sessionId,
                            user.displayName(),
                            session.englishNickname(),
                            authorities);
            var authentication =
                    new UsernamePasswordAuthenticationToken(principal, null, authorities);
            SecurityContextHolder.getContext().setAuthentication(authentication);
        } catch (DataAccessException exception) {
            log.error("Redis会话校验失败，请检查各服务的Redis连接配置", exception);
            SecurityContextHolder.clearContext();
        } catch (Exception exception) {
            SecurityContextHolder.clearContext();
        }
        filterChain.doFilter(request, response);
    }

    static List<SimpleGrantedAuthority> createAuthorities(ServerSession session) {
        return Stream.concat(
                        session.permissions().stream(),
                        session.roleCodes().stream().map(roleCode -> "ROLE_" + roleCode))
                .distinct()
                .map(SimpleGrantedAuthority::new)
                .toList();
    }
}

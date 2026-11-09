package com.adpulse.system.auth.service;

import com.adpulse.system.config.SecurityProperties;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Component;

/** 负责签发和验证仅承载会话标识的 JWT。 */
@Component
public class JwtService {

    private final SecurityProperties properties;
    private final SecretKey key;

    public JwtService(SecurityProperties properties) {
        this.properties = properties;
        this.key = Keys.hmacShaKeyFor(properties.jwtSecret().getBytes(StandardCharsets.UTF_8));
    }

    /** 签发与 Redis 会话同生命周期的访问令牌。 */
    public String issue(Long userId, String sessionId) {
        Instant now = Instant.now();
        return Jwts.builder()
                .issuer(properties.jwtIssuer())
                .subject(userId.toString())
                .claim("sid", sessionId)
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plus(properties.sessionTtl())))
                .signWith(key)
                .compact();
    }

    /** 验证签名、签发方和过期时间并返回声明。 */
    public Claims parse(String token) {
        return Jwts.parser()
                .verifyWith(key)
                .requireIssuer(properties.jwtIssuer())
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }
}

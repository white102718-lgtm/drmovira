package com.adpulse.system.common.security;

import java.util.Collection;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

/** 当前通过服务端会话校验的用户身份。 */
public record CurrentUser(
        Long userId,
        String sessionId,
        String displayName,
        String englishNickname,
        Collection<? extends GrantedAuthority> authorities)
        implements UserDetails {

    /** 兼容不依赖英文名的旧调用方。 */
    public CurrentUser(
            Long userId,
            String sessionId,
            String displayName,
            Collection<? extends GrantedAuthority> authorities) {
        this(userId, sessionId, displayName, null, authorities);
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return "";
    }

    @Override
    public String getUsername() {
        return userId.toString();
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }
}

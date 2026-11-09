package com.adpulse.main.safeheron.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.safeheron.dto.SafeheronRequests.ApproverSave;
import com.adpulse.main.safeheron.dto.SafeheronRequests.RuleQuery;
import com.adpulse.main.safeheron.dto.SafeheronRequests.RuleSave;
import com.adpulse.main.safeheron.dto.SafeheronRequests.TeamCreate;
import com.adpulse.main.safeheron.mapper.SafeheronMapper;
import com.adpulse.main.safeheron.security.SafeheronSecretCipher;
import com.adpulse.system.common.security.CurrentUser;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** Safeheron规则引用校验与分页边界测试。 */
@ExtendWith(MockitoExtension.class)
class SafeheronServiceTest {
    @Mock private SafeheronMapper mapper;
    @Mock private SafeheronSecretCipher cipher;

    private SafeheronService service;

    @BeforeEach
    void setUp() {
        service = new SafeheronService(mapper, cipher);
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldNormalizeRulePagination() {
        when(mapper.findRules(0, 500)).thenReturn(List.of());
        when(mapper.countRules()).thenReturn(0L);

        var result = service.listRules(new RuleQuery(0, 9999));

        assertThat(result.page()).isEqualTo(1);
        assertThat(result.pageSize()).isEqualTo(500);
        verify(mapper).findRules(0, 500);
    }

    @Test
    void shouldRejectRuleWhenDepartmentIsUnavailable() {
        RuleSave request =
                new RuleSave(
                        9L,
                        "wallet-1",
                        "USDT_TRC20",
                        BigDecimal.TEN,
                        30,
                        1,
                        BigDecimal.ZERO,
                        BigDecimal.ONE,
                        "审批组",
                        1);

        assertThatThrownBy(() -> service.createRule(request))
                .isInstanceOf(SafeheronService.SafeheronException.class)
                .hasMessageContaining("部门");
        verify(mapper, never()).insertRule(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void shouldValidateAllApproversBeforeUpdatingAnyTeam() {
        when(mapper.findTeam("team-a"))
                .thenReturn(new com.adpulse.main.safeheron.model.SafeheronModels.Team());

        assertThatThrownBy(() -> service.updateApprovers(List.of(new ApproverSave("team-a", 99L))))
                .isInstanceOf(SafeheronService.SafeheronException.class)
                .hasMessageContaining("审批用户");
        verify(mapper, never())
                .updateTeamApprover(
                        org.mockito.ArgumentMatchers.anyString(),
                        org.mockito.ArgumentMatchers.anyLong(),
                        org.mockito.ArgumentMatchers.anyLong());
    }

    @Test
    void shouldEncryptPrivateKeyBeforeInsertingTeam() throws Exception {
        var generator = java.security.KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        var keyPair = generator.generateKeyPair();
        String privateKey =
                java.util.Base64.getEncoder().encodeToString(keyPair.getPrivate().getEncoded());
        String publicKey =
                java.util.Base64.getEncoder().encodeToString(keyPair.getPublic().getEncoded());
        CurrentUser user = new CurrentUser(9L, "session", "测试用户", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", List.of()));
        TeamCreate request =
                new TeamCreate(
                        " 1 ",
                        " 默认团队 ",
                        null,
                        " api-key ",
                        "REDACTED_REFERENCE_SECRET",
                        publicKey,
                        null);
        when(cipher.encrypt(privateKey)).thenReturn("ciphertext-value");

        var result = service.createTeam(request);

        assertThat(result.teamId()).isEqualTo("1");
        var captor =
                org.mockito.ArgumentCaptor.forClass(
                        com.adpulse.main.safeheron.model.SafeheronModels.Team.class);
        verify(mapper).insertTeam(captor.capture());
        assertThat(captor.getValue().getPrivateKeyCiphertext()).isEqualTo("ciphertext-value");
        assertThat(captor.getValue().getPrivateKeyCiphertext()).doesNotContain("private-key");
        assertThat(captor.getValue().getCreatedBy()).isEqualTo(9L);
    }

    @Test
    void shouldRejectInvalidPrivateKeyBeforeEncryptionOrInsert() {
        var request =
                new TeamCreate(
                        "1", "默认团队", null, "api-key", "invalid-private-key", "public-key", null);
        assertThatThrownBy(() -> service.createTeam(request))
                .isInstanceOf(SafeheronService.SafeheronException.class)
                .hasMessageContaining("私钥校验失败");
        verify(cipher, never()).encrypt(org.mockito.ArgumentMatchers.anyString());
        verify(mapper, never()).insertTeam(org.mockito.ArgumentMatchers.any());
    }
}

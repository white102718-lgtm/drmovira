package com.adpulse.main.safeheron.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.safeheron.mapper.SafeheronMapper;
import com.adpulse.main.safeheron.model.SafeheronModels.Coin;
import com.adpulse.main.safeheron.model.SafeheronModels.Wallet;
import com.adpulse.main.safeheron.security.SafeheronSecretCipher;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** 项目钱包幂等关联及安全地址读取测试。 */
@ExtendWith(MockitoExtension.class)
class SafeheronWalletServiceTest {
    @Mock private SafeheronMapper mapper;
    @Mock private SafeheronSecretCipher cipher;

    private SafeheronWalletService service;

    @BeforeEach
    void setUp() {
        service = new SafeheronWalletService(mapper, cipher);
    }

    @Test
    void shouldBatchWalletsAndCoinsWithoutMixingAddresses() {
        Wallet first = new Wallet();
        first.setId(1L);
        first.setAccountKey("key-1");
        first.setCustomerRefId("P1");
        Wallet second = new Wallet();
        second.setId(2L);
        second.setAccountKey("key-2");
        second.setCustomerRefId("P2");
        Coin eth = coin("ETH", "encrypted-one", "ETH");
        eth.setAccountKey("key-1");
        Coin usdt = coin("USDT_TRC20", "encrypted-two", "TRX");
        usdt.setAccountKey("key-2");
        when(mapper.findWalletsByCustomerRefIds(List.of("P1", "P2")))
                .thenReturn(List.of(first, second));
        when(mapper.findWalletCoinsByAccountKeys(List.of("key-1", "key-2")))
                .thenReturn(List.of(usdt, eth));
        when(cipher.decrypt("encrypted-one")).thenReturn("address-one");
        when(cipher.decrypt("encrypted-two")).thenReturn("address-two");

        var result = service.findProjectWallets(List.of("P1", "P2", "P1"));

        assertThat(result.get("P1").ethAddress()).isEqualTo("address-one");
        assertThat(result.get("P1").usdtAddress()).isEmpty();
        assertThat(result.get("P2").ethAddress()).isEmpty();
        assertThat(result.get("P2").usdtAddress()).isEqualTo("address-two");
        verify(mapper, never()).findWalletCoins(org.mockito.ArgumentMatchers.any());
        verify(mapper, never()).findWalletByCustomerRefId(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void shouldSkipCoinQueriesWhenNoWalletExists() {
        assertThat(service.findProjectWallets(List.of())).isEmpty();
        org.mockito.Mockito.verifyNoInteractions(mapper, cipher);
        assertThat(service.findProjectWallets(List.of("P1"))).isEmpty();
        verify(mapper, never()).findWalletCoinsByAccountKeys(org.mockito.ArgumentMatchers.any());
        org.mockito.Mockito.verifyNoInteractions(cipher);
    }

    @Test
    void shouldReuseExistingProjectWalletWithoutCallingRemoteTeam() {
        Wallet wallet = new Wallet();
        wallet.setId(7L);
        wallet.setAccountKey("account-key");
        wallet.setAccountName("原始钱包名称");
        wallet.setCustomerRefId("PRJ-1");
        Coin eth = coin("ETH", "eth-cipher", "ETH");
        Coin usdt = coin("USDT_TRC20", "usdt-cipher", "TRX");
        when(mapper.findWalletByCustomerRefId("PRJ-1")).thenReturn(wallet);
        when(mapper.findWalletCoins("account-key")).thenReturn(List.of(eth, usdt));
        when(cipher.decrypt("eth-cipher")).thenReturn("0x123");
        when(cipher.decrypt("usdt-cipher")).thenReturn("T123");

        var result = service.createProjectWallet("PRJ-1", "项目一");

        assertThat(result.id()).isEqualTo("7");
        assertThat(result.accountName()).isEqualTo("原始钱包名称");
        assertThat(result.ethAddress()).isEqualTo("0x123");
        assertThat(result.usdtAddress()).isEqualTo("T123");
        assertThat(result.feeUnit()).isEqualTo("TRX");
        verify(mapper, never()).findTeam(SafeheronWalletService.DEFAULT_TEAM_ID);
    }

    @Test
    void shouldRejectCreationWhenDefaultTeamIsUnavailable() {
        when(mapper.findWalletByCustomerRefId("PRJ-1")).thenReturn(null);
        when(mapper.findTeam(SafeheronWalletService.DEFAULT_TEAM_ID)).thenReturn(null);

        assertThatThrownBy(() -> service.createProjectWallet("PRJ-1", "项目一"))
                .isInstanceOf(SafeheronWalletService.SafeheronWalletException.class)
                .hasMessageContaining("默认团队");

        verify(mapper, never()).insertWallet(org.mockito.ArgumentMatchers.any());
    }

    private Coin coin(String coinKey, String addressCiphertext, String feeUnit) {
        Coin coin = new Coin();
        coin.setCoinKey(coinKey);
        coin.setAddressCiphertext(addressCiphertext);
        coin.setFeeUnit(feeUnit);
        return coin;
    }
}

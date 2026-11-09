package com.adpulse.main.safeheron.service;

import com.adpulse.main.project.dto.ProjectViews.ProjectWallet;
import com.adpulse.main.safeheron.mapper.SafeheronMapper;
import com.adpulse.main.safeheron.model.SafeheronModels.Coin;
import com.adpulse.main.safeheron.model.SafeheronModels.Team;
import com.adpulse.main.safeheron.model.SafeheronModels.Wallet;
import com.adpulse.main.safeheron.security.SafeheronSecretCipher;
import com.safeheron.client.api.AccountApiService;
import com.safeheron.client.config.SafeheronConfig;
import com.safeheron.client.request.CreateAccountRequest;
import com.safeheron.client.response.CreateAccountResponse;
import com.safeheron.client.utils.ServiceCreator;
import com.safeheron.client.utils.ServiceExecutor;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

/** Safeheron项目钱包创建、幂等关联与安全展示服务。 */
@Service
public class SafeheronWalletService {
    private static final Logger log = LoggerFactory.getLogger(SafeheronWalletService.class);
    static final String DEFAULT_TEAM_ID = "1";
    private static final List<String> DEPOSIT_COINS = List.of("ETH", "USDT_TRC20");
    private static final Set<String> REQUIRED_DEPOSIT_COINS = Set.copyOf(DEPOSIT_COINS);
    private final SafeheronMapper mapper;
    private final SafeheronSecretCipher cipher;

    public SafeheronWalletService(SafeheronMapper mapper, SafeheronSecretCipher cipher) {
        this.mapper = mapper;
        this.cipher = cipher;
    }

    /** 按项目编码幂等创建入金币钱包；远端失败时抛出异常，由项目事务回滚本地数据。 */
    public ProjectWallet createProjectWallet(String projectCode, String projectName) {
        Wallet existing = mapper.findWalletByCustomerRefId(projectCode);
        if (existing != null) {
            return projectWallet(existing);
        }

        Team team = mapper.findTeam(DEFAULT_TEAM_ID);
        if (team == null) {
            throw new SafeheronWalletException("Safeheron默认团队未配置或已停用");
        }
        CreateAccountRequest request = new CreateAccountRequest();
        request.setAccountName(projectName);
        request.setCustomerRefId(projectCode);
        request.setHiddenOnUI(false);
        request.setAutoFuel(true);
        request.setCoinKeyList(DEPOSIT_COINS);
        request.setAccountTag("DEPOSIT");

        CreateAccountResponse response;
        try {
            response = ServiceExecutor.execute(accountApi(team).createAccount(request));
        } catch (RuntimeException exception) {
            log.error(
                    "Safeheron钱包创建失败: projectCode={}, exceptionType={}",
                    projectCode,
                    exception.getClass().getName(),
                    exception);
            throw new SafeheronWalletException("Safeheron钱包创建失败，请稍后重试", exception);
        }
        if (response == null
                || response.getAccountKey() == null
                || response.getAccountKey().isBlank()) {
            throw new SafeheronWalletException("Safeheron钱包创建结果缺少accountKey");
        }

        Wallet wallet = new Wallet();
        wallet.setAccountKey(response.getAccountKey());
        wallet.setAccountName(projectName);
        wallet.setCustomerRefId(projectCode);
        wallet.setTeamId(DEFAULT_TEAM_ID);
        try {
            mapper.insertWallet(wallet);
        } catch (DuplicateKeyException exception) {
            Wallet concurrent = mapper.findWalletByCustomerRefId(projectCode);
            if (concurrent == null) {
                throw exception;
            }
            return projectWallet(concurrent);
        }
        saveCoins(response, wallet.getAccountKey());
        return projectWallet(wallet);
    }

    /**
     * 幂等导入外部系统已创建的钱包；地址使用新系统密钥重新加密，禁止复制外部密文。
     *
     * @param snapshot 外部钱包及需要展示的币种地址
     * @return 新系统钱包展示模型
     */
    public ProjectWallet importProjectWallet(ImportedWallet snapshot) {
        if (snapshot == null
                || blank(snapshot.accountKey())
                || blank(snapshot.accountName())
                || blank(snapshot.customerRefId())) {
            throw new SafeheronWalletException("旧系统返回的钱包数据不完整");
        }
        Set<String> addressCoins =
                snapshot.coins().stream()
                        .filter(coin -> coin != null && !blank(coin.address()))
                        .map(ImportedCoin::coinKey)
                        .collect(Collectors.toSet());
        if (!addressCoins.containsAll(REQUIRED_DEPOSIT_COINS)) {
            throw new SafeheronWalletException("旧系统返回的ETH或USDT_TRC20地址缺失");
        }
        Wallet wallet = mapper.findWalletByCustomerRefId(snapshot.customerRefId());
        if (wallet != null && !snapshot.accountKey().equals(wallet.getAccountKey())) {
            throw new SafeheronWalletException("钱包业务引用已关联其他accountKey");
        }
        Wallet accountWallet = mapper.findWallet(snapshot.accountKey());
        if (accountWallet != null
                && !snapshot.customerRefId().equals(accountWallet.getCustomerRefId())) {
            throw new SafeheronWalletException("accountKey已关联其他钱包业务引用");
        }
        if (wallet == null) {
            wallet = new Wallet();
            wallet.setAccountKey(snapshot.accountKey());
            wallet.setAccountName(snapshot.accountName());
            wallet.setCustomerRefId(snapshot.customerRefId());
            wallet.setTeamId(blank(snapshot.teamId()) ? DEFAULT_TEAM_ID : snapshot.teamId());
            try {
                mapper.insertWallet(wallet);
            } catch (DuplicateKeyException exception) {
                wallet = mapper.findWalletByCustomerRefId(snapshot.customerRefId());
                if (wallet == null || !snapshot.accountKey().equals(wallet.getAccountKey())) {
                    throw exception;
                }
            }
        }
        for (ImportedCoin importedCoin : snapshot.coins()) {
            if (importedCoin == null || blank(importedCoin.coinKey())) continue;
            Coin coin = new Coin();
            coin.setAccountKey(wallet.getAccountKey());
            coin.setCoinKey(importedCoin.coinKey());
            coin.setCoinName(
                    blank(importedCoin.coinName())
                            ? importedCoin.coinKey()
                            : importedCoin.coinName());
            coin.setFeeUnit(importedCoin.feeUnit());
            if (!blank(importedCoin.address())) {
                coin.setAddressCiphertext(cipher.encrypt(importedCoin.address()));
            }
            mapper.upsertWalletCoin(coin, wallet.getAccountKey());
        }
        return projectWallet(wallet);
    }

    /** 查询项目钱包；未创建时返回null。 */
    public ProjectWallet findProjectWallet(String projectCode) {
        Wallet wallet = mapper.findWalletByCustomerRefId(projectCode);
        return wallet == null ? null : projectWallet(wallet);
    }

    /** 批量读取当前页项目的钱包和地址，不调用外部 Safeheron API。 */
    public Map<String, ProjectWallet> findProjectWallets(List<String> projectCodes) {
        List<String> codes = projectCodes.stream().filter(code -> !blank(code)).distinct().toList();
        if (codes.isEmpty()) return Map.of();
        List<Wallet> wallets = mapper.findWalletsByCustomerRefIds(codes);
        if (wallets.isEmpty()) return Map.of();
        List<String> keys = wallets.stream().map(Wallet::getAccountKey).distinct().toList();
        Map<String, List<Coin>> coins =
                mapper.findWalletCoinsByAccountKeys(keys).stream()
                        .collect(Collectors.groupingBy(Coin::getAccountKey));
        Map<String, ProjectWallet> result = new LinkedHashMap<>();
        for (Wallet wallet : wallets) {
            ProjectWallet previous =
                    result.put(
                            wallet.getCustomerRefId(),
                            projectWallet(
                                    wallet, coins.getOrDefault(wallet.getAccountKey(), List.of())));
            if (previous != null) throw new SafeheronWalletException("项目存在多个有效钱包，请检查钱包关联");
        }
        return result;
    }

    private AccountApiService accountApi(Team team) {
        if (blank(team.getApiKey())
                || blank(team.getPrivateKeyCiphertext())
                || blank(team.getSafeheronPublicKey())) {
            throw new SafeheronWalletException("Safeheron默认团队凭证不完整");
        }
        SafeheronConfig config =
                SafeheronConfig.builder()
                        .baseUrl(
                                blank(team.getBaseUrl())
                                        ? "https://api.safeheron.vip"
                                        : team.getBaseUrl())
                        .apiKey(team.getApiKey())
                        .rsaPrivateKey(cipher.decrypt(team.getPrivateKeyCiphertext()))
                        .safeheronRsaPublicKey(team.getSafeheronPublicKey())
                        .requestTimeout(
                                team.getRequestTimeout() == null
                                        ? 20_000L
                                        : team.getRequestTimeout())
                        .build();
        return ServiceCreator.create(AccountApiService.class, config);
    }

    private void saveCoins(CreateAccountResponse response, String accountKey) {
        if (response.getCoinAddressList() == null) return;
        for (CreateAccountResponse.CoinAddress item : response.getCoinAddressList()) {
            Coin coin = new Coin();
            coin.setAccountKey(accountKey);
            coin.setCoinKey(item.getCoinKey());
            coin.setCoinName(item.getCoinKey());
            coin.setFeeUnit("USDT_TRC20".equals(item.getCoinKey()) ? "TRX" : "ETH");
            if (item.getAddressList() != null && !item.getAddressList().isEmpty()) {
                String address = item.getAddressList().getFirst().getAddress();
                if (!blank(address)) coin.setAddressCiphertext(cipher.encrypt(address));
            }
            mapper.insertWalletCoin(coin, accountKey);
        }
    }

    private ProjectWallet projectWallet(Wallet wallet) {
        return projectWallet(wallet, mapper.findWalletCoins(wallet.getAccountKey()));
    }

    private ProjectWallet projectWallet(Wallet wallet, List<Coin> coins) {
        Coin eth = findCoin(coins, "ETH");
        Coin usdt = findCoin(coins, "USDT_TRC20");
        return new ProjectWallet(
                wallet.getId() == null ? null : wallet.getId().toString(),
                wallet.getAccountKey(),
                address(eth),
                address(usdt),
                usdt != null && !blank(usdt.getFeeUnit()) ? usdt.getFeeUnit() : "TRX",
                wallet.getAccountName());
    }

    private Coin findCoin(List<Coin> coins, String coinKey) {
        return coins.stream()
                .filter(item -> coinKey.equals(item.getCoinKey()))
                .findFirst()
                .orElse(null);
    }

    private String address(Coin coin) {
        return coin == null || blank(coin.getAddressCiphertext())
                ? ""
                : cipher.decrypt(coin.getAddressCiphertext());
    }

    private boolean blank(String value) {
        return value == null || value.isBlank();
    }

    /** 外部系统钱包快照，只保留新系统展示钱包所需字段。 */
    public record ImportedWallet(
            String accountKey,
            String accountName,
            String customerRefId,
            String teamId,
            List<ImportedCoin> coins) {
        public ImportedWallet {
            coins = coins == null ? List.of() : List.copyOf(coins);
        }
    }

    /** 外部钱包币种快照；只同步首个收款地址。 */
    public record ImportedCoin(String coinKey, String coinName, String feeUnit, String address) {}

    /** 可直接展示的钱包创建异常，不包含凭证或完整外部响应。 */
    public static class SafeheronWalletException extends RuntimeException {
        public SafeheronWalletException(String message) {
            super(message);
        }

        public SafeheronWalletException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}

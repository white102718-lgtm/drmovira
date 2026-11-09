package com.adpulse.main.cardstation.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.cardstation.dto.CardStationRequests.AutoAdjustSave;
import com.adpulse.main.cardstation.mapper.CardStationMapper;
import com.adpulse.main.cardstation.model.CardStationModels.LimitRule;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** 卡台限额规则未配置状态与开关保护测试。 */
@ExtendWith(MockitoExtension.class)
class CardStationServiceTest {
    @Mock private CardStationMapper mapper;

    private CardStationService service;

    @BeforeEach
    void setUp() {
        service = new CardStationService(mapper);
    }

    @Test
    void shouldReturnExplicitUnconfiguredRule() {
        when(mapper.findLimitRule()).thenReturn(null);

        var result = service.limitRule();

        assertThat(result.configured()).isFalse();
        assertThat(result.autoAdjustEnabled()).isFalse();
        assertThat(result.dailyPeriod()).isNull();
    }

    @Test
    void shouldExposeConfiguredRuleWithoutPersistenceModel() {
        LimitRule item = new LimitRule();
        item.setId(7L);
        item.setDailyPeriod(15);
        item.setAdjustAmount(new BigDecimal("100.50"));
        item.setMinAmount(new BigDecimal("20"));
        item.setAutoAdjustEnabled(true);
        item.setUpdatedAt(LocalDateTime.of(2026, 8, 20, 12, 0));
        when(mapper.findLimitRule()).thenReturn(item);

        var result = service.limitRule();

        assertThat(result.configured()).isTrue();
        assertThat(result.dailyPeriod()).isEqualTo(15);
        assertThat(result.adjustAmount()).isEqualByComparingTo("100.50");
        assertThat(result.minAmount()).isEqualByComparingTo("20");
        assertThat(result.autoAdjustEnabled()).isTrue();
    }

    @Test
    void shouldRejectAutoAdjustBeforeRuleIsConfigured() {
        when(mapper.findLimitRule()).thenReturn(null);

        assertThatThrownBy(() -> service.updateLimitRuleAutoAdjust(new AutoAdjustSave(true)))
                .isInstanceOf(CardStationService.CardStationException.class)
                .hasMessageContaining("先保存限额规则");
        verify(mapper, never())
                .updateLimitRuleAutoAdjust(
                        org.mockito.ArgumentMatchers.anyLong(),
                        org.mockito.ArgumentMatchers.anyBoolean(),
                        org.mockito.ArgumentMatchers.anyLong());
    }
}

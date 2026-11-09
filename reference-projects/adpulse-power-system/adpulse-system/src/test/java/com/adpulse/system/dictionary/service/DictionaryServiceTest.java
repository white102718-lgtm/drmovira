package com.adpulse.system.dictionary.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.dictionary.dto.DictionaryItemSaveRequest;
import com.adpulse.system.dictionary.mapper.DictionaryMapper;
import com.adpulse.system.dictionary.model.DictionaryItem;
import com.adpulse.system.dictionary.model.DictionaryType;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** 字典服务业务规则测试。 */
@ExtendWith(MockitoExtension.class)
class DictionaryServiceTest {

    @Mock private DictionaryMapper mapper;

    private DictionaryService service;

    @BeforeEach
    void setUp() {
        service = new DictionaryService(mapper);
    }

    @Test
    void shouldReturnOnlyMapperResolvedEnabledOptions() {
        DictionaryType type = new DictionaryType();
        type.setId(8L);
        DictionaryItem facebook = item("FACEBOOK", "Facebook");
        DictionaryItem google = item("GOOGLE", "Google");
        when(mapper.findEnabledTypeByCode("AD_MEDIA")).thenReturn(type);
        when(mapper.findEnabledItems(8L)).thenReturn(List.of(facebook, google));

        assertThat(service.options("ad_media"))
                .extracting("value", "label")
                .containsExactly(
                        org.assertj.core.groups.Tuple.tuple("FACEBOOK", "Facebook"),
                        org.assertj.core.groups.Tuple.tuple("GOOGLE", "Google"));
        verify(mapper).findEnabledTypeByCode("AD_MEDIA");
    }

    @Test
    void shouldRejectItemCreationWhenDictionaryTypeDoesNotExist() {
        when(mapper.findTypeById(99L)).thenReturn(null);

        assertThatThrownBy(
                        () ->
                                service.createItem(
                                        99L,
                                        new DictionaryItemSaveRequest("VALUE", "标签", 0, 1, null)))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("字典类型");
    }

    private DictionaryItem item(String value, String label) {
        DictionaryItem item = new DictionaryItem();
        item.setItemValue(value);
        item.setItemLabel(label);
        return item;
    }
}

package com.adpulse.system.dictionary.dto;

import java.util.List;

/** 字典类型及其字典项详情。 */
public record DictionaryDetail(DictionaryTypeView type, List<DictionaryItemView> items) {}

import type { TableColumnsType } from 'ant-design-vue';

import type { MaterialItem } from '../types';

import { ref, watch } from 'vue';

import dayjs from 'dayjs';

import { getDashboardDetail } from '#/api/dashboard';
import { getBatchMaterialImgApi, getMaterialImgApi } from '#/api/materials/all';

export function useMaterial() {
  const materialDateRange = ref<[number, number]>([
    dayjs(dayjs.tz().subtract(30, 'days').format('YYYY-MM-DD')).valueOf(),
    dayjs(dayjs.tz().format('YYYY-MM-DD')).endOf('day').valueOf(),
  ]);
  const selectedMaterialCategory = ref('all');
  const expandedCategories = ref<string[]>(['enterprise', 'personal']);
  const selectedLibraryMaterials = ref<string[]>([]);
  const currentPage = ref(1);
  const pageSize = ref(20);

  // 动态表格状态
  const materialData = ref<MaterialItem[]>([]);
  const materialColumns = ref<TableColumnsType>([]);
  const loading = ref(false);
  const totalCount = ref(0);

  // 图片加载状态
  const loadingImg = ref(false);

  // 格式化日期范围
  function formatDateRange(range: [number, number]) {
    const startDate = dayjs(range[0]).format('YYYY-MM-DD');
    const endDate = dayjs(range[1]).format('YYYY-MM-DD');
    return `${startDate},${endDate}`;
  }

  // 动态列构建
  function buildDynamicColumns(columns: string[]): TableColumnsType {
    return columns.map((col) => {
      switch (col) {
        case 'CPI':
        case 'cpi': {
          return {
            title: 'CPI',
            dataIndex: col,
            width: 105,
          };
        }
        case 'ctr':
        case '点击率': {
          return {
            title: '点击率',
            dataIndex: col,
            width: 105,
          };
        }
        case 'installs':
        case '安装量': {
          return {
            title: '安装量',
            dataIndex: col,
            width: 105,
          };
        }
        case 'isUsedToday':
        case '今日是否使用': {
          return {
            title: '今日是否使用',
            dataIndex: col,
            width: 120,
            align: 'center',
          };
        }
        case 'name': {
          return {
            title: '素材名称',
            dataIndex: col,
            width: 250,
            fixed: 'left',
          };
        }
        case 'purchaseCount':
        case '购物次数': {
          return {
            title: '购物次数',
            dataIndex: col,
            width: 105,
          };
        }
        case 'purchaseValue':
        case '购物转化价值': {
          return {
            title: '购物转化价值',
            dataIndex: col,
            width: 130,
          };
        }
        case 'registrations':
        case '注册量': {
          return {
            title: '注册量',
            dataIndex: col,
            width: 105,
          };
        }
        case 'ROAS':
        case 'roas': {
          return {
            title: 'ROAS',
            dataIndex: col,
            width: 105,
          };
        }
        case 'spend':
        case '花费':
        case '花费金额': {
          return {
            title: col === '花费金额' ? '花费金额' : '花费',
            dataIndex: col,
            width: 140,
          };
        }
        case 'thumbnail': {
          return {
            title: '预览',
            dataIndex: col,
            width: 120,
            align: 'center',
          };
        }
        case 'unique_name': {
          return {
            title: 'unique_name',
            dataIndex: col,
            width: 105,
          };
        }
        case 'uploadTime':
        case '上传时间': {
          return {
            title: '上传时间',
            dataIndex: col,
            width: 105,
          };
        }
        case 'usageCount':
        case '使用次数': {
          return {
            title: '使用次数',
            dataIndex: col,
            width: 105,
          };
        }
        case '创建时间': {
          return {
            title: '创建时间',
            dataIndex: col,
            width: 105,
          };
        }
        case '状态': {
          return {
            title: '状态',
            dataIndex: col,
            width: 105,
          };
        }
        default: {
          return {
            title: col,
            dataIndex: col,
            width: 105,
          };
        }
      }
    });
  }

  // 核心数据获取
  async function fetchMaterials() {
    loading.value = true;
    try {
      const params: Record<string, string> = {
        category: selectedMaterialCategory.value,
        date: formatDateRange(materialDateRange.value),
        page: currentPage.value.toString(),
        page_size: pageSize.value.toString(),
      };

      const response = await getDashboardDetail('ad_id', params);

      const rows: MaterialItem[] = (response.data || []).map(
        (item: MaterialItem) => ({
          ...item,
          key: item.id,
        }),
      );

      materialData.value = rows;

      // 如果接口返回了 columns，使用接口返回的；否则使用默认列
      if (response.columns && response.columns.length > 0) {
        materialColumns.value = buildDynamicColumns(response.columns);
      } else {
        // 默认列配置，确保即使没有数据也能显示表头
        materialColumns.value = buildDynamicColumns(['name']);
      }

      totalCount.value =
        (response.pagination && (response.pagination as any).total) ||
        rows.length ||
        0;
    } catch {
      materialData.value = [];
      // 错误时也显示默认列
      materialColumns.value = buildDynamicColumns(['name']);
      totalCount.value = 0;
    } finally {
      loading.value = false;
    }
  }

  // 批量加载缩略图
  async function loadMaterialThumbnails() {
    if (loadingImg.value) return;

    loadingImg.value = true;
    try {
      const itemsToLoad = materialData.value.filter(
        (item) => item.unique_name && !item.img,
      );
      const basenames = itemsToLoad.map((item) => item.unique_name);

      if (basenames.length === 0) return;

      const response = await getBatchMaterialImgApi(basenames);
      const batchData = response.images || {};

      materialData.value.forEach((item) => {
        if (item.unique_name && batchData[item.unique_name]) {
          const imgData = batchData[item.unique_name];
          item.img = imgData.img;
          item.filename = imgData.filename;
          item.filetype = imgData.filetype;
        }
      });
    } catch (error) {
    } finally {
      loadingImg.value = false;
    }
  }

  // 单个图片加载
  async function loadSingleImage(record: MaterialItem) {
    if (!record.unique_name || record.img || loadingImg.value) return;

    try {
      loadingImg.value = true;
      const response = await getMaterialImgApi(record.unique_name);
      record.img = response.img;
      record.filename = response.filename;
      record.filetype = response.filetype;
    } catch (error) {
    } finally {
      loadingImg.value = false;
    }
  }

  // 现有方法（保持兼容）
  function toggleCategory(key: string) {
    const index = expandedCategories.value.indexOf(key);
    if (index === -1) {
      expandedCategories.value.push(key);
    } else {
      expandedCategories.value.splice(index, 1);
    }
  }

  function selectCategory(key: string) {
    selectedMaterialCategory.value = key;
  }

  function isCategoryExpanded(key: string) {
    return expandedCategories.value.includes(key);
  }

  function isCategorySelected(key: string) {
    return selectedMaterialCategory.value === key;
  }

  function resetSelection() {
    selectedLibraryMaterials.value = [];
    selectedMaterialCategory.value = 'all';
    expandedCategories.value = ['enterprise', 'personal'];
    currentPage.value = 1;
    pageSize.value = 20;
  }

  // 监听分类变化，自动刷新数据
  watch(selectedMaterialCategory, () => {
    currentPage.value = 1;
    fetchMaterials();
  });

  return {
    // 现有导出（保持兼容）
    materialDateRange,
    selectedMaterialCategory,
    expandedCategories,
    selectedLibraryMaterials,
    currentPage,
    pageSize,

    // 新增导出
    materialData,
    materialColumns,
    loading,
    loadingImg,
    totalCount,

    // 方法
    toggleCategory,
    selectCategory,
    isCategoryExpanded,
    isCategorySelected,
    resetSelection,
    fetchMaterials,
    loadSingleImage,
    loadMaterialThumbnails,
  };
}

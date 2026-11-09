import type { Recordable } from '@vben/types';

import { h, nextTick, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';
import { $te } from '@vben/locales';
import {
  setupVbenVxeTable,
  useVbenVxeGrid as useBaseVbenVxeGrid,
} from '@vben/plugins/vxe-table';
import { get, getPopupContainer, isFunction, isString } from '@vben/utils';

import { objectOmit } from '@vueuse/core';
import {
  Button,
  Dropdown,
  Image,
  Menu,
  Popconfirm,
  Switch,
  Tag,
} from 'ant-design-vue';

import { $t } from '#/locales';
import {
  normalizeLocationQuery,
  parseListRouteState,
  serializeListRouteState,
} from '#/composables/list-route-state';

import { useVbenForm } from './form';

setupVbenVxeTable({
  configVxeTable: (vxeUI) => {
    vxeUI.setConfig({
      grid: {
        // 文本列默认左对齐，数字与操作列由各业务列按语义单独覆盖。
        align: 'left',
        border: false,
        columnConfig: {
          resizable: true,
        },
        cellConfig: {
          height: 44,
        },

        formConfig: {
          // 全局禁用vxe-table的表单配置，使用formOptions
          enabled: false,
        },
        // 页面主表格继承可用高度，数据较多时由表格内部滚动。
        height: '100%',
        minHeight: 180,
        headerCellConfig: {
          height: 40,
        },
        proxyConfig: {
          autoLoad: true,
          response: {
            result: 'items',
            total: 'total',
            list: '',
          },
          showActiveMsg: true,
          showResponseMsg: false,
        },
        round: true,
        scrollY: {
          scrollToTopOnChange: true,
        },
        size: 'small',
      },
    });

    /**
     * 解决vxeTable在热更新时可能会出错的问题
     */
    vxeUI.renderer.forEach((_item, key) => {
      if (key.startsWith('Cell')) {
        vxeUI.renderer.delete(key);
      }
    });

    // 表格配置项可以用 cellRender: { name: 'CellImage' },
    vxeUI.renderer.add('CellImage', {
      renderTableDefault(_renderOpts, params) {
        const { column, row } = params;
        return h(Image, { src: row[column.field] });
      },
    });

    // 表格配置项可以用 cellRender: { name: 'CellLink' },
    vxeUI.renderer.add('CellLink', {
      renderTableDefault(renderOpts) {
        const { props } = renderOpts;
        return h(
          Button,
          { size: 'small', type: 'link' },
          { default: () => props?.text },
        );
      },
    });

    // 单元格渲染： Tag
    vxeUI.renderer.add('CellTag', {
      renderTableDefault({ options, props }, { column, row }) {
        const value = get(row, column.field);
        const tagOptions = options ?? [
          { color: 'success', label: $t('common.enabled'), value: 1 },
          { color: 'error', label: $t('common.disabled'), value: 0 },
        ];
        const tagItem = tagOptions.find((item) => item.value === value);
        return h(
          Tag,
          {
            ...props,
            ...objectOmit(tagItem ?? {}, ['label']),
          },
          { default: () => tagItem?.label ?? value },
        );
      },
    });

    vxeUI.renderer.add('CellSwitch', {
      renderTableDefault({ attrs, props }, { column, row }) {
        const loadingKey = `__loading_${column.field}`;
        const finallyProps = {
          checkedChildren: $t('common.enabled'),
          checkedValue: 1,
          unCheckedChildren: $t('common.disabled'),
          unCheckedValue: 0,
          ...props,
          checked: row[column.field],
          loading: row[loadingKey] ?? false,
          'onUpdate:checked': onChange,
        };
        async function onChange(newVal: any) {
          row[loadingKey] = true;
          try {
            const result = await attrs?.beforeChange?.(newVal, row);
            if (result !== false) {
              row[column.field] = newVal;
            }
          } finally {
            row[loadingKey] = false;
          }
        }
        return h(Switch, finallyProps);
      },
    });

    /**
     * 注册表格的操作按钮渲染器
     */
    vxeUI.renderer.add('CellOperation', {
      renderTableDefault({ attrs, options, props }, { column, row }) {
        const defaultProps = { size: 'small', type: 'link', ...props };
        let align = 'end';
        switch (column.align) {
          case 'center': {
            align = 'center';
            break;
          }
          case 'left': {
            align = 'start';
            break;
          }
          default: {
            align = 'end';
            break;
          }
        }
        const presets: Recordable<Recordable<any>> = {
          delete: {
            danger: true,
            text: $t('common.delete'),
          },
          edit: {
            text: $t('common.edit'),
          },
        };
        const operations: Array<Recordable<any>> = (
          options || ['edit', 'delete']
        )
          .map((opt) => {
            if (isString(opt)) {
              return presets[opt]
                ? { code: opt, ...presets[opt], ...defaultProps }
                : {
                    code: opt,
                    text: $te(`common.${opt}`) ? $t(`common.${opt}`) : opt,
                    ...defaultProps,
                  };
            } else {
              return { ...defaultProps, ...presets[opt.code], ...opt };
            }
          })
          .map((opt) => {
            const optBtn: Recordable<any> = {};
            Object.keys(opt).forEach((key) => {
              optBtn[key] = isFunction(opt[key]) ? opt[key](row) : opt[key];
            });
            return optBtn;
          })
          .filter((opt) => opt.show !== false);

        function renderBtn(opt: Recordable<any>, listen = true) {
          return h(
            Button,
            {
              ...props,
              ...opt,
              icon: undefined,
              onClick: listen
                ? () =>
                    attrs?.onClick?.({
                      code: opt.code,
                      row,
                    })
                : undefined,
            },
            {
              default: () => {
                const content = [];
                if (opt.icon) {
                  content.push(
                    h(IconifyIcon, {
                      'aria-hidden': true,
                      class: 'size-5',
                      icon: opt.icon,
                    }),
                  );
                }
                content.push(opt.text);
                return content;
              },
            },
          );
        }

        function renderConfirm(opt: Recordable<any>) {
          const isDelete = opt.code === 'delete';
          const popTitle =
            opt.confirmTitle ??
            (isDelete
              ? $t('ui.actionTitle.delete', [attrs?.nameTitle || ''])
              : opt.text);
          let popDesc = '';
          if (opt.confirmDescription) {
            popDesc = isFunction(opt.confirmDescription)
              ? opt.confirmDescription(row)
              : opt.confirmDescription;
          } else if (isDelete) {
            popDesc = $t('ui.actionMessage.deleteConfirm', [
              row[attrs?.nameField || 'name'],
            ]);
          }
          let viewportWrapper: HTMLElement | null = null;
          return h(
            Popconfirm,
            {
              getPopupContainer(el) {
                viewportWrapper = el.closest('.vxe-table--viewport-wrapper');
                return getPopupContainer(el);
              },
              placement: 'topLeft',
              title: popTitle,
              ...props,
              ...opt,
              confirm: undefined,
              confirmTitle: undefined,
              confirmDescription: undefined,
              icon: undefined,
              onOpenChange: (open: boolean) => {
                if (open) {
                  viewportWrapper?.style.setProperty('pointer-events', 'none');
                } else {
                  viewportWrapper?.style.removeProperty('pointer-events');
                }
              },
              onConfirm: () => {
                attrs?.onClick?.({
                  code: opt.code,
                  row,
                });
              },
            },
            {
              default: () => renderBtn({ ...opt }, false),
              description: () => h('div', { class: 'truncate' }, popDesc),
            },
          );
        }

        const renderOperation = (opt: Recordable<any>) =>
          opt.code === 'delete' || opt.confirm
            ? renderConfirm(opt)
            : renderBtn(opt);

        const maxVisible = attrs?.maxVisible ?? 2;
        let btns = operations.map((operation) => renderOperation(operation));
        if (operations.length > maxVisible) {
          const visibleOperations = operations.slice(0, 1);
          const moreOperations = operations.slice(1);
          const moreDropdown = h(
            Dropdown,
            {
              trigger: ['click'],
            },
            {
              default: () =>
                h(Button, { ...defaultProps }, { default: () => '更多' }),
              overlay: () =>
                h(
                  Menu,
                  {
                    onClick: ({ key }: { key: string }) => {
                      attrs?.onClick?.({ code: key, row });
                    },
                  },
                  {
                    default: () =>
                      moreOperations.map((opt) =>
                        h(
                          Menu.Item,
                          { danger: opt.danger, key: opt.code },
                          { default: () => opt.text },
                        ),
                      ),
                  },
                ),
            },
          );
          btns = [
            ...visibleOperations.map((operation) => renderOperation(operation)),
            moreDropdown,
          ];
        }
        return h(
          'div',
          {
            class: 'flex gap-1 table-operations',
            style: { justifyContent: align },
          },
          btns,
        );
      },
    });

    // 这里可以自行扩展 vxe-table 的全局配置，比如自定义格式化
    // vxeUI.formats.add
  },
  useVbenForm,
});

export interface VxeGridRouteStateOptions {
  /** 同一路由存在多个主列表时用于隔离查询参数。 */
  scope?: string;
}

type BaseVbenVxeGridProps = Parameters<typeof useBaseVbenVxeGrid>[0];

export type PlatVxeGridProps = BaseVbenVxeGridProps & {
  /** 设置为 false 可排除弹窗、抽屉和选择器中的临时列表。 */
  routeState?: false | VxeGridRouteStateOptions;
};

function getRouteFormDefaults(schema: Array<Record<string, any>>) {
  return Object.fromEntries(
    schema
      .filter((item) => typeof item.fieldName === 'string')
      .map((item) => {
        const isMultiple = item.componentProps?.mode === 'multiple';
        const isRange = item.component === 'RangePicker';
        return [
          item.fieldName,
          item.defaultValue ?? (isMultiple || isRange ? [] : ''),
        ];
      }),
  );
}

/**
 * 创建默认支持 URL 状态恢复的业务 VXE 列表。
 *
 * @remarks
 * 只对同时声明查询表单和代理查询的主列表自动启用；临时列表必须显式传入 routeState: false。
 */
export function useVbenVxeGrid(options: PlatVxeGridProps) {
  const route = useRoute();
  const routePath = route.path;
  const schema = options.formOptions?.schema;
  const originalQuery = options.gridOptions?.proxyConfig?.ajax?.query;
  if (
    route.meta.hideInMenu === true ||
    options.routeState === false ||
    !Array.isArray(schema) ||
    typeof originalQuery !== 'function'
  ) {
    return useBaseVbenVxeGrid(options);
  }

  const router = useRouter();
  const routeStateOptions = options.routeState ?? {};
  const defaults = getRouteFormDefaults(schema as Array<Record<string, any>>);
  const pagerConfig = options.gridOptions?.pagerConfig;
  const defaultPageSize = Number(pagerConfig?.pageSize) || 20;
  const pageSizes = Array.isArray(pagerConfig?.pageSizes)
    ? pagerConfig.pageSizes.filter(
        (pageSize): pageSize is number => typeof pageSize === 'number',
      )
    : undefined;
  const pagination = { defaultPageSize, pageSizes };
  const restored = parseListRouteState({
    defaults,
    pagination,
    query: route.query,
    scope: routeStateOptions.scope,
  });
  let isRestoringRoute = false;
  let lastWrittenQuery = '';

  const enhancedOptions: PlatVxeGridProps = {
    ...options,
    formOptions: {
      ...options.formOptions,
      schema: (schema as Array<Record<string, any>>).map((item) => ({
        ...item,
        defaultValue:
          typeof item.fieldName === 'string'
            ? restored.state[item.fieldName]
            : item.defaultValue,
      })) as any,
    },
    gridOptions: {
      ...options.gridOptions,
      pagerConfig: {
        ...pagerConfig,
        currentPage: restored.pagination?.page ?? 1,
        pageSize: restored.pagination?.pageSize ?? defaultPageSize,
      },
      proxyConfig: {
        ...options.gridOptions?.proxyConfig,
        ajax: {
          ...options.gridOptions?.proxyConfig?.ajax,
          query: async (
            params: any,
            formValues: Record<string, unknown> | undefined,
          ) => {
            if (!isRestoringRoute && route.path === routePath) {
              const nextQuery = serializeListRouteState({
                currentQuery: route.query,
                defaults,
                pagination,
                paginationState: {
                  page: params.page.currentPage || 1,
                  pageSize: params.page.pageSize || defaultPageSize,
                },
                scope: routeStateOptions.scope,
                state: formValues ?? {},
              });
              lastWrittenQuery = normalizeLocationQuery(nextQuery);
              if (lastWrittenQuery !== normalizeLocationQuery(route.query)) {
                await router.replace({ path: route.path, query: nextQuery });
              }
            }
            return originalQuery(params, formValues);
          },
        },
      },
    },
  };
  delete enhancedOptions.routeState;

  const grid = useBaseVbenVxeGrid(enhancedOptions);
  const [, gridApi] = grid;

  watch(
    () => [route.path, normalizeLocationQuery(route.query)] as const,
    async ([currentPath, querySignature]) => {
      if (currentPath !== routePath) return;
      if (querySignature === lastWrittenQuery) {
        lastWrittenQuery = '';
        return;
      }
      const nextState = parseListRouteState({
        defaults,
        pagination,
        query: route.query,
        scope: routeStateOptions.scope,
      });
      isRestoringRoute = true;
      try {
        await nextTick();
        await gridApi.formApi.setValues(nextState.state);
        gridApi.setGridOptions({
          pagerConfig: {
            ...pagerConfig,
            currentPage: nextState.pagination?.page ?? 1,
            pageSize: nextState.pagination?.pageSize ?? defaultPageSize,
          },
        });
        await gridApi.reload(nextState.state);
      } finally {
        isRestoringRoute = false;
      }
    },
    { flush: 'post' },
  );

  return grid;
}

export type OnActionClickParams<T = Recordable<any>> = {
  code: string;
  row: T;
};
export type OnActionClickFn<T = Recordable<any>> = (
  params: OnActionClickParams<T>,
) => void;
export type * from '@vben/plugins/vxe-table';

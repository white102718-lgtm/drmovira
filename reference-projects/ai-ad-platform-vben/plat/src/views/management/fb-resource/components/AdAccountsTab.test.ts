import { mount } from '@vue/test-utils';
import { defineComponent, h } from 'vue';

import { beforeEach, describe, expect, it, vi } from 'vitest';

import AdAccountsTab from './AdAccountsTab.vue';

const useVbenVxeGrid = vi.hoisted(() => vi.fn());

vi.mock('#/adapter/vxe-table', () => ({
  useVbenVxeGrid,
}));

vi.mock('#/api', () => ({
  getAdAccounts: vi.fn(),
}));

const Grid = defineComponent({
  setup(_, { slots }) {
    return () => h('div', slots.default?.());
  },
});

describe('adAccountsTab', () => {
  beforeEach(() => {
    useVbenVxeGrid.mockReturnValue([Grid, { reload: vi.fn() }]);
  });

  it('uses a multiline field so pasted line breaks reach the ID parser', () => {
    mount(AdAccountsTab, {
      global: {
        stubs: { Page: { template: '<div><slot /></div>' } },
      },
    });

    const gridFactoryCall = useVbenVxeGrid.mock.calls[0];
    if (!gridFactoryCall) throw new Error('Expected grid factory to be called');

    const [{ formOptions }] = gridFactoryCall;
    expect(formOptions.schema[0].component).toBe('Textarea');
  });
});

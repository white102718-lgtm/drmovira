import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { downloadBlob, safeDownloadName } from './download.ts';

function installDownloadEnvironment(picker) {
  const descriptors = new Map(
    ['document', 'File', 'URL', 'window'].map((key) => [
      key,
      Object.getOwnPropertyDescriptor(globalThis, key),
    ]),
  );
  const state = {
    appended: 0,
    clicked: 0,
    createdUrls: 0,
    downloadLink: undefined,
    pickerCalls: 0,
    removed: 0,
    revokedUrls: [],
    scheduledCallbacks: [],
  };
  const link = {
    click() {
      state.clicked += 1;
    },
    download: '',
    href: '',
    rel: '',
    remove() {
      state.removed += 1;
    },
    style: { display: '' },
  };
  state.downloadLink = link;

  Object.defineProperties(globalThis, {
    document: {
      configurable: true,
      value: {
        body: {
          append() {
            state.appended += 1;
          },
        },
        createElement() {
          return link;
        },
      },
    },
    File: {
      configurable: true,
      value: class File {
        constructor(parts, name, options) {
          this.name = name;
          this.options = options;
          this.parts = parts;
        }
      },
    },
    URL: {
      configurable: true,
      value: {
        createObjectURL() {
          state.createdUrls += 1;
          return 'blob:approval-export';
        },
        revokeObjectURL(url) {
          state.revokedUrls.push(url);
        },
      },
    },
    window: {
      configurable: true,
      value: {
        setTimeout(callback) {
          state.scheduledCallbacks.push(callback);
          return state.scheduledCallbacks.length;
        },
        async showSaveFilePicker(options) {
          state.pickerCalls += 1;
          return picker(options);
        },
      },
    },
  });

  return {
    restore() {
      for (const [key, descriptor] of descriptors) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor);
        else delete globalThis[key];
      }
    },
    state,
  };
}

describe('safeDownloadName', () => {
  it('preserves an existing file extension before using the fallback', () => {
    assert.equal(safeDownloadName('审批中心.xlsx'), '审批中心.xlsx');
    assert.equal(safeDownloadName('审批中心'), '审批中心.bin');
  });
});

describe('downloadBlob', () => {
  it('uses the browser download path and preserves the xlsx extension', async () => {
    const environment = installDownloadEnvironment(async () => {
      throw new Error('save picker should not be called');
    });
    try {
      const result = await downloadBlob(
        new Blob(['xlsx'], { type: 'application/xlsx' }),
        '审批中心.xlsx',
        { mode: 'browser' },
      );

      assert.equal(result, 'started');
      assert.equal(environment.state.pickerCalls, 0);
      assert.equal(environment.state.createdUrls, 1);
      assert.equal(environment.state.appended, 1);
      assert.equal(environment.state.clicked, 1);
      assert.equal(environment.state.downloadLink.download, '审批中心.xlsx');

      environment.state.scheduledCallbacks.forEach((callback) => callback());
      assert.equal(environment.state.removed, 1);
      assert.deepEqual(environment.state.revokedUrls, ['blob:approval-export']);
    } finally {
      environment.restore();
    }
  });

  it('keeps the save picker as the default mode', async () => {
    let closed = false;
    let written;
    const environment = installDownloadEnvironment(async () => ({
      async createWritable() {
        return {
          async close() {
            closed = true;
          },
          async write(value) {
            written = value;
          },
        };
      },
    }));
    try {
      const blob = new Blob(['xlsx']);
      const result = await downloadBlob(blob, '审批中心.xlsx');

      assert.equal(result, 'saved');
      assert.equal(environment.state.pickerCalls, 1);
      assert.equal(written, blob);
      assert.equal(closed, true);
      assert.equal(environment.state.createdUrls, 0);
    } finally {
      environment.restore();
    }
  });

  it('reports cancellation without falling back to browser download', async () => {
    const environment = installDownloadEnvironment(async () => {
      throw Object.assign(new Error('cancelled'), { name: 'AbortError' });
    });
    try {
      const result = await downloadBlob(new Blob(['xlsx']), '审批中心.xlsx');

      assert.equal(result, 'cancelled');
      assert.equal(environment.state.createdUrls, 0);
      assert.equal(environment.state.clicked, 0);
    } finally {
      environment.restore();
    }
  });
});

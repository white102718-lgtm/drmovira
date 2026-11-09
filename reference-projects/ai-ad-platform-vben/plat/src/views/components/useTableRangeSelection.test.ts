import { ref } from 'vue';

import { describe, expect, it, vi } from 'vitest';

import {
  getSelectionBounds,
  isCellInSelection,
  serializeTableRange,
  useTableRangeSelection,
} from './useTableRangeSelection';

interface AssetRow {
  createdAt: string;
  identifier: string;
  name: string;
  owner: string;
}

const rows: AssetRow[] = [
  {
    createdAt: '2026-08-10 16:42',
    identifier: 'mp018@rrr.com',
    name: 'Facebook SEA 个号 018',
    owner: '未分配',
  },
  {
    createdAt: '2026-08-10 17:20',
    identifier: 'tt_70988101',
    name: 'TikTok 日本个号 01',
    owner: '赵宁',
  },
];

const columns = [
  { key: 'name', getText: (row: AssetRow) => row.name },
  { key: 'identifier', getText: (row: AssetRow) => row.identifier },
  { key: 'owner', getText: (row: AssetRow) => row.owner },
  { key: 'createdAt', getText: (row: AssetRow) => row.createdAt },
];

describe('table range selection', () => {
  it('normalizes a reverse drag into an inclusive rectangular range', () => {
    expect(
      getSelectionBounds({
        anchor: { columnIndex: 3, rowIndex: 1 },
        focus: { columnIndex: 1, rowIndex: 0 },
      }),
    ).toEqual({ columnEnd: 3, columnStart: 1, rowEnd: 1, rowStart: 0 });
  });

  it('recognizes cells inside and outside the selected rectangle', () => {
    const selection = {
      anchor: { columnIndex: 2, rowIndex: 0 },
      focus: { columnIndex: 1, rowIndex: 1 },
    };

    expect(isCellInSelection(selection, 0, 1)).toBe(true);
    expect(isCellInSelection(selection, 1, 2)).toBe(true);
    expect(isCellInSelection(selection, 0, 0)).toBe(false);
    expect(isCellInSelection(selection, 2, 1)).toBe(false);
  });

  it('serializes only the selected rows and columns as Excel-compatible TSV', () => {
    expect(
      serializeTableRange(rows, columns, {
        anchor: { columnIndex: 2, rowIndex: 0 },
        focus: { columnIndex: 1, rowIndex: 1 },
      }),
    ).toBe('mp018@rrr.com\t未分配\r\ntt_70988101\t赵宁');
  });

  it('keeps values with line breaks or tabs in a single copied cell', () => {
    expect(
      serializeTableRange(
        [
          {
            createdAt: '',
            identifier: 'id\t001',
            name: 'A\nB',
            owner: '',
          },
        ],
        columns,
        {
          anchor: { columnIndex: 0, rowIndex: 0 },
          focus: { columnIndex: 1, rowIndex: 0 },
        },
      ),
    ).toBe('A B\tid 001');
  });

  it('updates the range while dragging and clears it on demand', () => {
    const rangeSelection = useTableRangeSelection({
      columns: ref(columns),
      rows: ref(rows),
    });

    rangeSelection.beginSelection(0, 2);
    rangeSelection.extendSelection(1, 1);

    expect(rangeSelection.isSelecting.value).toBe(true);
    expect(rangeSelection.isCellSelected(0, 1)).toBe(true);
    expect(rangeSelection.getCopiedText()).toBe(
      'mp018@rrr.com\t未分配\r\ntt_70988101\t赵宁',
    );

    rangeSelection.endSelection();
    expect(rangeSelection.isSelecting.value).toBe(false);

    rangeSelection.clearSelection();

    expect(rangeSelection.selection.value).toBeUndefined();
    expect(rangeSelection.getCopiedText()).toBe('');
  });

  it('writes the selected range to a copy event and prevents native copy', () => {
    const rangeSelection = useTableRangeSelection({
      columns: ref(columns),
      rows: ref(rows),
    });
    const setData = vi.fn();
    const preventDefault = vi.fn();

    rangeSelection.beginSelection(0, 0);

    expect(
      rangeSelection.copySelection({
        clipboardData: { setData },
        preventDefault,
      } as unknown as ClipboardEvent),
    ).toBe(true);
    expect(setData).toHaveBeenCalledWith('text/plain', 'Facebook SEA 个号 018');
    expect(preventDefault).toHaveBeenCalledOnce();
  });

  it('moves or extends the focused cell without exceeding table boundaries', () => {
    const rangeSelection = useTableRangeSelection({
      columns: ref(columns),
      rows: ref(rows),
    });

    rangeSelection.beginSelection(0, 0);
    rangeSelection.endSelection();

    expect(rangeSelection.moveSelection(1, 1, true)).toBe(true);
    expect(rangeSelection.isCellSelected(1, 1)).toBe(true);
    expect(rangeSelection.moveSelection(1, 5, false)).toBe(true);
    expect(rangeSelection.selection.value).toEqual({
      anchor: { columnIndex: 3, rowIndex: 1 },
      focus: { columnIndex: 3, rowIndex: 1 },
    });
  });
});

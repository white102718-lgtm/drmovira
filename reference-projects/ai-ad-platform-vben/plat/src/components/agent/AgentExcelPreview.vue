<script lang="ts" setup>
/**
 * Excel 在线预览。文件还是那份 blob，用 SheetJS 拆成表画出来。
 * 合并单元格按工作簿原样还原，姓名 × 项目那种格子才对得上。
 */
import { computed, ref, watch } from 'vue';

import { Download, LoaderCircle } from 'lucide-vue-next';

import { Modal } from 'ant-design-vue';

import { fetchAttachment } from '#/api/agent';
import AgentDownloadLink from '#/components/agent/AgentDownloadLink.vue';

const props = defineProps<{
  filename: string;
  open: boolean;
  url: string;
}>();

const emit = defineEmits<{ 'update:open': [value: boolean] }>();

interface PreviewCell {
  colspan: number;
  rowspan: number;
  skip: boolean;
  text: string;
}

interface PreviewSheet {
  name: string;
  rows: PreviewCell[][];
}

interface Merge {
  e: { c: number; r: number };
  s: { c: number; r: number };
}

const loading = ref(false);
const failed = ref('');
const sheets = ref<PreviewSheet[]>([]);
const active = ref(0);
const blob = ref<Blob | null>(null);

const current = computed(() => sheets.value[active.value] ?? null);

let request = 0;

watch(
  () => [props.open, props.url] as const,
  ([open, url]) => {
    if (open && url) {
      void load(url);
      return;
    }
    request += 1;
    sheets.value = [];
    blob.value = null;
    failed.value = '';
    active.value = 0;
  },
);

async function load(url: string) {
  const mine = ++request;
  loading.value = true;
  failed.value = '';
  sheets.value = [];
  blob.value = null;
  active.value = 0;
  try {
    const file = await fetchAttachment(url);
    if (mine !== request) return;
    blob.value = file;
    const XLSX = await import('xlsx');
    if (mine !== request) return;
    const workbook = XLSX.read(await file.arrayBuffer(), {
      cellDates: true,
      type: 'array',
    });
    if (mine !== request) return;
    sheets.value = workbook.SheetNames.map((name) => {
      const sheet = workbook.Sheets[name];
      if (!sheet) return { name, rows: [] };
      const aoa = XLSX.utils.sheet_to_json<unknown[]>(sheet, {
        defval: '',
        header: 1,
        raw: false,
      });
      return { name, rows: cells(aoa, sheet['!merges'] ?? []) };
    }).filter((sheet) => sheet.rows.length > 0);
    if (sheets.value.length === 0) failed.value = '这个表格是空的。';
  } catch (error: any) {
    if (mine !== request) return;
    failed.value =
      error?.status === 404
        ? '这个文件已经过期了'
        : error?.message || '表格打开失败';
  } finally {
    if (mine === request) loading.value = false;
  }
}

function cells(aoa: unknown[][], merges: Merge[]): PreviewCell[][] {
  const maxCol = Math.max(
    1,
    ...aoa.map((row) => row.length),
    ...merges.map((merge) => merge.e.c + 1),
  );
  const maxRow = Math.max(
    aoa.length,
    ...merges.map((merge) => merge.e.r + 1),
    0,
  );
  const skip = new Set<string>();
  const span = new Map<string, { colspan: number; rowspan: number }>();
  for (const merge of merges) {
    span.set(`${merge.s.r},${merge.s.c}`, {
      colspan: merge.e.c - merge.s.c + 1,
      rowspan: merge.e.r - merge.s.r + 1,
    });
    for (let row = merge.s.r; row <= merge.e.r; row += 1) {
      for (let col = merge.s.c; col <= merge.e.c; col += 1) {
        if (row === merge.s.r && col === merge.s.c) continue;
        skip.add(`${row},${col}`);
      }
    }
  }
  const rows: PreviewCell[][] = [];
  for (let row = 0; row < maxRow; row += 1) {
    const line: PreviewCell[] = [];
    for (let col = 0; col < maxCol; col += 1) {
      const key = `${row},${col}`;
      const merged = span.get(key);
      line.push({
        colspan: merged?.colspan ?? 1,
        rowspan: merged?.rowspan ?? 1,
        skip: skip.has(key),
        text: String(aoa[row]?.[col] ?? ''),
      });
    }
    rows.push(line);
  }
  return rows;
}

function close() {
  emit('update:open', false);
}
</script>

<template>
  <Modal
    :open="open"
    :title="filename || '表格预览'"
    :footer="null"
    :width="1100"
    centered
    destroy-on-close
    wrap-class-name="agent-excel-preview"
    @cancel="close"
  >
    <div class="flex h-[70vh] flex-col">
      <div class="mb-3 flex shrink-0 items-center justify-between gap-3">
        <div class="flex min-w-0 flex-wrap gap-1">
          <button
            v-for="(sheet, index) in sheets"
            :key="sheet.name"
            type="button"
            class="rounded-md px-2.5 py-1 text-xs transition"
            :class="
              index === active
                ? 'bg-slate-900 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            "
            @click="active = index"
          >
            {{ sheet.name }}
          </button>
        </div>
        <AgentDownloadLink
          v-if="blob"
          class="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:border-slate-400"
          :url="url"
          :filename="filename || 'adpulse-export.xlsx'"
        >
          <Download class="h-3.5 w-3.5" />
          下载
        </AgentDownloadLink>
      </div>

      <div
        v-if="loading"
        class="flex flex-1 items-center justify-center text-sm text-slate-400"
      >
        <LoaderCircle class="mr-2 h-4 w-4 animate-spin" />
        正在打开表格…
      </div>
      <div
        v-else-if="failed"
        class="flex flex-1 items-center justify-center text-sm text-slate-400"
      >
        {{ failed }}
      </div>
      <div
        v-else-if="current"
        class="min-h-0 flex-1 overflow-auto rounded-lg border border-slate-200"
      >
        <table class="w-max min-w-full border-collapse text-xs">
          <tbody>
            <tr v-for="(row, rowIndex) in current.rows" :key="rowIndex">
              <template v-for="(cell, colIndex) in row" :key="colIndex">
                <th
                  v-if="!cell.skip && rowIndex === 0"
                  :colspan="cell.colspan"
                  :rowspan="cell.rowspan"
                  class="sticky top-0 z-10 whitespace-nowrap border border-slate-200 bg-[#0D4DCC] px-2.5 py-2 text-left font-medium text-white"
                >
                  {{ cell.text }}
                </th>
                <td
                  v-else-if="!cell.skip"
                  :colspan="cell.colspan"
                  :rowspan="cell.rowspan"
                  class="max-w-xs border border-slate-100 px-2.5 py-1.5 align-top text-slate-700"
                  :class="
                    colIndex <= 1
                      ? 'whitespace-nowrap bg-white'
                      : 'whitespace-pre-wrap'
                  "
                >
                  {{ cell.text }}
                </td>
              </template>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </Modal>
</template>

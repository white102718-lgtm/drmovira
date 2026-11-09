// 跨需求页面共用的常量配置
import { h } from 'vue';

import { Clock } from '@vben/icons';

import TagRow from './components/TagRow.vue';

import facebookCountries from '#/data/facebook_countries.json';

export const countryMap = Object.fromEntries(
  facebookCountries.map((c) => [c.code, `${c.name}`]),
);

/** country 映射为中文 */
export function buildTagLabels(tags?: { country?: string[]; theme?: string[]; gameplay?: string[] }): string[] {
  return [
    ...(tags?.country ?? []).map((c) => countryMap[c] ?? c),
    ...(tags?.theme ?? []),
    ...(tags?.gameplay ?? []),
  ].filter(Boolean);
}


export const priorityConfig: Record<string, { bg: string; color: string }> = {
  P0: { bg: '#fef2f2', color: '#ef4444' },
  P1: { bg: '#fff7ed', color: '#f97316' },
  P2: { bg: '#f3f4f6', color: '#6b7280' },
  P3: { bg: '#f3f4f6', color: '#9ca3af' },
};

export const demandTypeMap: Record<string, string> = {
  video: '视频',
  image: '图片',
};

// ==================== 表格列渲染工具 ====================

/** 标题列 tag 行：自适应容器宽度，溢出部分 +N Popover */
export function renderTagRow(tags: string[]) {
  return h(TagRow, { tags });
}

/** 交付时间列：显示日期 + 剩余/超时副文本（含时钟图标） */
export function renderDeadlineCell(row: { deadline: string; deadlineSub: string | null; deadlineSubClass: string }) {
  const showClock = row.deadlineSub?.startsWith('剩');
  const clockIcon = h(Clock, { class: 'inline-block w-3 h-3 mr-0.5 flex-shrink-0' });
  return [
    h('div', { class: 'text-center' }, [
      h('div', { class: 'text-xs text-gray-700' }, row.deadline),
      row.deadlineSub != null && h('div', { class: `inline-flex items-center text-xs font-medium mt-0.5 ${row.deadlineSubClass}` }, [
        showClock ? clockIcon : null,
        row.deadlineSub,
      ]),
    ]),
  ];
}

/** 将 remaining_hours 转换为统一的 deadline 显示文本和样式类 */
export function mapDeadline(remainHours: null | number | undefined) {
  const rh = remainHours ?? null;
  const deadlineSub = rh != null
    ? (rh >= 0 ? `剩 ${rh}h` : `超时 ${Math.abs(rh)}h`)
    : null;
  const deadlineSubClass = rh == null
    ? 'text-gray-400'
    : rh < 0 || rh <= 24
      ? 'text-red-500'
      : 'text-orange-400';
  return { deadlineSub, deadlineSubClass };
}

// key 为英文状态码
export const statusColorMap: Record<string, string> = {
  draft: '#9ca3af',
  pending_review: '#3b82f6',
  pending_assign: '#f97316',
  assigned: '#f97316',
  in_production: '#16a34a',
  pending_accept: '#059669',
  rejected: '#ef4444',
  accepted: '#6b7280',
  archived: '#9ca3af',
};

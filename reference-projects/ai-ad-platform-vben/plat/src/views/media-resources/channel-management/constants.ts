export const TEAM_OPTIONS = ['Mpower', 'ZCLINK', 'Firefly'].map((value) => ({
  label: value,
  value,
}));

export const SETTLEMENT_OPTIONS = [
  '预付实消',
  '日结',
  '周结',
  '预充值',
  '预结算',
  '买断',
].map((value) => ({ label: value, value }));

export const TIMEZONE_OPTIONS = Array.from({ length: 27 }, (_, index) => {
  const offset = index - 12;
  const value = `UTC${offset >= 0 ? '+' : ''}${offset}`;
  return { label: value, value };
});

export const REGION_OPTIONS = [
  '全部地区',
  '北美',
  '拉丁美洲',
  '欧洲',
  '东南亚',
  '南亚',
  '东亚',
  '中东',
  '非洲',
  '大洋洲',
].map((value, index) => ({ label: value, value: index === 0 ? '999' : value }));

export const ACCOUNT_STATUS_OPTIONS = [
  1, 2, 3, 7, 8, 9, 100, 101, 201, 202,
].map((value) => ({
  label: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[value]!,
  value: String(value),
}));

export const USAGE_STATUS_OPTIONS = [
  { color: 'default', label: '未使用', value: '0' },
  { color: 'success', label: '使用中', value: '1' },
];

export function formatMoney(value: unknown, divisor = 1): string {
  const amount = Number(value ?? 0) / divisor;
  return Number.isFinite(amount) ? amount.toFixed(2) : '0.00';
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
import { FACEBOOK_AD_ACCOUNT_STATUS_LABELS } from '#/constants/facebook-ad-account-status';

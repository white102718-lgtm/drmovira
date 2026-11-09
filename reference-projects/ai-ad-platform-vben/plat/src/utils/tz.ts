import dayjs from 'dayjs';

/**
 * 将中国时区日期转为浏览器本地时区同一天的零点时间戳
 * NaivUI 用浏览器本地时区解析时间戳显示日期，直接传 CST 零点（UTC+8 midnight）
 * 在 UTC-8 等时区会显示前一天，需转为本地时区等效零点
 */
export const toLocalDayStart = (d: { format: (fmt: string) => string }): number =>
  dayjs(d.format('YYYY-MM-DD')).valueOf();

export const toLocalDayEnd = (d: { format: (fmt: string) => string }): number =>
  dayjs(d.format('YYYY-MM-DD')).endOf('day').valueOf();

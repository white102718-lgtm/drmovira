interface TaskResultPage<T> {
  items: T[];
  pageSize?: number;
  total?: number;
}

/**
 * 从第一页开始收集当前查询下的全部任务，供看板和仪表盘共用。
 * 切换查询后停止取数；分页重复或提前结束时报错，避免把残缺数据当成全量统计。
 */
export async function loadAllTaskPages<T extends { id: string }>(
  firstPage: TaskResultPage<T>,
  fetchPage: (page: number) => Promise<TaskResultPage<T>>,
  isCurrent: () => boolean,
  requestedPageSize: number,
): Promise<T[] | undefined> {
  const items = new Map<string, T>();
  const total = firstPage.total;
  const pageSize = firstPage.pageSize ?? requestedPageSize;
  let page = firstPage;
  let pageNumber = 1;

  while (isCurrent()) {
    const previousSize = items.size;
    for (const item of page.items) items.set(item.id, item);
    if (
      total === undefined ? page.items.length < pageSize : items.size >= total
    ) {
      return [...items.values()];
    }
    if (page.items.length === 0 || items.size === previousSize) {
      throw new Error('任务数据不完整，请刷新后重试');
    }
    pageNumber += 1;
    page = await fetchPage(pageNumber);
  }
  return undefined;
}

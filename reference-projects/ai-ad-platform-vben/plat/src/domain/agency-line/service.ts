import type { AgencyLineAdapter } from './adapter';
import type {
  AgencyLine,
  AgencyLineDeliveryUrlHistory,
  AgencyLineImportError,
  AgencyLineImportResult,
  AgencyLineListQuery,
  AgencyLineListResult,
  AgencyLineOption,
  AgencyLineSaveManyOptions,
  AgencyLineUpsertInput,
} from './types';

import { parseAgencyLineImportRows } from './bulk-import';
import { normalizeAgencyLineInput } from './validation';

export interface AgencyLineServiceOptions {
  requestId?: () => string;
}

interface AgencyLineCreateAttempt {
  fingerprint: string;
  operation?: Promise<AgencyLine>;
  result?: AgencyLine;
}

/** 固定本次导入的写入目标和内容，重试不能从新增意外变为覆盖。 */
interface AgencyLineImportAttempt extends AgencyLineCreateAttempt {
  input: AgencyLineUpsertInput;
  update: boolean;
}

export class AgencyLineService {
  private readonly createAttempts = new Map<string, AgencyLineCreateAttempt>();
  private readonly importAttempts = new Map<string, AgencyLineImportAttempt>();
  private readonly requestId: () => string;

  constructor(
    private readonly adapter: AgencyLineAdapter,
    options: AgencyLineServiceOptions = {},
  ) {
    this.requestId =
      options.requestId ??
      (() =>
        typeof crypto?.randomUUID === 'function'
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
  }

  async create(
    input: AgencyLineUpsertInput,
    requestId: string,
  ): Promise<AgencyLine> {
    if (!requestId.trim()) throw new Error('创建代理线请求 ID 不能为空');
    const normalized = normalizeAgencyLineInput(input);
    const fingerprint = JSON.stringify(normalized);
    let attempt = this.createAttempts.get(requestId);
    if (attempt && attempt.fingerprint !== fingerprint) {
      throw new Error('同一创建请求 ID 不能用于不同代理线数据');
    }
    if (!attempt) {
      await this.validateUniqueNormalizedInput(normalized);
      attempt = { fingerprint };
      this.createAttempts.set(requestId, attempt);
    }
    if (attempt.result) return attempt.result;
    if (attempt.operation) return attempt.operation;

    const operation = this.adapter.create({ input: normalized, requestId });
    attempt.operation = operation;
    try {
      const result = await operation;
      attempt.result = result;
      return result;
    } finally {
      attempt.operation = undefined;
    }
  }

  get(id: string): Promise<AgencyLine> {
    if (!id.trim()) return Promise.reject(new Error('代理线 ID 不能为空'));
    return this.adapter.get(id);
  }

  getDeliveryUrlHistory(id: string): Promise<AgencyLineDeliveryUrlHistory[]> {
    if (!id.trim()) return Promise.reject(new Error('代理线 ID 不能为空'));
    return this.adapter.getDeliveryUrlHistory(id);
  }

  list(query: AgencyLineListQuery = {}): Promise<AgencyLineListResult> {
    return this.adapter.list(query);
  }

  listOptions(query: AgencyLineListQuery = {}): Promise<AgencyLineOption[]> {
    return this.adapter.listOptions(query);
  }

  remove(id: string): Promise<void> {
    if (!id.trim()) return Promise.reject(new Error('代理线 ID 不能为空'));
    return this.adapter.remove(id);
  }

  /** 批量删除逐项执行后端软删除，返回部分失败项供界面保留并重试。 */
  async removeMany(ids: readonly string[]) {
    const removedIds: string[] = [];
    const failures: Array<{ id: string; message: string }> = [];
    for (const id of new Set(ids)) {
      try {
        if (!id.trim()) throw new Error('代理线 ID 不能为空');
        await this.remove(id);
        removedIds.push(id);
      } catch (error) {
        failures.push({
          id,
          message: error instanceof Error ? error.message : '删除失败，请重试',
        });
      }
    }
    return { removedIds, failures };
  }

  async save(input: AgencyLineUpsertInput): Promise<AgencyLine> {
    const normalized = await this.validateUniqueInput(input);
    return this.adapter.save(normalized);
  }

  async saveMany(
    sources: readonly unknown[],
    options: AgencyLineSaveManyOptions = {},
  ): Promise<AgencyLineImportResult> {
    if (options.rowNumbers && options.rowNumbers.length !== sources.length) {
      throw new Error('批量导入原始行号与数据行数量不一致');
    }
    const rawParsed = parseAgencyLineImportRows(sources);
    const remapRow = (row: number) =>
      row === 0 ? 0 : (options.rowNumbers?.[row - 1] ?? row);
    const parsed = {
      ...rawParsed,
      errors: rawParsed.errors.map((error) => ({
        ...error,
        row: remapRow(error.row),
      })),
      rows: rawParsed.rows.map((row) => ({
        ...row,
        row: remapRow(row.row),
      })),
    };
    if (parsed.errors.length > 0) {
      return {
        errors: parsed.errors,
        importedItems: [],
        items: [],
        status: 'validation_failed',
        total: parsed.total,
      };
    }

    const duplicateErrors: AgencyLineImportError[] = [];
    const rowsByName = new Map<string, number[]>();
    for (const row of parsed.rows) {
      const key = row.input.name.toLowerCase();
      rowsByName.set(key, [...(rowsByName.get(key) ?? []), row.row]);
    }
    for (const [name, rows] of rowsByName) {
      if (rows.length < 2) continue;
      const locations = rows.join('、');
      for (const row of rows) {
        duplicateErrors.push({
          code: 'duplicate',
          field: 'name',
          message: `批次内代理线名称重复：${name}（数据行 ${locations}）`,
          row,
        });
      }
    }

    let existing: AgencyLineListResult;
    try {
      existing = await this.adapter.list({ page: 1, pageSize: 200 });
      while (existing.items.length < existing.total) {
        const next = await this.adapter.list({
          page: existing.page + 1,
          pageSize: 200,
        });
        if (!next.items.length) throw new Error('代理线列表加载不完整，请重试');
        existing = { ...next, items: [...existing.items, ...next.items] };
      }
    } catch (error) {
      return {
        errors: [
          {
            code: 'preflight_failed',
            field: 'row',
            message:
              error instanceof Error ? error.message : '批量导入预检查失败',
            row: 0,
          },
        ],
        importedItems: [],
        items: [],
        status: 'failed',
        total: parsed.total,
      };
    }

    for (const row of parsed.rows) {
      const duplicate = existing.items.find(
        (line) =>
          line.id !== row.input.id &&
          line.name.trim().toLowerCase() === row.input.name.toLowerCase(),
      );
      const isIdempotentRetry =
        options.retry && Boolean(options.requestIdsByRow?.[row.row]);
      if (duplicate && !isIdempotentRetry && !options.overwriteExisting) {
        duplicateErrors.push({
          code: 'duplicate',
          field: 'name',
          message: `代理线名称已存在（ID：${duplicate.id}）`,
          row: row.row,
        });
      }
    }

    if (duplicateErrors.length > 0) {
      return {
        errors: duplicateErrors,
        importedItems: [],
        items: [],
        status: 'validation_failed',
        total: parsed.total,
      };
    }

    const errors: AgencyLineImportError[] = [];
    const importedItems: AgencyLineImportResult['importedItems'] = [];
    const items: AgencyLine[] = [];
    for (const row of parsed.rows) {
      const requestId =
        options.requestIdsByRow?.[row.row] ??
        `agency-line-import-${row.row}-${this.requestId()}`;
      try {
        const target = options.overwriteExisting
          ? existing.items.find(
              (line) =>
                line.name.trim().toLowerCase() === row.input.name.toLowerCase(),
            )
          : undefined;
        const line = await this.saveImportedRow(
          row.input,
          requestId,
          target,
          Boolean(options.overwriteExisting),
        );
        items.push(line);
        importedItems.push({
          line,
          requestId,
          requestedProjectId: row.input.projectId,
          row: row.row,
        });
      } catch (error) {
        errors.push({
          code: 'save_failed',
          field: 'row',
          message: error instanceof Error ? error.message : '保存失败',
          recoverable: true,
          requestId,
          row: row.row,
        });
      }
    }

    let status: AgencyLineImportResult['status'] = 'success';
    if (errors.length > 0) status = items.length > 0 ? 'partial' : 'failed';

    return {
      errors,
      importedItems,
      items,
      status,
      total: parsed.total,
    };
  }

  /** 更新只覆盖模板可编辑字段，保留预算、启停等未出现在模板中的配置。 */
  private async saveImportedRow(
    input: AgencyLineUpsertInput,
    requestId: string,
    target: AgencyLine | undefined,
    overwrite: boolean,
  ): Promise<AgencyLine> {
    const fingerprint = JSON.stringify({ input, overwrite });
    let attempt = this.importAttempts.get(requestId);
    if (attempt && attempt.fingerprint !== fingerprint) {
      throw new Error('同一导入请求 ID 不能用于不同数据或覆盖模式');
    }
    if (!attempt) {
      const payload = target
        ? {
            ...target,
            name: input.name,
            platform: input.platform,
            deliveryUrl: input.deliveryUrl,
            cloakUrl: input.cloakUrl,
            pageId: input.pageId,
            pixelId: input.pixelId,
            pixelName: input.pixelName,
            testCode: input.testCode,
            token: input.token,
            type: input.type,
            optimizerId: input.optimizerId,
            optimizerName: input.optimizerName,
            projectId: input.projectId || target.projectId,
          }
        : input;
      attempt = { fingerprint, input: payload, update: Boolean(target) };
      this.importAttempts.set(requestId, attempt);
    }
    if (attempt.result) return attempt.result;
    if (attempt.operation) return attempt.operation;
    const operation = attempt.update
      ? this.save(attempt.input)
      : this.create(attempt.input, requestId);
    attempt.operation = operation;
    try {
      attempt.result = await operation;
      return attempt.result;
    } finally {
      attempt.operation = undefined;
    }
  }

  private async validateUniqueInput(input: AgencyLineUpsertInput) {
    const normalized = normalizeAgencyLineInput(input);
    await this.validateUniqueNormalizedInput(normalized);
    return normalized;
  }

  private async validateUniqueNormalizedInput(
    normalized: AgencyLineUpsertInput,
  ) {
    const normalizedName = normalized.name;
    const existing = await this.adapter.list({
      keyword: normalizedName,
      page: 1,
      pageSize: 1000,
    });
    if (
      existing.items.some(
        (line) =>
          line.id !== normalized.id &&
          line.name.trim().toLowerCase() === normalizedName.toLowerCase(),
      )
    ) {
      throw new Error('代理线名称已存在，请使用其他名称');
    }
  }
}

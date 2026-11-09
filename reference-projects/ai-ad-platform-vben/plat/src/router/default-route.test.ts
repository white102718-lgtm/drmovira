// @ts-nocheck -- 仓库当前未向 plat 的生产类型检查暴露 Vitest 类型。
import type { MenuRecordRaw, RouteRecordRaw } from '@vben/types';

import { describe, expect, it } from 'vitest';

import { resolveAuthorizedDefaultPath } from './default-route';

function route(path: string, children?: RouteRecordRaw[]): RouteRecordRaw {
  return {
    name: path,
    path,
    component: { render: () => null },
    children,
  } as RouteRecordRaw;
}

function menu(path: string, children?: MenuRecordRaw[]): MenuRecordRaw {
  return { name: path, path, children };
}

describe('resolveAuthorizedDefaultPath', () => {
  it('优先返回已授权首页', () => {
    expect(
      resolveAuthorizedDefaultPath({
        accessibleMenus: [menu('/home'), menu('/workbench')],
        accessibleRoutes: [route('/home'), route('/workbench')],
        preferredPath: '/home',
      }),
    ).toBe('/home');
  });

  it('首页未授权时返回首个内部菜单', () => {
    expect(
      resolveAuthorizedDefaultPath({
        accessibleMenus: [menu('https://example.com'), menu('/workbench')],
        accessibleRoutes: [route('/workbench')],
        preferredPath: '/home',
      }),
    ).toBe('/workbench');
  });

  it('没有可见菜单时返回后端欢迎路由', () => {
    expect(
      resolveAuthorizedDefaultPath({
        accessibleMenus: [],
        accessibleRoutes: [route('/welcome')],
        preferredPath: '/home',
      }),
    ).toBe('/welcome');
  });

  it('没有任何可用路由时返回无权限页', () => {
    expect(
      resolveAuthorizedDefaultPath({
        accessibleMenus: [menu('https://example.com')],
        accessibleRoutes: [],
        preferredPath: '/home',
      }),
    ).toBe('/forbidden');
  });
});

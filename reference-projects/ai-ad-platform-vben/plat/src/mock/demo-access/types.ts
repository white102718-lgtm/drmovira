import type { RouteRecordStringComponent } from '@vben/types';

import type { DemoRoleId } from '#/mock/demo-role-preview';

/**
 * Local-only data ranges used by the role-switching demonstration.  They are
 * deliberately kept out of the production authentication contract.
 */
export type DemoDataScope = 'ALL' | 'DEPARTMENT' | 'PROJECT' | 'SELF' | 'TEAM';

export type DemoBusinessObject =
  | 'adAccount'
  | 'creativeTask'
  | 'finance'
  | 'material'
  | 'project'
  | 'resourceApplication'
  | 'task';

export type DemoActionCode =
  | 'ad.create'
  | 'ad.manage'
  | 'ad.monitor'
  | 'finance.read'
  | 'finance.write'
  | 'material.create'
  | 'material.manage'
  | 'material.read'
  | 'material.submit'
  | 'material.use'
  | 'project.create'
  | 'project.edit'
  | 'project.read'
  | 'resource.allocate'
  | 'resource.apply'
  | 'resource.approve'
  | 'resource.manage'
  | 'resource.read'
  | 'system.manage'
  | 'system.read'
  | 'task.accept'
  | 'task.assign'
  | 'task.create'
  | 'task.process'
  | 'task.read';

export interface DemoRolePolicy {
  actionCodes: readonly DemoActionCode[];
  dataScopes: Readonly<Partial<Record<DemoBusinessObject, DemoDataScope[]>>>;
  homeConfigKey: DemoRoleId;
  /** `*` intentionally remains Demo-only and is never sent to an API. */
  routeNames: '*' | readonly string[];
}

export interface DemoActor {
  departmentId: string;
  roleCodes: readonly string[];
  roleId: DemoRoleId;
  teamIds: readonly string[];
  userId: string;
}

export interface DemoProjectMembership {
  projectId: string;
  role: 'am' | 'creative-lead' | 'creator' | 'delivery-lead' | 'operator';
  teamId?: string;
  userId: string;
}

export type DemoMenuNode = RouteRecordStringComponent & {
  children?: DemoMenuNode[];
};

import type { RouteRecordStringComponent } from '@vben/types';

import type {
  DemoActionCode,
  DemoActor,
  DemoBusinessObject,
  DemoMenuNode,
  DemoProjectMembership,
} from './types';

import type { DemoRoleId, DemoRoleProfile } from '#/mock/demo-role-preview';

import { readSelectedDemoRole } from '#/mock/demo-role-preview';

import {
  demoProjectMemberships,
  demoUserRelations,
  getDemoProjectIds,
} from './relationships';
import {
  demoManagedRouteNames,
  demoRoutePathByName,
  getDemoRolePolicy,
} from './role-policies';

export function getDemoActor(profile: DemoRoleProfile): DemoActor {
  const relation =
    demoUserRelations[profile.userId as keyof typeof demoUserRelations];
  return {
    departmentId: relation?.departmentId ?? 'department-demo',
    roleCodes: profile.roles,
    roleId: profile.id,
    teamIds: relation?.teamIds ?? [],
    userId: profile.userId,
  };
}

export function getCurrentDemoActor(): DemoActor | undefined {
  const profile = readSelectedDemoRole();
  return profile ? getDemoActor(profile) : undefined;
}

export function getDemoAccessCodes(roleId: DemoRoleId): string[] {
  return [...getDemoRolePolicy(roleId).actionCodes];
}

export function canDemoAction(
  actor: DemoActor | undefined,
  action: DemoActionCode,
): boolean {
  if (!actor) return false;
  return getDemoRolePolicy(actor.roleId).actionCodes.includes(action);
}

export function hasDemoScope(
  actor: DemoActor | undefined,
  object: DemoBusinessObject,
  scope: 'ALL' | 'DEPARTMENT' | 'PROJECT' | 'SELF' | 'TEAM',
): boolean {
  if (!actor) return false;
  return Boolean(
    getDemoRolePolicy(actor.roleId).dataScopes[object]?.includes(scope),
  );
}

export function canDemoRoute(
  roleId: DemoRoleId,
  routeName: null | string | undefined,
): boolean {
  if (!routeName) return false;
  const routeNames = getDemoRolePolicy(roleId).routeNames;
  return routeNames === '*' || routeNames.includes(routeName);
}

export function isDemoManagedRouteName(
  routeName: null | string | undefined,
): boolean {
  return Boolean(routeName && demoManagedRouteNames.has(routeName));
}

export function getDemoRouteNameByPath(path: string): string | undefined {
  return Object.entries(demoRoutePathByName).find(
    ([, candidate]) => candidate === path,
  )?.[0];
}

function cloneRoute(
  node: DemoMenuNode,
  children?: DemoMenuNode[],
): DemoMenuNode {
  return {
    ...node,
    children,
    meta: node.meta ? { ...node.meta } : node.meta,
  };
}

/**
 * Filters the unified Demo menu without mutating the schema.  A group exists
 * only when it still has a visible child; hidden deep-links remain present
 * only for roles explicitly allowed to access their business action.
 */
export function filterDemoMenuTree(
  tree: readonly RouteRecordStringComponent[],
  roleId: DemoRoleId,
): RouteRecordStringComponent[] {
  const visit = (node: DemoMenuNode): DemoMenuNode | undefined => {
    if (node.children?.length) {
      const children: DemoMenuNode[] = [];
      for (const child of node.children) {
        const allowedChild = visit(child);
        if (allowedChild) children.push(allowedChild);
      }
      return children.length > 0 ? cloneRoute(node, children) : undefined;
    }
    return canDemoRoute(roleId, String(node.name ?? ''))
      ? cloneRoute(node)
      : undefined;
  };

  const filtered: DemoMenuNode[] = [];
  for (const node of tree) {
    const allowedNode = visit(node as DemoMenuNode);
    if (allowedNode) filtered.push(allowedNode);
  }
  return filtered;
}

interface ProjectLike {
  amUserId?: string;
  deliveryLeaderId?: string;
  id: string;
}

export function canDemoReadProject<T extends ProjectLike>(
  actor: DemoActor | undefined,
  project: T,
): boolean {
  if (!actor) return true;
  if (hasDemoScope(actor, 'project', 'ALL')) return true;
  if (
    project.amUserId === actor.userId ||
    project.deliveryLeaderId === actor.userId
  ) {
    return true;
  }
  return getDemoProjectIds(actor.userId).includes(project.id);
}

export function filterDemoProjects<T extends ProjectLike>(
  actor: DemoActor | undefined,
  projects: readonly T[],
): T[] {
  return actor
    ? projects.filter((project) => canDemoReadProject(actor, project))
    : [...projects];
}

export function canDemoEditProject<T extends ProjectLike>(
  actor: DemoActor | undefined,
  project: T,
): boolean {
  if (!actor) return true;
  if (!canDemoAction(actor, 'project.edit')) return false;
  if (actor.roleId === 'admin') return true;
  return (
    project.amUserId === actor.userId ||
    demoProjectMemberships.some(
      (membership) =>
        membership.userId === actor.userId &&
        membership.role === 'am' &&
        membership.projectId === project.id,
    )
  );
}

interface TaskLike {
  assignments?: readonly {
    assigneeId: string;
    departmentId?: string;
    teamCodes?: readonly string[];
  }[];
  audiences?: readonly string[];
  createdBy?: string;
  ownerId?: string;
  projectId?: string;
}

function actorMemberships(actor: DemoActor): readonly DemoProjectMembership[] {
  return demoProjectMemberships.filter(
    (membership) => membership.userId === actor.userId,
  );
}

export function canDemoReadTask<T extends TaskLike>(
  actor: DemoActor | undefined,
  task: T,
): boolean {
  if (!actor) return true;
  if (hasDemoScope(actor, 'task', 'ALL')) return true;
  const policy = getDemoRolePolicy(actor.roleId);
  const assignments = task.assignments ?? [];
  const isAssignee = assignments.some(
    (assignment) => assignment.assigneeId === actor.userId,
  );
  const isOwner = task.ownerId === actor.userId;
  if (policy.dataScopes.task?.includes('SELF') && (isAssignee || isOwner))
    return true;
  if (
    policy.dataScopes.task?.includes('PROJECT') &&
    task.projectId &&
    getDemoProjectIds(actor.userId).includes(task.projectId)
  ) {
    return true;
  }
  if (policy.dataScopes.task?.includes('TEAM')) {
    const teams = new Set(actor.teamIds);
    const inTaskTeam = assignments.some(
      (assignment) =>
        assignment.teamCodes?.some((team) => teams.has(team)) ||
        assignment.departmentId === actor.departmentId,
    );
    const inProjectTeam = actorMemberships(actor).some(
      (membership) =>
        membership.projectId === task.projectId &&
        membership.teamId &&
        teams.has(membership.teamId),
    );
    if (inTaskTeam || inProjectTeam) return true;
  }
  if (policy.dataScopes.task?.includes('DEPARTMENT')) {
    return Boolean(
      actor.departmentId === 'department-media' &&
        task.audiences?.some((item) => ['media', 'reviewer'].includes(item)),
    );
  }
  return false;
}

export function filterDemoTasks<T extends TaskLike>(
  actor: DemoActor | undefined,
  tasks: readonly T[],
): T[] {
  return actor
    ? tasks.filter((task) => canDemoReadTask(actor, task))
    : [...tasks];
}

interface ResourceAccountLike {
  assigneeId?: string;
  projectId?: string;
  teamId?: string;
}

export function canDemoReadAdAccount<T extends ResourceAccountLike>(
  actor: DemoActor | undefined,
  account: T,
): boolean {
  if (!actor) return true;
  if (hasDemoScope(actor, 'adAccount', 'ALL')) return true;
  if (
    hasDemoScope(actor, 'adAccount', 'SELF') &&
    account.assigneeId === actor.userId
  )
    return true;
  if (
    hasDemoScope(actor, 'adAccount', 'PROJECT') &&
    account.projectId &&
    getDemoProjectIds(actor.userId).includes(account.projectId)
  )
    return true;
  return Boolean(
    hasDemoScope(actor, 'adAccount', 'TEAM') &&
      account.teamId &&
      actor.teamIds.includes(account.teamId),
  );
}

export function filterDemoAdAccounts<T extends ResourceAccountLike>(
  actor: DemoActor | undefined,
  accounts: readonly T[],
): T[] {
  return actor
    ? accounts.filter((account) => canDemoReadAdAccount(actor, account))
    : [...accounts];
}

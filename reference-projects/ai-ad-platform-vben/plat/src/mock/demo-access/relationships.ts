import type { DemoProjectMembership } from './types';

/** Local stable-ID relationships shared by every role view in Demo mode. */
export const demoUserRelations = {
  'user-1': {
    departmentId: 'department-delivery',
    teamIds: ['team-delivery-a'],
  },
  'user-2': {
    departmentId: 'department-creative',
    teamIds: ['team-creative-a'],
  },
  'user-3': {
    departmentId: 'department-delivery',
    teamIds: ['team-delivery-a'],
  },
  'user-4': { departmentId: 'department-platform', teamIds: ['team-platform'] },
  'user-6': { departmentId: 'department-am', teamIds: ['team-am-a'] },
  'user-7': {
    departmentId: 'department-creative',
    teamIds: ['team-creative-a'],
  },
  'user-8': { departmentId: 'department-media', teamIds: ['team-media-a'] },
  'user-9': { departmentId: 'department-finance', teamIds: ['team-finance'] },
} as const;

export const demoProjectMemberships: readonly DemoProjectMembership[] = [
  {
    projectId: 'project-starfall',
    role: 'am',
    teamId: 'team-am-a',
    userId: 'user-6',
  },
  {
    projectId: 'project-ark',
    role: 'am',
    teamId: 'team-am-a',
    userId: 'user-6',
  },
  {
    projectId: 'project-starfall',
    role: 'delivery-lead',
    teamId: 'team-delivery-a',
    userId: 'user-3',
  },
  {
    projectId: 'project-pixel',
    role: 'delivery-lead',
    teamId: 'team-delivery-a',
    userId: 'user-3',
  },
  {
    projectId: 'project-starfall',
    role: 'operator',
    teamId: 'team-delivery-a',
    userId: 'user-1',
  },
  {
    projectId: 'project-ark',
    role: 'operator',
    teamId: 'team-delivery-a',
    userId: 'user-1',
  },
  {
    projectId: 'project-starfall',
    role: 'creative-lead',
    teamId: 'team-creative-a',
    userId: 'user-7',
  },
  {
    projectId: 'project-pixel',
    role: 'creative-lead',
    teamId: 'team-creative-a',
    userId: 'user-7',
  },
  {
    projectId: 'project-starfall',
    role: 'creator',
    teamId: 'team-creative-a',
    userId: 'user-2',
  },
  {
    projectId: 'project-pixel',
    role: 'creator',
    teamId: 'team-creative-a',
    userId: 'user-2',
  },
];

export function getDemoProjectIds(userId: string): string[] {
  return demoProjectMemberships
    .filter((membership) => membership.userId === userId)
    .map((membership) => membership.projectId);
}

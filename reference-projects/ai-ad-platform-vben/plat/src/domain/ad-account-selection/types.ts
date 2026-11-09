export type SelectableAdAccountPlatform = 'facebook' | 'google' | 'tiktok';

export type AdAccountAuthorizationStatus =
  | 'authorized'
  | 'expired'
  | 'pending'
  | 'revoked';

export type AdAccountStatus =
  | 'active'
  | 'closed'
  | 'disabled'
  | 'pending_review'
  | 'restricted'
  | 'unsettled';

export type AdAccountResourceStatus =
  | 'assigned'
  | 'available'
  | 'exception'
  | 'maintenance'
  | 'pending_assignment'
  | 'pending_return'
  | 'retired';

export type AdAccountAssignmentStatus =
  | 'active'
  | 'return_requested'
  | 'returned';

export type AdAccountBindingStatus =
  | 'bound'
  | 'expired'
  | 'expiring'
  | 'unbound';

export interface AdAccountAssetReference {
  id: string;
  name: string;
  ownerId?: string;
  ownerName?: string;
  pictureUrl?: string;
}

export interface AdAccountBusinessManager {
  id?: string;
  name?: string;
}

export interface SelectableAdAccount {
  accountStatus: AdAccountStatus;
  adAccountId: string;
  agencyLineId: string;
  assigneeId: string;
  assigneeName: string;
  assignmentStatus: AdAccountAssignmentStatus;
  authorizationExpiresAt?: string;
  authorizationStatus: AdAccountAuthorizationStatus;
  balance?: number;
  bindingStatus: AdAccountBindingStatus;
  businessManager: AdAccountBusinessManager;
  currency?: string;
  id: string;
  name: string;
  pages: AdAccountAssetReference[];
  pixels: AdAccountAssetReference[];
  platform: SelectableAdAccountPlatform;
  projectId: string;
  resourceStatus: AdAccountResourceStatus;
  spendCap?: number;
}

export interface AdAccountSelectionQuery {
  accountIds?: string[];
  accountNames?: string[];
  agencyLineId?: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
  pixelName?: string;
  platform: SelectableAdAccountPlatform;
  projectId: string;
  userId?: string;
  userName?: string;
}

export interface AdAccountSelectionResult {
  items: SelectableAdAccount[];
  page: number;
  pageSize: number;
  total: number;
}

export interface MockAdAccountAssetFacts {
  authorizationExpiresAt?: string;
  authorizationStatus: AdAccountAuthorizationStatus;
  bindingStatus: AdAccountBindingStatus;
  pages: AdAccountAssetReference[];
  pixels: AdAccountAssetReference[];
}

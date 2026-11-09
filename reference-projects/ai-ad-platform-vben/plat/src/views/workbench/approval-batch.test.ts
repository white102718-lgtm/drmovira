import type { ResourceApplication } from '#/domain/application';

import { describe, expect, it } from 'vitest';

import { isBatchDecisionEligible } from './approval-batch';

function application(id: string, status = 'pending') {
  return { id, status } as ResourceApplication;
}

describe('approval batch selection', () => {
  it('accepts only pending backend applications handled by the current approver', () => {
    expect(isBatchDecisionEligible(application('31'), true, true)).toBe(true);
    expect(isBatchDecisionEligible(application('31'), true, false)).toBe(false);
    expect(isBatchDecisionEligible(application('demo-31'), true, true)).toBe(false);
    expect(isBatchDecisionEligible(application('31', 'approved'), true, true)).toBe(
      false,
    );
    expect(isBatchDecisionEligible(application('31'), false, true)).toBe(false);
  });
});

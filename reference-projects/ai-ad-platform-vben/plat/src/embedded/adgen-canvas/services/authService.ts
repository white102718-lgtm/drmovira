import { BACKEND_URL } from './runtimeConfig';
import { getAdgenCanvasAccessToken } from '../runtime';
import { readCanvasModelApiResponse } from '../../../api/canvas-model-response';

const API_BASE = BACKEND_URL;
const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';

export type UserRole = 'super_admin' | 'admin' | 'user';

export interface User {
  _id: string;
  username: string;
  email: string;
  created_at: string;
  is_active?: boolean;
  is_admin?: boolean;
  role?: UserRole;
  totp_enabled?: boolean;
  nickname?: string;
  real_name?: string;
  daily_limit?: number | null;
  weekly_limit?: number | null;
  monthly_limit?: number | null;
}

export interface RolePermissions {
  permissions: Record<string, string[]>;
  all_pages: string[];
}

export interface AuthSuccess {
  user: User;
  token: string;
  requirePasswordChange?: boolean;
}

export interface TotpSetupChallenge {
  mfaSetupRequired: true;
  challengeToken: string;
  secret: string;
  otpauthUrl: string;
  qrCodeDataUrl: string;
  user?: User;
}

export interface TotpVerifyChallenge {
  mfaRequired: true;
  challengeToken: string;
  user?: User;
}

export type LoginResult = AuthSuccess | TotpSetupChallenge | TotpVerifyChallenge;

const isAuthSuccess = (data: LoginResult): data is AuthSuccess => {
  return 'token' in data && !!data.token;
};

export const authService = {
  getToken(): string | null {
    return getAdgenCanvasAccessToken();
  },

  getUser(): User | null {
    const user = localStorage.getItem(USER_KEY);
    return user ? JSON.parse(user) : null;
  },

  setAuth(token: string, user: User): void {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },

  clearAuth(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },

  isAuthenticated(): boolean {
    return !!this.getToken();
  },

  async listUsers(): Promise<User[]> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/users`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    return data.data.users;
  },

  async updateProfile(nickname: string): Promise<{ user: User }> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/update-profile`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      body: JSON.stringify({ nickname }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    this.setAuth(token!, data.data.user);
    return data.data;
  },

  async adminCreateUser(username: string, password: string, nickname: string): Promise<void> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/users/create`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ username, password, nickname }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
  },

  async adminResetUserPassword(userId: string): Promise<void> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/users/${userId}/reset-password`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
  },

  async adminResetUserTotp(userId: string): Promise<void> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/users/${userId}/reset-totp`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
  },

  async toggleUserActive(userId: string, isActive: boolean): Promise<void> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/users/${userId}/toggle-active`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ isActive }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
  },

  async toggleUserAdmin(userId: string, isAdmin: boolean): Promise<void> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/users/${userId}/toggle-admin`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ isAdmin }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
  },

  async setUserRole(userId: string, role: UserRole): Promise<void> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/users/${userId}/set-role`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ role }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
  },

  async adminUpdateUserNickname(userId: string, nickname: string): Promise<void> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/users/${userId}/update-nickname`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ nickname }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
  },

  async setUserLimits(userId: string, daily_limit: number | null, weekly_limit: number | null, monthly_limit: number | null): Promise<void> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/users/${userId}/limits`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ daily_limit, weekly_limit, monthly_limit }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
  },

  // Registration has been disabled
  // Uncomment below to re-enable registration
  // async register(username: string, password: string, email?: string): Promise<{ user: User; token: string }> {
  //   const res = await fetch(`${API_BASE}/api/auth/register`, {
  //     method: 'POST',
  //     headers: { 'Content-Type': 'application/json' },
  //     body: JSON.stringify({ username, password, email }),
  //   });
  //   const data = await res.json();
  //   if (!data.success) throw new Error(data.error);
  //   this.setAuth(data.data.token, data.data.user);
  //   return data.data;
  // },

  async login(username: string, password: string): Promise<LoginResult> {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    if (isAuthSuccess(data.data)) {
      this.setAuth(data.data.token, data.data.user);
    }
    return data.data;
  },

  async verifyTotp(challengeToken: string, code: string): Promise<AuthSuccess> {
    const res = await fetch(`${API_BASE}/api/auth/verify-totp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ challengeToken, code }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    this.setAuth(data.data.token, data.data.user);
    return data.data;
  },

  async confirmTotpSetup(challengeToken: string, code: string): Promise<AuthSuccess> {
    const res = await fetch(`${API_BASE}/api/auth/setup-totp/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ challengeToken, code }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    this.setAuth(data.data.token, data.data.user);
    return data.data;
  },

  async getLarkConfig(): Promise<{ appId: string }> {
    const res = await fetch(`${API_BASE}/api/auth/lark-config`);
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    return data.data;
  },

  async loginWithLark(code: string): Promise<LoginResult> {
    const res = await fetch(`${API_BASE}/api/auth/lark-login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    if (isAuthSuccess(data.data)) {
      this.setAuth(data.data.token, data.data.user);
    }
    return data.data;
  },

  async getMyUsage(): Promise<{ usage: { daily_cost: number, weekly_cost: number, monthly_cost: number }, limits: { daily: number | null, weekly: number | null, monthly: number | null } }> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/my-usage`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
    const rawText = await res.text();
    let data: any;
    try {
      data = rawText ? JSON.parse(rawText) : null;
    } catch (error) {
      throw new Error('用量数据返回不完整，请稍后重试');
    }
    if (!res.ok) throw new Error(data?.error || '获取用量失败');
    if (!data.success) throw new Error(data.error);
    return data.data;
  },

  async getMyUsageDetails(params: { page?: number; page_size?: number; generation_type?: string } = {}): Promise<any> {
    const token = this.getToken();
    const query = new URLSearchParams();
    if (params.page) query.set('page', String(params.page));
    if (params.page_size) query.set('page_size', String(params.page_size));
    if (params.generation_type) query.set('generation_type', params.generation_type);
    const res = await fetch(`${API_BASE}/api/auth/my-usage/details?${query}`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    return data.data;
  },

  async verify(): Promise<User | null> {
    const token = this.getToken();
    if (!token) return null;
    try {
      const res = await fetch(`${API_BASE}/api/auth/verify`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!data.success) {
        this.clearAuth();
        return null;
      }
      // 同步更新 localStorage 中的用户数据（包含最新的 role）
      const user = data.data.user;
      this.setAuth(token, user);
      return user;
    } catch {
      return null;
    }
  },

  logout(): void {
    this.clearAuth();
  },

  getUserId(): string | null {
    const user = this.getUser();
    return user?._id || null;
  },

  async getLeaderboard(period: 'daily' | 'weekly' | 'monthly' = 'daily'): Promise<{
    leaderboard: { rank: number; user_id: string; username: string; nickname: string; cost: number; calls: number }[];
    period: string;
  }> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/usage/leaderboard?period=${period}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    return data;
  },

  async getSystemStatus(): Promise<{
    config: {
      system_daily_limit: number | null;
      system_weekly_limit: number | null;
      system_monthly_limit: number | null;
      video_generation_config?: any;
      daily_inspiration_config?: any;
    };
    usage: { daily_cost: number; weekly_cost: number; monthly_cost: number };
  }> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/usage/system-status`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    return data;
  },

  async getSystemConfig(): Promise<{
    config: {
      system_daily_limit: number | null;
      system_weekly_limit: number | null;
      system_monthly_limit: number | null;
      video_generation_config?: any;
      daily_inspiration_config?: any;
      updated_at?: string;
      updated_by?: string;
    };
    usage: { daily_cost: number; weekly_cost: number; monthly_cost: number };
  }> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/admin/usage-stats/system-config`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return readCanvasModelApiResponse(res);
  },

  async updateSystemConfig(config: { daily_limit: number | null; weekly_limit: number | null; monthly_limit: number | null; video_generation_config?: any; daily_inspiration_config?: any }): Promise<void> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/admin/usage-stats/system-config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(config),
    });
    await readCanvasModelApiResponse(res);
  },

  // ─── Role Permissions ──────────────────────────────────────────────────────

  async getRolePermissions(): Promise<RolePermissions> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/role-permissions`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    return data.data;
  },

  async updateRolePermissions(role: string, allowed_pages: string[]): Promise<void> {
    const token = this.getToken();
    const res = await fetch(`${API_BASE}/api/auth/role-permissions`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ role, allowed_pages }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
  },
};

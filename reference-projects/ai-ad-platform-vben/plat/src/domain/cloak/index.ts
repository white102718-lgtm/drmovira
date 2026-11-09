import { HttpCloakAdapter } from './adapters/http';
import { CloakService } from './service';

export type { CloakAdapter } from './adapter';
export { HttpCloakAdapter } from './adapters/http';
export { CloakService } from './service';
export type * from './types';

export const cloakService = new CloakService(new HttpCloakAdapter());

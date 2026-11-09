import type {
  ApplicationFormSchema,
  ApplicationType,
  ResourceApplication,
  ResourceApplicationSeed,
} from './types';

/**
 * The legacy Store keeps ownership of local persistence. This adapter only
 * normalizes old payload shapes at that boundary, so a future HTTP adapter can
 * replace it without changing the application or approval pages.
 */
export interface ApplicationAdapter {
  normalize(application: ResourceApplicationSeed): ResourceApplication;
}

/** Read boundary for application-type fields during the compatibility phase. */
export interface ApplicationFormSchemaAdapter {
  getFormSchema(type: ApplicationType): ApplicationFormSchema;
}

/**
 * Write facade over the legacy Pinia Store. The Store keeps ownership of its
 * raw localStorage key; ApplicationService only coordinates business actions.
 */
export interface ApplicationPersistenceAdapter extends ApplicationAdapter {
  list(): readonly ResourceApplication[];
  remove(applicationId: string): void;
  upsert(application: ResourceApplication): ResourceApplication;
}

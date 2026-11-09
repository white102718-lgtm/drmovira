import { HttpMaterialInboundAdapter } from './adapters/http';
import { MaterialInboundService } from './inbound-service';

export * from './adapter';
export * from './adapters/atomic-http';
export * from './adapters/folder-http';
export * from './adapters/http';
export * from './adapters/library-http';
export * from './adapters/selection-demo';
export * from './adapters/selection-http';
export * from './folder-http-service';
export * from './inbound-service';
export * from './library-service';
export * from './selection-service';
export * from './types';

export const materialInboundService = new MaterialInboundService(
  new HttpMaterialInboundAdapter(),
);

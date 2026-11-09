/**
 * Ephemeral canvas inputs delivered with a director-desk host session.
 *
 * This is intentionally separate from DirectorProject: it is source material
 * for human decisions and AI assists, not mutable 3D scene state.
 */
export type HostDirectorContextKind =
  | 'brief'
  | 'storyboard'
  | 'character'
  | 'scene'
  | 'reference-image'
  | 'camera-direction';

export interface HostDirectorContextItem {
  id: string;
  kind: HostDirectorContextKind;
  title: string;
  description?: string;
  imageUrl?: string;
  fields?: Array<{ label: string; value: string }>;
}

export interface HostDirectorContext {
  version: 1;
  generatedAt: string;
  sourceNodeIds: string[];
  briefs: HostDirectorContextItem[];
  storyboards: HostDirectorContextItem[];
  characters: HostDirectorContextItem[];
  scenes: HostDirectorContextItem[];
  referenceImages: HostDirectorContextItem[];
  cameraDirections: HostDirectorContextItem[];
}

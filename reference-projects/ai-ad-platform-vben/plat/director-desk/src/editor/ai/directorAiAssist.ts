import type { CameraShotSnapshot } from '../store/directorStore';
import type { DirectorProject, GeometryPrimitiveType } from '../schema/directorProject';
import type { HostDirectorContext } from '../schema/hostContext';

export interface DirectorCameraCandidate {
  id: string;
  title: string;
  description: string;
  snapshot: CameraShotSnapshot;
}

export interface DirectorAutoLayoutDraft {
  description: string;
  backgroundColor: string;
  charactersToAdd: number;
  geometry: GeometryPrimitiveType[];
}

function allContextText(context: HostDirectorContext) {
  return [
    ...context.briefs,
    ...context.storyboards,
    ...context.characters,
    ...context.scenes,
    ...context.referenceImages,
    ...context.cameraDirections,
  ]
    .flatMap((item) => [item.title, item.description, ...(item.fields || []).map((field) => `${field.label} ${field.value}`)])
    .filter((item): item is string => Boolean(item))
    .join(' ')
    .toLowerCase();
}

function getColorForBrief(text: string) {
  if (/(夜|夜景|neon|霓虹|赛博|cyber)/.test(text)) return '#101828';
  if (/(自然|森林|户外|草地|nature|forest)/.test(text)) return '#1b2a22';
  if (/(暖|日落|黄昏|sunset|golden)/.test(text)) return '#2d1d18';
  return '#E8EEF6';
}

function getDirectionTitle(
  context: HostDirectorContext,
  index: number,
  fallback: string,
) {
  return context.cameraDirections[index]?.title || fallback;
}

/**
 * Local, explainable fallback for the future model endpoint. It turns the
 * structured canvas context into safe, reviewable proposals; it never mutates
 * the scene until a user explicitly applies a proposal.
 */
export function createDirectorAiAssistDraft(
  context: HostDirectorContext,
  project: DirectorProject,
): { layout: DirectorAutoLayoutDraft; cameras: DirectorCameraCandidate[] } {
  const text = allContextText(context);
  const desiredCharacters = Math.min(Math.max(context.characters.length, 1), 3);
  const charactersToAdd = Math.max(
    0,
    desiredCharacters - project.objects.filter((item) => item.kind === 'character').length,
  );
  const geometry: GeometryPrimitiveType[] = context.scenes.length || context.referenceImages.length
    ? ['box', 'cylinder', 'torus']
    : ['box'];
  const target: [number, number, number] = [0, 1.2, 0];

  return {
    layout: {
      description: `根据 ${context.sourceNodeIds.length} 个画布上游节点生成：保留主体活动区，并补足基础前景、中景和背景层次。`,
      backgroundColor: getColorForBrief(text),
      charactersToAdd,
      geometry,
    },
    cameras: [
      {
        id: 'establishing',
        title: getDirectionTitle(context, 0, '建立镜头'),
        description: '广角交代环境、角色位置与主要布景关系。',
        snapshot: { fov: 35, position: [0, 3.2, 10], target },
      },
      {
        id: 'subject',
        title: getDirectionTitle(context, 1, '主体中景'),
        description: '中焦突出主角与关键道具，便于承接分镜动作。',
        snapshot: { fov: 50, position: [4.6, 2.1, 5.4], target },
      },
      {
        id: 'impact',
        title: getDirectionTitle(context, 2, '低机位动势镜头'),
        description: '较低视角与广角透视增强人物或产品的力量感。',
        snapshot: { fov: 28, position: [-2.8, 1, 4.6], target },
      },
    ],
  };
}

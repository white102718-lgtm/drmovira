import { NodeStatus, NodeType, type NodeData, type NodeGroup } from './types';

export type DirectorDeskContextKind =
  | 'brief'
  | 'storyboard'
  | 'character'
  | 'scene'
  | 'reference-image'
  | 'camera-direction';

export interface DirectorDeskContextItem {
  id: string;
  kind: DirectorDeskContextKind;
  title: string;
  description?: string;
  imageUrl?: string;
  fields?: Array<{ label: string; value: string }>;
}

/**
 * A compact, serializable view of the canvas inputs that affect a director
 * node. It deliberately carries source ids so AI results can later be traced
 * back to the canvas rather than becoming anonymous prompt text.
 */
export interface DirectorDeskContext {
  version: 1;
  generatedAt: string;
  sourceNodeIds: string[];
  briefs: DirectorDeskContextItem[];
  storyboards: DirectorDeskContextItem[];
  characters: DirectorDeskContextItem[];
  scenes: DirectorDeskContextItem[];
  referenceImages: DirectorDeskContextItem[];
  cameraDirections: DirectorDeskContextItem[];
}

function cleanText(value: unknown) {
  return typeof value === 'string' ? value.trim() : '';
}

function uniqueItems(items: DirectorDeskContextItem[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.kind}:${item.id}:${item.imageUrl || ''}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function makeNodeItem(
  node: NodeData,
  kind: DirectorDeskContextKind,
): DirectorDeskContextItem {
  return {
    id: node.id,
    kind,
    title: cleanText(node.title) || node.type,
    description: cleanText(node.prompt) || undefined,
    imageUrl: node.resultUrl,
    fields: node.businessFields?.filter(
      (field) => cleanText(field.label) && cleanText(field.value),
    ),
  };
}

function collectUpstreamNodes(nodes: NodeData[], directorNode: NodeData) {
  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const visited = new Set<string>();
  const stack = [...(directorNode.parentIds || [])];

  while (stack.length > 0) {
    const nodeId = stack.pop();
    if (!nodeId || visited.has(nodeId)) continue;
    visited.add(nodeId);
    const node = nodesById.get(nodeId);
    node?.parentIds?.forEach((parentId) => stack.push(parentId));
  }

  return nodes.filter((node) => visited.has(node.id));
}

function getStoryContextItems(groups: NodeGroup[], upstreamIds: Set<string>) {
  const storyboards: DirectorDeskContextItem[] = [];
  const characters: DirectorDeskContextItem[] = [];
  const scenes: DirectorDeskContextItem[] = [];

  groups.forEach((group) => {
    if (!group.nodeIds.some((nodeId) => upstreamIds.has(nodeId))) return;
    const context = group.storyContext;
    if (!context) return;

    const story = cleanText(context.story);
    if (story) {
      storyboards.push({
        id: `group:${group.id}`,
        kind: 'storyboard',
        title: group.label || '分镜故事',
        description: story,
      });
    }

    (context.selectedCharacters || []).forEach((character, index) => {
      const candidate = character as Record<string, unknown>;
      const title =
        cleanText(candidate.name) ||
        cleanText(candidate.title) ||
        `角色参考 ${index + 1}`;
      const description =
        cleanText(candidate.description) || cleanText(candidate.prompt);
      const imageUrl =
        cleanText(candidate.imageUrl) || cleanText(candidate.url) || undefined;
      characters.push({
        id: `group:${group.id}:character:${index}`,
        kind: 'character',
        title,
        description: description || undefined,
        imageUrl,
      });
    });

    (context.scripts || []).forEach((script, index) => {
      const candidate = script as Record<string, unknown>;
      const description = [
        cleanText(candidate.scene),
        cleanText(candidate.sceneDescription),
        cleanText(candidate.action),
        cleanText(candidate.visual),
      ]
        .filter(Boolean)
        .join('；');
      if (!description) return;
      scenes.push({
        id: `group:${group.id}:scene:${index}`,
        kind: 'scene',
        title: cleanText(candidate.title) || `场景 ${index + 1}`,
        description,
      });
    });
  });

  return { storyboards, characters, scenes };
}

export function buildDirectorDeskContext(
  nodes: NodeData[],
  groups: NodeGroup[],
  directorNode: NodeData,
  generatedAt = new Date().toISOString(),
): DirectorDeskContext {
  const upstream = collectUpstreamNodes(nodes, directorNode);
  const upstreamIds = new Set(upstream.map((node) => node.id));
  const fromGroups = getStoryContextItems(groups, upstreamIds);
  const briefs: DirectorDeskContextItem[] = [];
  const storyboards = [...fromGroups.storyboards];
  const characters = [...fromGroups.characters];
  const scenes = [...fromGroups.scenes];
  const referenceImages: DirectorDeskContextItem[] = [];
  const cameraDirections: DirectorDeskContextItem[] = [];

  upstream.forEach((node) => {
    if (node.type === NodeType.STORYBOARD) {
      storyboards.push(makeNodeItem(node, 'storyboard'));
      return;
    }
    if (node.type === NodeType.CAMERA_ANGLE) {
      cameraDirections.push(makeNodeItem(node, 'camera-direction'));
      return;
    }
    if (node.type === NodeType.IMAGE || node.type === NodeType.REFERENCE) {
      if (node.resultUrl) {
        referenceImages.push(makeNodeItem(node, 'reference-image'));
      }
      (node.characterReferenceUrls || []).forEach((imageUrl, index) => {
        if (!cleanText(imageUrl)) return;
        characters.push({
          id: `${node.id}:character-reference:${index}`,
          kind: 'character',
          title: `${node.title || '分镜'} · 角色参考 ${index + 1}`,
          imageUrl,
        });
      });
      return;
    }
    if (
      [
        NodeType.PROJECT,
        NodeType.PRODUCT,
        NodeType.KPI,
        NodeType.REQUIREMENT,
        NodeType.BRAND_GUIDELINE,
        NodeType.TEXT,
      ].includes(node.type)
    ) {
      briefs.push(makeNodeItem(node, 'brief'));
    }
  });

  return {
    version: 1,
    generatedAt,
    sourceNodeIds: upstream.map((node) => node.id),
    briefs: uniqueItems(briefs),
    storyboards: uniqueItems(storyboards),
    characters: uniqueItems(characters),
    scenes: uniqueItems(scenes),
    referenceImages: uniqueItems(referenceImages),
    cameraDirections: uniqueItems(cameraDirections),
  };
}

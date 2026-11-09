/**
 * useWorkflow.ts
 * 
 * Custom hook for managing workflow save/load functionality.
 * Handles persistence to the backend server.
 */

import React, { useState, useCallback, useEffect, type Dispatch, type SetStateAction } from 'react';
import type { NodeData, NodeGroup, Viewport } from '../types';
import {
    apiFetch,
    getRuntime,
    notifySaveState,
    workflowStorageKey
} from '../runtime';

interface WorkflowData {
    id: string | null;
    title: string;
    nodes: NodeData[];
    groups: NodeGroup[];
    viewport: Viewport;
}

interface UseWorkflowOptions {
    initialWorkflowId?: string;
    nodes: NodeData[];
    groups: NodeGroup[];
    viewport: Viewport;
    canvasTitle: string;
    setNodes: Dispatch<SetStateAction<NodeData[]>>;
    setGroups: Dispatch<SetStateAction<NodeGroup[]>>; // For restoring groups when loading
    setSelectedNodeIds: Dispatch<SetStateAction<string[]>>;
    setCanvasTitle: (title: string) => void;
    setEditingTitleValue: (value: string) => void;
    onPanelOpen?: () => void; // Called when workflow panel opens
}

export const useWorkflow = ({
    initialWorkflowId,
    nodes,
    groups,
    viewport,
    canvasTitle,
    setNodes,
    setGroups,
    setSelectedNodeIds,
    setCanvasTitle,
    setEditingTitleValue,
    onPanelOpen
}: UseWorkflowOptions) => {
    // Workflow state
    const [workflowId, setWorkflowId] = useState<string | null>(initialWorkflowId || null);
    const [isWorkflowPanelOpen, setIsWorkflowPanelOpen] = useState(false);
    const [workflowPanelY, setWorkflowPanelY] = useState(0);

    /**
     * Save current workflow to server
     */
    const handleSaveWorkflow = useCallback(async () => {
        notifySaveState('saving');
        try {
            const resolvedId = workflowId || initialWorkflowId || `canvas-${Date.now()}`;
            const workflow: WorkflowData = {
                id: resolvedId,
                title: canvasTitle,
                nodes,
                groups,
                viewport
            };

            localStorage.setItem(
                workflowStorageKey(resolvedId),
                JSON.stringify({ ...workflow, savedAt: new Date().toISOString() })
            );
            setWorkflowId(resolvedId);

            if (getRuntime().apiBase) {
                const response = await apiFetch('/api/workflows', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(workflow)
                });
                if (!response.ok) throw new Error(`保存接口返回 ${response.status}`);
            }
            notifySaveState('saved');
        } catch (error) {
            console.error('Failed to save workflow:', error);
            notifySaveState('failed');
            throw error;
        }
    }, [workflowId, initialWorkflowId, canvasTitle, nodes, groups, viewport]);

    /**
     * Load workflow from server
     * Supports both user workflows and public workflows (prefixed with "public:")
     * Returns the loaded workflow's node count and title for tracking
     */
    const handleLoadWorkflow = useCallback(async (id: string): Promise<{ nodeCount: number; title: string } | null> => {
        try {
            // Check if loading a public workflow
            const isPublic = id.startsWith('public:');
            const normalizedId = isPublic ? id.replace('public:', '') : id;
            let workflow: WorkflowData | undefined;

            if (!isPublic) {
                const local = localStorage.getItem(workflowStorageKey(normalizedId));
                if (local) workflow = JSON.parse(local) as WorkflowData;
            }

            if (!workflow && getRuntime().apiBase) {
                const endpoint = isPublic
                    ? `/api/public-workflows/${normalizedId}`
                    : `/api/workflows/${normalizedId}`;
                const response = await apiFetch(endpoint);
                if (response.ok) workflow = await response.json();
            }

            if (workflow) {

                // For public workflows, don't set the workflowId so it saves as a new workflow
                if (!isPublic) {
                    setWorkflowId(workflow.id);
                } else {
                    setWorkflowId(null); // New copy, not linked to public workflow
                }

                setCanvasTitle(workflow.title || 'Untitled');
                setEditingTitleValue(workflow.title || 'Untitled');
                setNodes(workflow.nodes || []);
                setGroups(workflow.groups || []); // Restore groups
                // Reset selection
                setSelectedNodeIds([]);
                setIsWorkflowPanelOpen(false);
                console.log(isPublic ? 'Public workflow loaded:' : 'Workflow loaded:', normalizedId);
                // Return info for tracking
                return {
                    nodeCount: (workflow.nodes || []).length,
                    title: workflow.title || 'Untitled'
                };
            }
        } catch (error) {
            console.error('Failed to load workflow:', error);
        }
        return null;
    }, [setNodes, setGroups, setSelectedNodeIds, setCanvasTitle, setEditingTitleValue]);

    useEffect(() => {
        if (initialWorkflowId) void handleLoadWorkflow(initialWorkflowId);
    }, [handleLoadWorkflow, initialWorkflowId]);

    /**
     * Handle workflow panel toggle from toolbar click
     */
    const handleWorkflowsClick = useCallback((e: React.MouseEvent) => {
        const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
        setWorkflowPanelY(rect.top - getRuntime().container.getBoundingClientRect().top);
        setIsWorkflowPanelOpen(prev => !prev);
        onPanelOpen?.(); // Close other panels
    }, [onPanelOpen]);

    /**
     * Close workflow panel
     */
    const closeWorkflowPanel = useCallback(() => {
        setIsWorkflowPanelOpen(false);
    }, []);

    /**
     * Reset workflow ID (for creating a new canvas)
     */
    const resetWorkflowId = useCallback(() => {
        setWorkflowId(null);
    }, []);

    return {
        workflowId,
        isWorkflowPanelOpen,
        workflowPanelY,
        handleSaveWorkflow,
        handleLoadWorkflow,
        handleWorkflowsClick,
        closeWorkflowPanel,
        resetWorkflowId
    };
};

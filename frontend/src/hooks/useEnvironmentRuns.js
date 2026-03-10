import { useState, useMemo, useCallback } from 'react';
import { normalizeLogEntries, mergeRunLogs } from '../utils/logUtils';

export const useEnvironmentRuns = (setActiveRunId) => {
    const [environmentRunTabs, setEnvironmentRunTabs] = useState({});

    const environmentRunTabEntries = useMemo(
        () => Object.values(environmentRunTabs).sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0)),
        [environmentRunTabs],
    );

    const handleEnvironmentRunStateChange = useCallback((nextState) => {
        if (!nextState || typeof nextState !== 'object' || !nextState.runId) {
            return;
        }

        const { runId } = nextState;
        let shouldActivateNewTab = false;

        setEnvironmentRunTabs((prev) => {
            const currentCount = Object.keys(prev).length;
            const existing = prev[runId];

            if (!existing) {
                shouldActivateNewTab = true;
            }

            const incomingSnapshotLogs = normalizeLogEntries(nextState.logs);
            const incomingAppendLogs = normalizeLogEntries(nextState.appendLogs);
            const mergedLogs = mergeRunLogs({
                existingLogs: existing?.logs || [],
                snapshotLogs: incomingSnapshotLogs,
                appendLogs: incomingAppendLogs,
            });

            const taskName = typeof nextState.taskName === 'string' && nextState.taskName.trim()
                ? nextState.taskName.trim()
                : (existing?.taskName || '');

            const status = nextState.status ?? existing?.status ?? null;

            return {
                ...prev,
                [runId]: {
                    id: runId,
                    createdAt: existing?.createdAt || Date.now(),
                    taskName,
                    label: taskName || existing?.label || `Environment Run ${currentCount + (existing ? 0 : 1)}`,
                    description: typeof status === 'string' && status.trim()
                        ? status.trim().toUpperCase()
                        : undefined,
                    status,
                    isRunning: typeof nextState.isRunning === 'boolean'
                        ? nextState.isRunning
                        : Boolean(existing?.isRunning),
                    logs: mergedLogs,
                    error: nextState.error !== undefined ? nextState.error : (existing?.error || null),
                },
            };
        });

        if (shouldActivateNewTab) {
            setActiveRunId(runId);
        }
    }, [setActiveRunId]);

    const removeEnvironmentRun = useCallback((id) => {
         setEnvironmentRunTabs((prev) => {
            if (!prev[id]) {
                return prev;
            }

            const next = { ...prev };
            delete next[id];
            return next;
        });
    }, []);

    return {
        environmentRunTabs,
        environmentRunTabEntries,
        handleEnvironmentRunStateChange,
        removeEnvironmentRun
    };
};

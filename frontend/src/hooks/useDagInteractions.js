import { useState, useRef, useCallback } from 'react';
import { 
    DAG_FOCUS_EVENT_TYPES, 
    DAG_EVENT_MIN_INTERVAL_BY_TYPE, 
    normalizeDAGInteractionForExport, 
    buildDAGInteractionSummary 
} from '../utils/dagUtils';

export const useDagInteractions = (activeRunId) => {
    const [dagInteractions, setDagInteractions] = useState([]);
    const dagInteractionCounterRef = useRef(0);
    const dagInteractionLastRecordedAtRef = useRef(new Map());
    const dagZoomScaleByRunRef = useRef(new Map());

    const handleDAGInteraction = useCallback((interaction) => {
        if (!interaction || typeof interaction !== 'object') {
            return;
        }

        const type = typeof interaction.type === 'string' ? interaction.type : 'unknown';
        if (!DAG_FOCUS_EVENT_TYPES.has(type)) {
            return;
        }

        const runKey = activeRunId || 'global';
        const now = Date.now();
        const throttleKey = `${runKey}::${type}`;
        const minInterval = DAG_EVENT_MIN_INTERVAL_BY_TYPE[type] || 0;
        const lastRecordedAt = dagInteractionLastRecordedAtRef.current.get(throttleKey) || 0;
        if (minInterval > 0 && now - lastRecordedAt < minInterval) {
            return;
        }

        dagInteractionLastRecordedAtRef.current.set(throttleKey, now);

        const normalizedPayload = normalizeDAGInteractionForExport(interaction, {
            runKey,
            zoomScaleByRunRef: dagZoomScaleByRunRef,
        });
        if (!normalizedPayload) {
            return;
        }

        dagInteractionCounterRef.current += 1;
        const normalizedInteraction = {
            sequence: dagInteractionCounterRef.current,
            recordedAt: new Date(now).toISOString(),
            runId: activeRunId || null,
            ...normalizedPayload,
        };

        setDagInteractions((prev) => [...prev, normalizedInteraction]);
    }, [activeRunId]);

    const handleExportDAGInteractions = useCallback(() => {
        if (!dagInteractions.length) {
            alert('No DAG interaction data to export.');
            return;
        }

        const timestamp = new Date();
        const summary = buildDAGInteractionSummary(dagInteractions);
        const payload = {
            exportVersion: 'dag_interactions_focused_v2',
            granularity: 'focused',
            exportedAt: timestamp.toISOString(),
            count: dagInteractions.length,
            summary,
            samplingPolicy: {
                focusEventTypes: Array.from(DAG_FOCUS_EVENT_TYPES),
                minIntervalMsByType: DAG_EVENT_MIN_INTERVAL_BY_TYPE,
            },
            interactions: dagInteractions,
        };
        const fileName = `dag_interactions_${timestamp.toISOString().replace(/[:.]/g, '-')}.json`;

        let objectUrl = null;
        try {
            const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
            objectUrl = URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = objectUrl;
            anchor.download = fileName;
            document.body.appendChild(anchor);
            anchor.click();
            document.body.removeChild(anchor);

            setDagInteractions([]);
            dagInteractionCounterRef.current = 0;
            dagInteractionLastRecordedAtRef.current.clear();
            dagZoomScaleByRunRef.current.clear();
            alert(`Exported ${payload.count} focused DAG interactions.`);
        } catch (error) {
            alert(`Failed to export DAG interactions: ${error?.message || 'unknown error'}`);
        } finally {
            if (objectUrl) {
                URL.revokeObjectURL(objectUrl);
            }
        }
    }, [dagInteractions]);

    return {
        dagInteractions,
        handleDAGInteraction,
        handleExportDAGInteractions
    };
};

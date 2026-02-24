import React, { useRef, useState } from 'react';
import { runBrowserAgent, stopBrowserAgentRun, getBrowserAgentStatus } from '../../services/api';

const createBrowserAgentRunId = () => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID();
    }
    return `run_${Date.now()}_${Math.random().toString(16).slice(2)}`;
};

const TestAutoBuy = ({ onAddRun }) => {
    const timerRef = useRef(null);
    const runIdRef = useRef(null);
    const abortRef = useRef(null);
    const [isWaiting, setIsWaiting] = useState(false);
    const [waitSeconds, setWaitSeconds] = useState(0);

    const handleTest = async () => {
        if (isWaiting) {
            const activeRunId = runIdRef.current;
            if (timerRef.current) {
                window.clearInterval(timerRef.current);
                timerRef.current = null;
            }
            if (abortRef.current) {
                abortRef.current.abort();
                abortRef.current = null;
            }
            if (activeRunId) {
                try {
                    await stopBrowserAgentRun(activeRunId);
                } catch (error) {
                    console.warn('TestAutoBuy stop request failed:', error);
                }
            }
            runIdRef.current = null;
            setIsWaiting(false);
            return;
        }

        const runId = createBrowserAgentRunId();
        const abortController = new AbortController();
        runIdRef.current = runId;
        abortRef.current = abortController;

        const payload = {
            task: {
                name: 'Find me a ticket from New York to San Francisco next week(you don\'t need to actually buy it, just find the best option and tell me the details)',
                url: 'https://www.google.com/travel/flights?gl=US&hl=en-US'
            },
            model: ['deepseek-chat'],
            persona: [
                { value: 'frugal', content: 'Tell me in the most frugal way' },
            ],
            run_times: 1,
            run_id: runId,
        };

        try {
            setIsWaiting(true);
            setWaitSeconds(0);
            timerRef.current = window.setInterval(() => {
                setWaitSeconds((prev) => prev + 1);
            }, 1000);

            console.log('TestAutoBuy sending payload:', payload);
            const response = await runBrowserAgent(payload, {
                signal: abortController.signal,
                headers: {
                    'X-Browser-Agent-Run-Id': runId,
                },
            });

            if (!response.ok) {
                const detail = response.status === 409
                    ? 'Another run is in progress.'
                    : 'Failed to start run.';
                console.error('TestAutoBuy start failed:', detail);
                alert(detail);
                return;
            }

            // Poll for results
            const POLL_INTERVAL_MS = 3000;
            let pollActive = true;

            while (pollActive && !abortController.signal.aborted) {
                await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
                if (abortController.signal.aborted) break;

                try {
                    const statusResponse = await getBrowserAgentStatus(runId);
                    if (!statusResponse.ok) continue;

                    const data = statusResponse.data;
                    if (data.status === 'completed') {
                        pollActive = false;
                        if (data.results && onAddRun) {
                            console.log('TestAutoBuy calling onAddRun with:', data.results);
                            onAddRun({ results: data.results });
                        }
                    } else if (data.status === 'failed' || data.status === 'cancelled') {
                        pollActive = false;
                        console.error('TestAutoBuy run ended:', data.error);
                        alert(`Run ${data.status}: ${data.error || 'Unknown error'}`);
                    }
                } catch (pollError) {
                    if (pollError?.name === 'AbortError') break;
                    console.warn('TestAutoBuy poll error:', pollError);
                }
            }
        } catch (error) {
            if (error?.name === 'AbortError') {
                return;
            }
            console.error('TestAutoBuy error:', error);
            alert('TestAutoBuy error. Check console.');
        } finally {
            if (timerRef.current) {
                window.clearInterval(timerRef.current);
                timerRef.current = null;
            }
            abortRef.current = null;
            runIdRef.current = null;
            setIsWaiting(false);
        }
    };

    return (
        <button 
            type="button" 
            onClick={handleTest} 
            className="panel__action"
            style={{ 
                backgroundColor: '#ef4444', 
                color: 'white',
                border: 'none',
                marginLeft: '8px'
            }}
        >
            {isWaiting ? `Stop Test (${waitSeconds}s)` : 'Test: Find Flight'}
        </button>
    );
};

export default TestAutoBuy;

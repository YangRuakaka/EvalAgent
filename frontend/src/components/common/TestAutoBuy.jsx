import React, { useRef, useState } from 'react';
import { runBrowserAgent } from '../../services/api';

const TestAutoBuy = ({ onAddRun }) => {
    const timerRef = useRef(null);
    const [isWaiting, setIsWaiting] = useState(false);
    const [waitSeconds, setWaitSeconds] = useState(0);

    const handleTest = async () => {
        const payload = {
            task: {
                name: 'Find me a ticket from New York to San Francisco next week(you don\'t need to actually buy it, just find the best option and tell me the details)',
                url: 'https://www.google.com/travel/flights?gl=US&hl=en-US'
            },
            model: ['deepseek-chat'],
            persona: [
                { value: 'frugal', content: 'Tell me in the most frugal way' },
                { value: 'efficiency', content: 'Tell me in the most efficient way' },
            ],
            run_times: 1
        };

        try {
            setIsWaiting(true);
            setWaitSeconds(0);
            timerRef.current = window.setInterval(() => {
                setWaitSeconds((prev) => prev + 1);
            }, 1000);

            console.log('TestAutoBuy sending payload:', payload);
            const response = await runBrowserAgent(payload, {
                onRetry: ({ attempt, error }) => {
                    console.warn('[TestAutoBuy] retrying browser-agent request', { attempt, error });
                },
            });
            if (response.ok && response.data && response.data.results) {
                if (onAddRun) {
                    console.log('TestAutoBuy calling onAddRun with:', response.data.results);
                    onAddRun({ results: response.data.results });
                }
            } else {
                console.error('TestAutoBuy failed:', response);
                alert('TestAutoBuy failed. Check console.');
            }
        } catch (error) {
            console.error('TestAutoBuy error:', error);
            alert('TestAutoBuy error. Check console.');
        } finally {
            if (timerRef.current) {
                window.clearInterval(timerRef.current);
                timerRef.current = null;
            }
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
            {isWaiting ? `Waiting Backend ${waitSeconds}s` : 'Test: Find Flight'}
        </button>
    );
};

export default TestAutoBuy;

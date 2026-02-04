import React from 'react';
import { runBrowserAgent } from '../../services/api';

const TestAutoBuy = ({ onAddRun }) => {
    const handleTest = async () => {
        const payload = {
            task: {
                name: 'Tell me who is Yukun Yang',
                url: 'https://yangruakaka.github.io/Yukun_Yang/'
            },
            model: ['deepseek-chat'],
            persona: [
                { value: 'frugal', content: 'Tell me in the most frugal way' },
                { value: 'efficiency', content: 'Tell me in the most efficient way' },
            ],
            run_times: 1
        };

        try {
            console.log('TestAutoBuy sending payload:', payload);
            const response = await runBrowserAgent(payload);
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
            Test: Buy Milk
        </button>
    );
};

export default TestAutoBuy;

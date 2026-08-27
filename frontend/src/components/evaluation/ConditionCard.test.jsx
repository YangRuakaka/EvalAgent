import { render, screen } from '@testing-library/react';
import ConditionCard from './ConditionCard';

jest.mock('react-markdown', () => function MockReactMarkdown({ children }) {
	return children;
});

describe('ConditionCard result rendering', () => {
	test('renders a fenced Markdown final result as formatted content', () => {
		const { container } = render(
			<ConditionCard
				condition={{
					id: 'condition-1',
					raw: {
						final_result: '```markdown\n# Completed\n\n- first item\n- second item\n```',
					},
				}}
			/>,
		);

		expect(container.querySelector('.condition-card__result-content').textContent).toContain('# Completed');
		expect(container.querySelector('.condition-card__result-content').textContent).toContain('- first item');
		expect(screen.queryByText(/```markdown/)).toBeNull();
	});

	test('renders Markdown from a structured result value', () => {
		const { container } = render(
			<ConditionCard
				condition={{
					id: 'condition-2',
					result: { markdown: '**Passed** with [details](https://example.com)' },
				}}
			/>,
		);

		expect(container.querySelector('.condition-card__result-content').textContent).toBe('**Passed** with [details](https://example.com)');
	});
});

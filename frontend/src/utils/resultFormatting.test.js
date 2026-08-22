import { looksLikeMarkdown, normalizeMarkdownText, resultToText } from './resultFormatting';

describe('resultFormatting', () => {
	test('detects and unwraps fenced markdown results', () => {
		const value = '```markdown\n# Result\n\n- one\n- two\n```';
		expect(looksLikeMarkdown(value)).toBe(true);
		expect(normalizeMarkdownText(value)).toBe('# Result\n\n- one\n- two');
	});

	test('leaves plain text as plain text', () => {
		expect(looksLikeMarkdown('Task completed successfully.')).toBe(false);
	});

	test('extracts text from structured result values', () => {
		expect(resultToText({ markdown: '**Done**' })).toBe('**Done**');
	});
});

import { getScreenshotDataUri } from './screenshotUtils';

describe('getScreenshotDataUri', () => {
	test('preserves cached screenshot proxy URLs without file extensions in the endpoint path', () => {
		const url = '/api/v1/history-logs/screenshot?dataset=data1&path=history_logs%2Fscreenshot.png';
		expect(getScreenshotDataUri(url)).toBe(url);
	});

	test('preserves absolute URLs and existing data URIs', () => {
		expect(getScreenshotDataUri('https://example.com/screenshot.png')).toBe('https://example.com/screenshot.png');
		expect(getScreenshotDataUri('data:image/webp;base64,AAAA')).toBe('data:image/webp;base64,AAAA');
	});

	test('converts raw base64 and rejects filesystem paths', () => {
		expect(getScreenshotDataUri('QUJDREVGR0hJSktMTU5PUA==')).toBe('data:image/png;base64,QUJDREVGR0hJSktMTU5PUA==');
		expect(getScreenshotDataUri('history_logs/screenshots/screenshot.png')).toBeNull();
	});
});

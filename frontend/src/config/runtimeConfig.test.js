import {
  API_BASE_URL,
  TARGET_BASE_URL,
  TARGET_URL_OPTIONS,
  WEBHARBOR_HOST,
} from './runtimeConfig';

describe('local WebHarbor runtime configuration', () => {
  test('uses the local WebHarbor host', () => {
    expect(API_BASE_URL).toBe('http://127.0.0.1:8000/api/v1');
    expect(WEBHARBOR_HOST).toBe('http://localhost');
    expect(TARGET_BASE_URL).toBe(WEBHARBOR_HOST);
  });

  test('exposes every local WebHarbor site on its dedicated port', () => {
    expect(TARGET_URL_OPTIONS).toHaveLength(15);
    expect(TARGET_URL_OPTIONS.map((option) => option.port)).toEqual(
      Array.from({ length: 15 }, (_value, index) => 40000 + index),
    );
    expect(TARGET_URL_OPTIONS[0]).toMatchObject({
      id: 'allrecipes',
      value: 'http://localhost:40000',
    });
    expect(TARGET_URL_OPTIONS[14]).toMatchObject({
      id: 'espn',
      value: 'http://localhost:40014',
    });
  });

  test('does not expose legacy Web Static Environment routes', () => {
    const serialized = JSON.stringify(TARGET_URL_OPTIONS).toLowerCase();
    expect(serialized).not.toContain('riverbuy');
    expect(serialized).not.toContain('zoomcar');
    expect(serialized).not.toContain('dwellio');
    expect(serialized).not.toContain(':3000/');
  });
});

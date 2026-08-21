import {
	computeSuffixPrefixOverlap,
	mergeRunLogs,
	normalizeLogEntries,
} from './logUtils';

test('normalizes non-string log entries and removes blanks', () => {
	expect(normalizeLogEntries([' first ', null, 42, ''])).toEqual(['first', '42']);
});

test('finds the overlap between a snapshot and existing logs', () => {
	expect(computeSuffixPrefixOverlap(['a', 'b', 'c'], ['b', 'c', 'd'])).toBe(2);
});

test('merges snapshots and appended logs without duplicates', () => {
	expect(mergeRunLogs({
		existingLogs: ['a', 'b'],
		snapshotLogs: ['a', 'b', 'c'],
		appendLogs: ['c', 'd'],
	})).toEqual(['a', 'b', 'c', 'd']);
});

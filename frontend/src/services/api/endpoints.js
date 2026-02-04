export const API_ENDPOINTS = {
  persona: {
    root: '/persona',
    generate: '/persona/generate',
  },
  personaVariation: {
    root: '/persona-variation',
    generate: '/persona-variation/generate',
  },
  historyLogs: {
    root: '/history-logs',
  },
  browserAgent: {
    run: '/browser-agent/run',
  },
  criteria: {
    root: '/criteria',
    generate: '/criteria/generate',
    create: '/criteria',
    update: (id) => `/criteria/${id}`,
    delete: (id) => `/criteria/${id}`,
  },
  judge: {
    evaluateExperiment: '/judge/evaluate-experiment',
    analyzeGranularity: '/judge/analyze-granularity',
    aggregateSteps: '/judge/aggregate-steps',
  },
};

export default API_ENDPOINTS;

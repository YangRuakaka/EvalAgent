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
    status: '/browser-agent/status',
    events: '/browser-agent/events',
    stop: '/browser-agent/stop',
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
  },
  maintenance: {
    cleanupFiles: '/maintenance/cleanup-files',
    restartService: '/maintenance/restart-service',
  },
};

export default API_ENDPOINTS;

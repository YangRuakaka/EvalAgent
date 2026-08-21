const sanitizeBaseUrl = (value) => {
  if (!value) {
    return '';
  }

  const trimmed = String(value).trim();
  if (!trimmed) {
    return '';
  }

  return trimmed.endsWith('/') ? trimmed.slice(0, -1) : trimmed;
};

const getRuntimeEnvironment = () => {
  const env = process.env.NODE_ENV;
  return env === 'production' ? 'production' : 'development';
};

const resolveBaseUrl = (explicitValue, defaultsByEnv) => {
  const explicit = sanitizeBaseUrl(explicitValue);
  if (explicit) {
    return explicit;
  }

  const runtimeEnv = getRuntimeEnvironment();
  return sanitizeBaseUrl(defaultsByEnv[runtimeEnv]);
};

export const API_BASE_URL = resolveBaseUrl(process.env.REACT_APP_API_BASE_URL, {
  development: 'http://127.0.0.1:8000/api/v1',
  production: 'https://eval-agent-backend-588077581214.us-central1.run.app/api/v1',
});

export const WEBHARBOR_HOST = resolveBaseUrl(
  process.env.REACT_APP_WEBHARBOR_HOST,
  {
    development: 'http://localhost',
    production: 'http://localhost',
  },
);

// Backward-compatible export used by existing configuration components.
export const TARGET_BASE_URL = WEBHARBOR_HOST;

const buildWebHarborUrl = (port) => {
  try {
    const target = new URL(WEBHARBOR_HOST);
    target.port = String(port);
    target.pathname = '/';
    target.search = '';
    target.hash = '';
    return target.toString().replace(/\/$/, '');
  } catch (_error) {
    return `${WEBHARBOR_HOST}:${port}`;
  }
};

const WEBHARBOR_TARGETS = [
  { id: 'allrecipes', port: 40000, label: 'Allrecipes' },
  { id: 'amazon', port: 40001, label: 'Amazon' },
  { id: 'apple', port: 40002, label: 'Apple' },
  { id: 'arxiv', port: 40003, label: 'ArXiv' },
  { id: 'bbc-news', port: 40004, label: 'BBC News' },
  { id: 'booking', port: 40005, label: 'Booking' },
  { id: 'github', port: 40006, label: 'GitHub' },
  { id: 'google-flights', port: 40007, label: 'Google Flights' },
  { id: 'google-maps', port: 40008, label: 'Google Maps' },
  { id: 'google-search', port: 40009, label: 'Google Search' },
  { id: 'hugging-face', port: 40010, label: 'Hugging Face' },
  { id: 'wolfram-alpha', port: 40011, label: 'WolframAlpha' },
  { id: 'cambridge-dictionary', port: 40012, label: 'Cambridge Dictionary' },
  { id: 'coursera', port: 40013, label: 'Coursera' },
  { id: 'espn', port: 40014, label: 'ESPN' },
];

export const TARGET_URL_OPTIONS = WEBHARBOR_TARGETS.map((option) => ({
  ...option,
  value: buildWebHarborUrl(option.port),
}));

const runtimeConfig = {
  API_BASE_URL,
  WEBHARBOR_HOST,
  TARGET_BASE_URL,
  TARGET_URL_OPTIONS,
};

export default runtimeConfig;

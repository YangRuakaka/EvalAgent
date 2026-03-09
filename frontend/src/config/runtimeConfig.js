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

export const TARGET_BASE_URL = resolveBaseUrl(process.env.REACT_APP_TARGET_BASE_URL, {
  development: 'http://localhost:3000',
  production: 'http://34.55.136.249:3000',
});

const TARGET_PATH_OPTIONS = [
  { path: '/riverbuy', label: 'RiverBuy' },
  { path: '/flight', label: 'Flight' },
  { path: '/grumble', label: 'Grumble' },
  { path: '/zoomcar', label: 'Zoomcar' },
  { path: '/stayscape', label: 'StayScape' },
  { path: '/dwellio', label: 'Dwellio' },
];

export const TARGET_URL_OPTIONS = TARGET_PATH_OPTIONS.map((option) => ({
  ...option,
  value: `${TARGET_BASE_URL}${option.path}`,
}));

const runtimeConfig = {
  API_BASE_URL,
  TARGET_BASE_URL,
  TARGET_URL_OPTIONS,
};

export default runtimeConfig;
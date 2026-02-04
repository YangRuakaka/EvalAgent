
const sanitizeBaseUrl = (value) => {
  if (!value) {
    return '';
  }

  if (value.endsWith('/')) {
    return value.slice(0, -1);
  }

  return value;
};

const defaultConfig = {
  baseUrl: sanitizeBaseUrl(process.env.REACT_APP_API_BASE_URL || 'http://127.0.0.1:8000/api/v1/'),
  enableNetwork: true,
};

const buildUrl = (baseUrl, path) => {
  const normalizedBase = sanitizeBaseUrl(baseUrl);
  if (!path.startsWith('/')) {
    return `${normalizedBase}/${path}`;
  }
  return `${normalizedBase}${path}`;
};

const parseResponse = async (response) => {
  const payload = {
    status: response.status,
    ok: response.ok,
    headers: response.headers,
    data: null,
  };

  try {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      payload.data = await response.json();
    } else {
      payload.data = await response.text();
    }
  } catch (error) {
    payload.data = null;
    payload.parseError = error;
  }

  return payload;
};

const mockResponse = (path, method) => {
  return Promise.resolve({
    status: 200,
    ok: true,
    headers: new Headers(),
    data: {
      mocked: true,
      path,
      method,
      timestamp: Date.now(),
    },
  });
};

export const createApiClient = (overrides = {}) => {
  const config = { ...defaultConfig, ...overrides };

  const request = async (path, options = {}) => {
    const method = options.method || 'GET';

    if (!config.enableNetwork) {
      console.info('[api-client] Mocked request', { path, method });
      return mockResponse(path, method);
    }

    const url = buildUrl(config.baseUrl, path);
    console.log('[api-client] Sending request:', { url, method, headers: options.headers });
    const response = await fetch(url, options);
    const parsedResponse = await parseResponse(response);
    console.log('[api-client] Received response:', { status: parsedResponse.status, ok: parsedResponse.ok });
    return parsedResponse;
  };

  return {
    get: (path, options) => request(path, { ...options, method: 'GET' }),
    post: (path, body, options) =>
      request(path, {
        ...options,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(options && options.headers),
        },
        body: JSON.stringify(body),
      }),
    put: (path, body, options) =>
      request(path, {
        ...options,
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(options && options.headers),
        },
        body: JSON.stringify(body),
      }),
    patch: (path, body, options) =>
      request(path, {
        ...options,
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...(options && options.headers),
        },
        body: JSON.stringify(body),
      }),
    delete: (path, options) => request(path, { ...options, method: 'DELETE' }),
    withConfig: (nextConfig) => createApiClient({ ...config, ...nextConfig }),
  };
};

export default createApiClient;

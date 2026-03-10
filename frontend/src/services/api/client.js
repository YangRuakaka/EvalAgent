
import { API_BASE_URL } from '../../config/runtimeConfig';

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
  baseUrl: sanitizeBaseUrl(API_BASE_URL),
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

const sleep = (durationMs) =>
  new Promise((resolve) => {
    window.setTimeout(resolve, durationMs);
  });

const shouldRetryNetworkError = (error) => {
  if (!(error instanceof TypeError)) {
    return false;
  }

  const message = String(error?.message || '').toLowerCase();
  return (
    message.includes('failed to fetch')
    || message.includes('networkerror')
    || message.includes('load failed')
    || message.includes('err_connection_closed')
  );
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
    const retryOnNetworkError = Boolean(options.retryOnNetworkError);
    const maxRetries = Number.isFinite(options.maxRetries) ? Number(options.maxRetries) : Infinity;
    const retryDelayMs = Number.isFinite(options.retryDelayMs) ? Number(options.retryDelayMs) : 1500;
    const onRetry = typeof options.onRetry === 'function' ? options.onRetry : null;

    if (!config.enableNetwork) {
      console.info('[api-client] Mocked request', { path, method });
      return mockResponse(path, method);
    }

    const url = buildUrl(config.baseUrl, path);
    const requestOptions = { ...options };
    delete requestOptions.retryOnNetworkError;
    delete requestOptions.maxRetries;
    delete requestOptions.retryDelayMs;
    delete requestOptions.onRetry;

    let attempt = 0;
    // eslint-disable-next-line no-constant-condition
    while (true) {
      try {
        console.log('[api-client] Sending request:', {
          url,
          method,
          headers: requestOptions.headers,
          attempt,
        });
        const response = await fetch(url, requestOptions);
        const parsedResponse = await parseResponse(response);
        console.log('[api-client] Received response:', { status: parsedResponse.status, ok: parsedResponse.ok });
        return parsedResponse;
      } catch (error) {
        const canRetry =
          retryOnNetworkError
          && shouldRetryNetworkError(error)
          && attempt < maxRetries;

        if (!canRetry) {
          throw error;
        }

        attempt += 1;
        if (onRetry) {
          onRetry({ attempt, error, url, method });
        }
        await sleep(retryDelayMs);
      }
    }
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

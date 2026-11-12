type ApiError = {
  error?: string;
};

export async function apiPost<TRequest, TResponse>(
  url: string,
  body: TRequest
): Promise<TResponse> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const errorBody = (await response
      .json()
      .catch(() => ({}))) as ApiError;

    throw new Error(
      errorBody.error ?? `Request failed with status ${response.status}`
    );
  }

  return response.json() as Promise<TResponse>;
}
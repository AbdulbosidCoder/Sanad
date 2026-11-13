import { ApiError, createClient } from "./index";

function fakeFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  const calls: { url: string; init: RequestInit }[] = [];
  const impl = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(JSON.stringify(body), { status, headers });
  }) as unknown as typeof fetch;
  return { impl, calls };
}

describe("api client", () => {
  it("sends a request id and language", async () => {
    const { impl, calls } = fakeFetch(200, { status: "ok", components: {} });
    await createClient({ fetchImpl: impl, locale: "uz" }).health();
    const headers = new Headers(calls[0]!.init.headers);
    expect(headers.get("X-Request-Id")).toMatch(/^[0-9a-f]{32}$/);
    expect(headers.get("Accept-Language")).toBe("uz");
  });

  it("turns problem+json into ApiError with module, code and request id", async () => {
    const { impl } = fakeFetch(409, {
      status: 409,
      title: "Request failed",
      code: "ORDERS.OUT_OF_STOCK",
      module: "orders",
      request_id: "abc",
    });
    const err = await createClient({ fetchImpl: impl })
      .request("/api/v1/checkout")
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 409, code: "ORDERS.OUT_OF_STOCK", module: "orders", requestId: "abc" });
  });

  it("reports network failures with the request id it sent", async () => {
    const impl = (async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    const err = (await createClient({ fetchImpl: impl }).health().catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("NETWORK_ERROR");
    expect(err.requestId).toMatch(/^[0-9a-f]{32}$/);
  });

  it("returns a degraded health report instead of throwing", async () => {
    const { impl } = fakeFetch(503, { status: "degraded", components: { redis: "down" } });
    const report = await createClient({ fetchImpl: impl }).health();
    expect(report.components.redis).toBe("down");
  });
});

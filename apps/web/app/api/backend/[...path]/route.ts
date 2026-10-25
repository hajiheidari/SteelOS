import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const upstream = process.env.API_BASE_URL || "http://127.0.0.1:8000";
const cookieName = "steelos_session";
const resources = new Set([
  "auth",
  "inventory",
  "sales-drafts",
  "invoice-intakes",
  "sales-assistant",
  "organization",
  "catalog-references",
  "products",
  "product-identifiers",
  "parties",
  "crm-follow-ups",
  "warehouses",
  "locations",
  "warehouse-access",
  "price-sources",
  "price-observations",
  "audit-events",
]);

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (!resources.has(path[0]) || path.some((p) => !/^[a-zA-Z0-9-]+$/.test(p))) {
    return NextResponse.json(
      { error: { message: "مسیر نامعتبر است" } },
      { status: 404 },
    );
  }
  if (
    request.method !== "GET" &&
    request.headers.get("origin") !==
      (process.env.APP_ORIGIN || "http://127.0.0.1:3000")
  ) {
    return NextResponse.json(
      { error: { message: "درخواست از مبدأ نامعتبر است" } },
      { status: 403 },
    );
  }
  const jar = await cookies();
  const token = jar.get(cookieName)?.value;
  const invoiceUpload =
    request.method === "POST" && path.join("/") === "invoice-intakes/extract";
  const headers: Record<string, string> = {
    "Content-Type": invoiceUpload
      ? request.headers.get("content-type") || "application/octet-stream"
      : "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  const key = request.headers.get("idempotency-key");
  if (key) headers["Idempotency-Key"] = key;
  let body: string | Uint8Array | undefined;
  if (invoiceUpload) {
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 5 * 1024 * 1024) {
          await reader.cancel();
          return NextResponse.json(
            { error: { message: "حداکثر اندازهٔ فایل ۵ مگابایت است" } },
            { status: 413 },
          );
        }
        chunks.push(value);
      }
    }
    const bytes = new Uint8Array(size);
    let position = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, position);
      position += chunk.byteLength;
    }
    body = bytes;
  } else if (request.method !== "GET") body = await request.text();
  let result: Response;
  try {
    result = await fetch(
      `${upstream}/api/v1/${path.join("/")}${request.nextUrl.search}`,
      {
        method: request.method,
        headers,
        cache: "no-store",
        redirect: "error",
        body: body as BodyInit | undefined,
        signal: AbortSignal.timeout(invoiceUpload ? 45000 : 15000),
      },
    );
  } catch {
    return NextResponse.json(
      { error: { message: "ارتباط با سرور برقرار نشد" } },
      { status: 503 },
    );
  }
  const data = await result.json();
  if (result.ok && data.access_token) {
    jar.set(cookieName, data.access_token, {
      httpOnly: true,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      expires: new Date(data.expires_at),
    });
    delete data.access_token;
  }
  if (
    result.status === 401 ||
    (["auth/logout", "auth/password"].includes(path.join("/")) && result.ok)
  )
    jar.delete(cookieName);
  return NextResponse.json(data, {
    status: result.status,
    headers: { "Cache-Control": "no-store" },
  });
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };

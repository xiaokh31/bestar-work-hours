import { NextRequest, NextResponse } from "next/server";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;
const MAX_BODY = 3_200_000;
const allowed = /^(?:health|attendance-imports(?:\/deletion-history|\/[a-f0-9-]+(?:\/(?:parse|parse-result|generate-wage-record|files|row-history|deletion-impact|rows\/[a-f0-9-]+))?)?|attendance-files\/[a-f0-9-]+\/download)$/;
function failure(code: string, status: number) { return NextResponse.json({code,message:code},{status,headers:{"Cache-Control":"no-store"}}); }
async function proxy(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
  const {path} = await context.params;
  const route = path.join("/");
  if (!allowed.test(route)) return failure("NOT_FOUND",404);
  const mutating = !["GET","HEAD"].includes(request.method);
  // Exact configured public origin protects mutations, against cross-origin form submissions.
  const origin = process.env.APP_ORIGIN ?? request.nextUrl.origin;
  if (mutating && request.headers.get("origin") !== origin) return failure("FORBIDDEN",403);
  if (!process.env.API_ORIGIN || !process.env.API_SERVICE_SECRET) return failure("CONFIGURATION_REQUIRED",503);
  let body: Uint8Array | undefined;
  if (mutating && request.body) {
    const reader = request.body.getReader(); const chunks: Uint8Array[] = []; let length = 0;
    while (true) { const result=await reader.read(); if(result.done)break; length+=result.value.byteLength;
      if(length>MAX_BODY){await reader.cancel(); return failure("ATTENDANCE_FILE_TOO_LARGE",413);} chunks.push(result.value); }
    body = new Uint8Array(length); let offset=0; for(const chunk of chunks){body.set(chunk,offset);offset+=chunk.length;}
  }
  try {
    const headers = new Headers({"X-Service-Key":process.env.API_SERVICE_SECRET});
    if(process.env.API_DEPLOYMENT_BYPASS_SECRET)headers.set("x-vercel-protection-bypass",process.env.API_DEPLOYMENT_BYPASS_SECRET);
    if(request.headers.has("content-type"))headers.set("Content-Type",request.headers.get("content-type")!);
    const upstream = await fetch(`${process.env.API_ORIGIN.replace(/\/$/,"")}/${route}${request.nextUrl.search}`,{
      method:request.method,headers,body:body as BodyInit | undefined,redirect:"error",cache:"no-store",signal:AbortSignal.timeout(55000),
    });
    const outHeaders = new Headers({"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"});
    for(const key of ["content-type","content-disposition"])if(upstream.headers.has(key))outHeaders.set(key,upstream.headers.get(key)!);
    return new NextResponse(upstream.body,{status:upstream.status,headers:outHeaders});
  } catch { return failure("API_UNAVAILABLE",503); }
}
export { proxy as GET, proxy as POST, proxy as DELETE, proxy as PATCH };

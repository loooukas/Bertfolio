import { NextRequest } from "next/server"

import { proxyDelete, proxyGet } from "@/lib/server/backend-proxy"

interface RouteContext {
  params: Promise<{ ticker: string }>
}

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  const { ticker } = await context.params
  return proxyGet(request, `/api/cache-runs/${encodeURIComponent(ticker)}`)
}

export async function DELETE(request: NextRequest, context: RouteContext): Promise<Response> {
  const { ticker } = await context.params
  return proxyDelete(request, `/api/cache-runs/${encodeURIComponent(ticker)}`)
}

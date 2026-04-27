import { NextRequest } from "next/server"

import { proxyGet } from "@/lib/server/backend-proxy"

interface RouteContext {
  params: Promise<{ job_id: string }>
}

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  const { job_id: jobId } = await context.params
  return proxyGet(request, `/api/analyze/jobs/${encodeURIComponent(jobId)}`)
}

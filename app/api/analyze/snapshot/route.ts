import { NextRequest } from "next/server"

import { proxyGet } from "@/lib/server/backend-proxy"

export async function GET(request: NextRequest): Promise<Response> {
  return proxyGet(request, "/api/analyze/snapshot")
}

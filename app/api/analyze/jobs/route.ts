import { NextRequest } from "next/server"

import { proxyPost } from "@/lib/server/backend-proxy"

export async function POST(request: NextRequest): Promise<Response> {
  return proxyPost(request, "/api/analyze/jobs")
}

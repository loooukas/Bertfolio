import { NextRequest } from "next/server"

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"

function backendBaseUrl(): string {
  return (process.env.FINBERT_BACKEND_URL || DEFAULT_BACKEND_URL).replace(/\/+$/, "")
}

function createTargetUrl(request: NextRequest, path: string): URL {
  const source = new URL(request.url)
  const target = new URL(`${backendBaseUrl()}${path}`)
  target.search = source.search
  return target
}

function copyResponseHeaders(response: Response): Headers {
  const headers = new Headers(response.headers)
  headers.delete("content-encoding")
  headers.delete("transfer-encoding")
  headers.delete("connection")
  return headers
}

function copyRequestHeaders(request: NextRequest): Headers {
  const headers = new Headers()
  const contentType = request.headers.get("content-type")
  const accept = request.headers.get("accept")
  if (contentType) {
    headers.set("content-type", contentType)
  }
  if (accept) {
    headers.set("accept", accept)
  }
  return headers
}

export async function proxyGet(request: NextRequest, path: string): Promise<Response> {
  const response = await fetch(createTargetUrl(request, path), {
    method: "GET",
    headers: copyRequestHeaders(request),
    cache: "no-store",
  })
  return new Response(response.body, { status: response.status, headers: copyResponseHeaders(response) })
}

export async function proxyPost(request: NextRequest, path: string): Promise<Response> {
  const body = await request.text()
  const response = await fetch(createTargetUrl(request, path), {
    method: "POST",
    headers: copyRequestHeaders(request),
    body,
    cache: "no-store",
  })
  return new Response(response.body, { status: response.status, headers: copyResponseHeaders(response) })
}

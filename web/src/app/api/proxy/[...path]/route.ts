/**
 * API Proxy Route
 *
 * Proxies requests to the backend API with the API key header.
 * This allows client components to make authenticated API requests
 * without exposing the API key to the browser.
 */

import { NextRequest, NextResponse } from "next/server";

const API_BASE =
  process.env.SPORTS_API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_SPORTS_API_URL ||
  "http://localhost:8000";

const API_KEY = process.env.SPORTS_API_KEY;

async function proxyRequest(
  request: NextRequest,
  params: Promise<{ path: string[] }>
): Promise<NextResponse> {
  const { path } = await params;
  const pathStr = path.join("/");
  const url = new URL(request.url);
  const targetUrl = `${API_BASE}/${pathStr}${url.search}`;

  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };

  if (API_KEY) {
    headers["X-API-Key"] = API_KEY;
  }

  // Forward relevant headers from the original request
  const forwardHeaders = ["accept", "content-type"];
  for (const header of forwardHeaders) {
    const value = request.headers.get(header);
    if (value) {
      headers[header] = value;
    }
  }

  try {
    // For POST/PUT/PATCH, get the body and re-encode to ensure proper JSON
    let body: string | undefined;
    if (request.method !== "GET" && request.method !== "HEAD") {
      const contentType = request.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        // Parse and re-stringify to ensure clean JSON encoding
        const jsonBody = await request.json();
        body = JSON.stringify(jsonBody);
      } else {
        body = await request.text();
      }
    }

    const response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
    });

    const data = await response.text();

    return new NextResponse(data, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") || "application/json",
      },
    });
  } catch (error) {
    console.error("Proxy error:", error);
    return NextResponse.json(
      { error: "Failed to proxy request to backend" },
      { status: 502 }
    );
  }
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  return proxyRequest(request, context.params);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  return proxyRequest(request, context.params);
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  return proxyRequest(request, context.params);
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  return proxyRequest(request, context.params);
}

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  return proxyRequest(request, context.params);
}

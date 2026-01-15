import { NextRequest, NextResponse } from "next/server";

/**
 * Basic auth middleware for production admin console.
 * 
 * Requires ADMIN_PASSWORD env var to be set in production.
 * Username is "admin", password is the configured value.
 */
export function middleware(request: NextRequest) {
  const adminPassword = process.env.ADMIN_PASSWORD;
  const environment = process.env.ENVIRONMENT || process.env.NODE_ENV;

  // Skip auth in development or if no password configured
  if (environment === "development" || !adminPassword) {
    return NextResponse.next();
  }

  const authHeader = request.headers.get("authorization");

  if (!authHeader) {
    return unauthorizedResponse();
  }

  // Parse basic auth: "Basic base64(username:password)"
  const [scheme, encoded] = authHeader.split(" ");
  if (scheme !== "Basic" || !encoded) {
    return unauthorizedResponse();
  }

  const decoded = Buffer.from(encoded, "base64").toString("utf-8");
  const [username, password] = decoded.split(":");

  // Fixed username "admin", password from env
  if (username === "admin" && password === adminPassword) {
    return NextResponse.next();
  }

  return unauthorizedResponse();
}

function unauthorizedResponse(): NextResponse {
  return new NextResponse("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="Sports Admin"',
    },
  });
}

// Apply to all routes
export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

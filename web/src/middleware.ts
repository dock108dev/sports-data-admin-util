import { NextRequest, NextResponse } from "next/server";

/**
 * Constant-time string comparison to prevent timing attacks.
 * Uses Web Crypto API's subtle.digest which is available in Edge Runtime.
 */
async function timingSafeCompare(a: string, b: string): Promise<boolean> {
  // Use Web Crypto API to create hashes for constant-time comparison
  // Hashing ensures comparison time is independent of input content and length
  const encoder = new TextEncoder();
  const aBuffer = encoder.encode(a);
  const bBuffer = encoder.encode(b);
  
  // Hash both strings
  const [aHash, bHash] = await Promise.all([
    crypto.subtle.digest('SHA-256', aBuffer),
    crypto.subtle.digest('SHA-256', bBuffer),
  ]);
  
  // Compare hashes byte by byte in constant time
  const aArray = new Uint8Array(aHash);
  const bArray = new Uint8Array(bHash);
  
  let result = 0;
  for (let i = 0; i < aArray.length; i++) {
    result |= aArray[i] ^ bArray[i];
  }
  
  return result === 0;
}

/**
 * Basic auth middleware for production admin console.
 * 
 * Requires ADMIN_PASSWORD env var to be set in production.
 * Username is "admin", password is the configured value.
 */
export async function middleware(request: NextRequest) {
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
  
  // Split only on first colon to handle passwords containing colons
  const colonIndex = decoded.indexOf(":");
  if (colonIndex === -1) {
    return unauthorizedResponse();
  }
  const username = decoded.substring(0, colonIndex);
  const password = decoded.substring(colonIndex + 1);

  // Fixed username "admin", password from env
  // Use constant-time comparison to prevent timing attacks
  const usernameMatch = username === "admin";
  const passwordMatch = adminPassword ? await timingSafeCompare(password, adminPassword) : false;
  
  if (usernameMatch && passwordMatch) {
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

// Apply to all routes except static assets, API routes, and healthz
// API routes use X-API-Key auth, not basic auth
export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/|healthz).*)"],
};

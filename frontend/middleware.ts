import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const COOKIE_NAME = process.env.NEXT_PUBLIC_REFRESH_COOKIE_NAME ?? "invoice_refresh_token";
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8009").replace(/\/$/, "");
const APP_ENV = (process.env.NEXT_PUBLIC_APP_ENV ?? "local").toLowerCase();
const PUBLIC_READONLY_DEMO =
  (process.env.NEXT_PUBLIC_AUTH_PUBLIC_READONLY_DEMO ?? (APP_ENV === "production" ? "false" : "true")).toLowerCase() === "true";

function loginRedirect(request: NextRequest) {
  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
}

export async function middleware(request: NextRequest) {
  if (!request.nextUrl.pathname.startsWith("/app")) {
    return NextResponse.next();
  }

  if (PUBLIC_READONLY_DEMO && APP_ENV !== "production") {
    return NextResponse.next();
  }

  const token = request.cookies.get(COOKIE_NAME)?.value;
  if (!token) {
    return loginRedirect(request);
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
      method: "GET",
      headers: {
        Cookie: `${COOKIE_NAME}=${token}`
      },
      cache: "no-store"
    });
    if (response.status === 401) {
      return loginRedirect(request);
    }
  } catch {
    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/app/:path*"]
};

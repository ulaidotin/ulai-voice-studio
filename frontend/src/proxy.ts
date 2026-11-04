import { NextResponse, type NextRequest } from "next/server";

// Optimistic check only: the backend validates the session on every API call, and a 401 there
// also sends the browser to /login.
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const signedIn = request.cookies.has("uvs_session");

  if (!signedIn && pathname !== "/login") {
    const url = new URL("/login", request.url);
    if (pathname !== "/") url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Everything except the API proxy, Next internals and static files.
  matcher: ["/((?!api/|_next/|favicon.ico|icon.svg|.*\\.(?:svg|png|jpg|ico|webp|txt)$).*)"],
};

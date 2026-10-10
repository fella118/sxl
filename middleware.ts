import { NextRequest, NextResponse } from "next/server";

// Basic auth: any username, password must equal APP_PASSWORD.
// If APP_PASSWORD is not set, every request is refused (fail closed).
export function middleware(req: NextRequest) {
  const expected = process.env.APP_PASSWORD;
  if (!expected) {
    return new NextResponse("APP_PASSWORD non configuré.", { status: 503 });
  }

  const header = req.headers.get("authorization");
  if (header?.startsWith("Basic ")) {
    try {
      const decoded = atob(header.slice(6));
      const password = decoded.slice(decoded.indexOf(":") + 1);
      if (safeEqual(password, expected)) return NextResponse.next();
    } catch {
      // malformed header, fall through to 401
    }
  }

  return new NextResponse("Authentification requise.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="C scan", charset="UTF-8"' },
  });
}

function safeEqual(a: string, b: string) {
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

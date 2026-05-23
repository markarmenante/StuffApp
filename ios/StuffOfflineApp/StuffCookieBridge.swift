import Foundation
import WebKit

enum StuffCookieBridge {
    @MainActor
    static func syncWebCookiesToURLSession() async {
        let cookieStore = WKWebsiteDataStore.default().httpCookieStore
        let cookies = await cookieStore.allCookies()
        for cookie in cookies where shouldCopy(cookie) {
            HTTPCookieStorage.shared.setCookie(cookie)
        }
    }

    private static func shouldCopy(_ cookie: HTTPCookie) -> Bool {
        let domain = cookie.domain.lowercased()
        return domain.contains("armenante.com") || domain.contains("cloudflareaccess.com")
    }
}

private extension WKHTTPCookieStore {
    func allCookies() async -> [HTTPCookie] {
        await withCheckedContinuation { continuation in
            getAllCookies { cookies in
                continuation.resume(returning: cookies)
            }
        }
    }
}

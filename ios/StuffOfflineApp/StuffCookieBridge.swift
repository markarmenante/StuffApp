import Foundation
import WebKit

enum StuffCookieBridge {
    static func syncWebCookiesToURLSession() async {
        let cookieStore = WKWebsiteDataStore.default().httpCookieStore
        let cookies = await cookieStore.allCookies()
        for cookie in cookies where cookie.domain.contains("stuff.armenante.com") {
            HTTPCookieStorage.shared.setCookie(cookie)
        }
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

# Run Stuff On Your iPhone

This project is a native iOS app, so it needs Apple's Xcode app to install it
on an iPhone. The web app remains the source of truth; the iPhone app downloads
a local copy of records and files for low-connectivity browsing.

## One-Time Mac Setup

1. Install **Xcode** from the Mac App Store.
2. Open Xcode once after install and let it finish installing components.
3. If Xcode asks you to sign in, use your Apple ID.

Optional Terminal check after install:

```sh
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
xcodebuild -version
```

## Open The Project

1. In Finder, open:

   `/Users/markarmenante/Desktop/StuffApp/ios`

2. Double-click:

   `Stuff.xcodeproj`

3. Xcode opens the project. In the top bar, the scheme should read **Stuff**.

## Set Signing

1. In Xcode's left sidebar, click the blue **Stuff** project icon.
2. Click the **Stuff** target.
3. Open **Signing & Capabilities**.
4. Check **Automatically manage signing**.
5. Choose your Apple developer team.
6. If Xcode says the bundle identifier is already taken, change it from:

   `com.armenante.stuff`

   to something unique, for example:

   `com.markarmenante.stuff`

## Install On iPhone

1. Plug the iPhone into the Mac with USB-C.
2. Unlock the iPhone and tap **Trust This Computer** if asked.
3. In Xcode's device picker near the Run button, choose your iPhone.
4. Press the **Run** button, the triangle/play icon.
5. If the iPhone blocks the app as an untrusted developer, open:

   `Settings > General > VPN & Device Management`

   Then trust your Apple ID/developer profile.

## First Launch

1. Open **Stuff** on the iPhone.
2. Tap the Safari/web icon in the top right to open the live web app.
3. Sign into `stuff.armenante.com` if Cloudflare asks.
4. Tap **Done** to close the live web app.
5. Tap **Sync**.

After that sync, records and downloaded images/documents are available locally
inside the app for low-connectivity browsing. When you edit online, close the
live editor and the app syncs the canonical web data back down.

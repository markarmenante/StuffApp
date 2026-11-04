import {createController} from './controller.mjs';

const controller = createController(chrome);
chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  controller.handle(message, sender).then(sendResponse, () => sendResponse({ok:false, error:'browser_unavailable'}));
  // Literal true works across supported Chromium versions. No long-held
  // message channel: start/poll return immediately while the reader owns its tab.
  return true;
});
chrome.tabs.onRemoved.addListener(id => controller.tabRemoved(id));

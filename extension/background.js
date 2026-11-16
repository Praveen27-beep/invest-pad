// Opens the notepad and hands it the page's address, title and selected text.
//
// The page is read only at the moment you ask: clicking the toolbar button, pressing the
// shortcut, or choosing "Add to Invest-pad" from the right-click menu. Nothing runs on
// pages in the background, and nothing is sent anywhere from this file.

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "capture", title: "Add to Invest-pad", contexts: ["page", "selection"] });
});

function remember(tab, selection) {
  return chrome.storage.session.set({
    context: { url: tab?.url ?? "", title: tab?.title ?? "", selection: selection ?? "", at: Date.now() },
  });
}

// Toolbar button and keyboard shortcut.
chrome.action.onClicked.addListener((tab) => {
  // Must be the first call: Chrome only allows opening the panel directly from the click.
  chrome.sidePanel.open({ tabId: tab.id });
  chrome.scripting
    .executeScript({ target: { tabId: tab.id }, func: () => String(window.getSelection() ?? "") })
    .then(([result]) => remember(tab, result?.result))
    .catch(() => remember(tab, "")); // pages Chrome does not let extensions read
});

// Right-click menu. Chrome supplies the selected text itself.
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab) return;
  chrome.sidePanel.open({ tabId: tab.id });
  remember(tab, info.selectionText);
});

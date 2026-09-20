/* Preserve the visible note when server-rendered history panels change height. */
(function () {
  'use strict';
  var toggle = document.getElementById('banknoteHistoryToggle');
  if (!toggle) return; // Collection only; never market rows or other categories.
  var key = 'banknote-history-position';

  toggle.addEventListener('click', function (event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey ||
        event.ctrlKey || event.shiftKey || event.altKey) return;
    var destination = new URL(window.location.href);
    var historyValue = new URL(toggle.href).searchParams.get('history');
    if (historyValue === null) destination.searchParams.delete('history');
    else destination.searchParams.set('history', historyValue);
    var toolbar = document.querySelector('.list-toolbar');
    var top = toolbar ? Math.max(0, toolbar.getBoundingClientRect().bottom) : 0;
    var rows = Array.from(document.querySelectorAll('.item-list-banknotes .item-row'));
    var row = rows.find(function (item) { return item.getBoundingClientRect().bottom > top; });
    var position = {url: destination.href, savedAt: Date.now(), atTop: window.scrollY < 1,
      id: row ? row.id : null, offset: row ? row.getBoundingClientRect().top : 0};
    try {
      sessionStorage.setItem(key, JSON.stringify(position));
    } catch (_) {
      // Storage-disabled browsers still land on the right note.
      if (row && !position.atTop) destination.hash = row.id;
    }
    event.preventDefault();
    window.location.assign(destination.href);
  });

  window.BanknoteHistoryPosition = {
    restore: function () {
      var position;
      try {
        position = JSON.parse(sessionStorage.getItem(key));
        sessionStorage.removeItem(key); // One navigation, never later Back/filter actions.
      } catch (_) { return false; }
      if (!position || position.url !== window.location.href ||
          Date.now() - position.savedAt > 30000 || !Number.isFinite(position.offset)) return false;
      var row = position.id && document.getElementById(position.id);
      if (!position.atTop && !row) return false;
      var cancelled = false;
      function cancel() { cancelled = true; }
      ['wheel', 'touchstart', 'pointerdown', 'keydown'].forEach(function (event) {
        window.addEventListener(event, cancel, {once: true, passive: true});
      });
      function apply() {
        if (cancelled) return; // Never pull the user back after they start moving.
        window.scrollTo({top: position.atTop ? 0 :
          window.scrollY + row.getBoundingClientRect().top - position.offset,
          behavior: 'instant'});
      }
      apply();
      // Native hash restoration and late fonts/images can run after this script.
      // Reapply after layout settles, while allowing immediate user interaction.
      function settled() { requestAnimationFrame(function () { requestAnimationFrame(apply); }); }
      if (document.readyState === 'complete') settled();
      else window.addEventListener('load', settled, {once: true});
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(settled);
      return true;
    }
  };
})();

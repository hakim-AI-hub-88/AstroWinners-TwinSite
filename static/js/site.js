/*###########################################################################
# TWINSITE - SHARED SITE SCRIPT (loaded by templates/base.html)
#   Table of contents (<details class="toc">): open on desktop, collapsed on
#   mobile, highlights the section currently in view.
#   No dependencies; pages work fully without it.
###########################################################################*/
(function () {
  "use strict";
  var toc = document.querySelector("details.toc");
  if (!toc) return;

  // Keep the table of contents open on desktop, collapsed on small screens.
  var wide = window.matchMedia("(min-width: 961px)");
  function sync() { toc.open = wide.matches; }
  sync();
  if (wide.addEventListener) wide.addEventListener("change", sync); else wide.addListener(sync);

  // Close it after picking a section on mobile.
  toc.addEventListener("click", function (e) {
    if (e.target.closest("a") && !wide.matches) toc.open = false;
  });

  // Scroll spy: mark the link of the section in view.
  var links = Array.prototype.slice.call(toc.querySelectorAll('a[href^="#"]'));
  var byId = {};
  links.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
  var sections = Object.keys(byId).map(function (id) { return document.getElementById(id); }).filter(Boolean);
  if (!("IntersectionObserver" in window) || !sections.length) return;
  var current = null;
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (!en.isIntersecting) return;
      if (current) current.classList.remove("is-active");
      current = byId[en.target.id];
      if (current) current.classList.add("is-active");
    });
  }, { rootMargin: "-20% 0px -70% 0px" });
  sections.forEach(function (s) { io.observe(s); });
})();

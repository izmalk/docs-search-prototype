/* Phase 6: Custom Sphinx search override.
 *
 * Intercepts the canonical-sphinx sidebar search form (selector
 * `form.sidebar-search-container`, input `input.sidebar-search`) and routes
 * the query to the FastAPI `/api/search` endpoint instead of Sphinx's native
 * client-side searchindex.js mechanism.
 *
 * Results are rendered into the main content area (<article id="furo-main-content">),
 * replacing the page's content while search results are visible. The original
 * content is restored when the user closes the results panel (× button or Esc).
 * This gives the results the full width of the content column, which is much
 * more readable than cramming them into the narrow sidebar.
 */
(function () {
  "use strict";

  // --- Styles injected once on DOMContentLoaded -------------------------------
  var STYLE = `
    .opensearch-results-header {
      display: flex; align-items: center; gap: .5rem;
      margin-bottom: 1.5rem;
      padding-bottom: .75rem;
      border-bottom: 1px solid var(--color-foreground-border, #eee);
    }
    .opensearch-results-header .opensearch-query {
      flex: 1; font-size: 1.25rem; font-weight: 550; margin: 0;
    }
    .opensearch-results-close {
      cursor: pointer; border: none; background: none;
      font-size: 1.5rem; line-height: 1;
      color: var(--color-foreground-secondary, #666);
      padding: 0 .5rem;
    }
    .opensearch-results-close:hover { color: var(--color-link, #06c); }
    .opensearch-results { list-style: none; margin: 0; padding: 0; }
    .opensearch-result-item {
      padding: 1rem 0;
      border-bottom: 1px solid var(--color-foreground-border, #eee);
    }
    .opensearch-result-item:last-child { border-bottom: none; }
    .opensearch-result-item a {
      display: block;
      font-size: 1.1rem; font-weight: 500;
      color: var(--color-link, #06c);
      text-decoration: none;
    }
    .opensearch-result-item a:hover { text-decoration: underline; }
    .opensearch-result-snippet {
      margin: .5rem 0 0;
      font-size: .95rem;
      color: var(--color-foreground-secondary, #666);
      line-height: 1.5;
    }
    .opensearch-loading, .opensearch-no-results, .opensearch-error {
      padding: 2rem 0;
      font-size: 1rem;
      color: var(--color-foreground-secondary, #666);
    }
    .opensearch-error { color: #c00; }
  `;

  function injectStyles() {
    if (document.getElementById("opensearch-style")) return;
    var s = document.createElement("style");
    s.id = "opensearch-style";
    s.textContent = STYLE;
    document.head.appendChild(s);
  }

  // --- State -----------------------------------------------------------------
  var savedContent = null; // original innerHTML of <article> before results
  var mainContent = null;  // the <article id="furo-main-content"> element

  function getMainContent() {
    if (!mainContent) {
      mainContent = document.getElementById("furo-main-content") ||
        document.querySelector("article[role='main']");
    }
    return mainContent;
  }

  function renderResults(container, results) {
    container.innerHTML = "";

    var header = document.createElement("div");
    header.className = "opensearch-results-header";

    var queryLabel = document.createElement("h2");
    queryLabel.className = "opensearch-query";
    container._opensearchQuery = queryLabel; // stash for runSearch to update
    header.appendChild(queryLabel);

    var closeBtn = document.createElement("button");
    closeBtn.className = "opensearch-results-close";
    closeBtn.innerHTML = "&times;";
    closeBtn.setAttribute("aria-label", "Close search results");
    closeBtn.addEventListener("click", restoreContent);
    header.appendChild(closeBtn);

    container.appendChild(header);

    if (!results.length) {
      var empty = document.createElement("p");
      empty.className = "opensearch-no-results";
      empty.textContent = "No results found.";
      container.appendChild(empty);
      return;
    }

    var list = document.createElement("ul");
    list.className = "opensearch-results";
    results.forEach(function (r) {
      var item = document.createElement("li");
      item.className = "opensearch-result-item";

      var link = document.createElement("a");
      link.href = r.url;
      link.textContent = r.title || r.url;
      item.appendChild(link);

      if (r.snippet) {
        var snip = document.createElement("p");
        snip.className = "opensearch-result-snippet";
        snip.textContent = r.snippet;
        item.appendChild(snip);
      }
      list.appendChild(item);
    });
    container.appendChild(list);
  }

  async function runSearch(query) {
    var article = getMainContent();
    if (!article) return;

    // Save original content the first time we replace it.
    if (!savedContent) {
      savedContent = article.innerHTML;
    }

    // Swap in a loading state immediately.
    article.innerHTML = "";
    var container = document.createElement("div");
    container.id = "opensearch-results-container";
    article.appendChild(container);

    // Render the header with the query + a loading message.
    renderResults(container, []);
    container._opensearchQuery.textContent = 'Results for "' + query + '"';
    var loading = document.createElement("p");
    loading.className = "opensearch-loading";
    loading.textContent = "Searching…";
    container.appendChild(loading);

    try {
      var resp = await fetch("/api/search?q=" + encodeURIComponent(query));
      if (!resp.ok) {
        throw new Error("Search endpoint returned " + resp.status);
      }
      var results = await resp.json();
      renderResults(container, results);
      container._opensearchQuery.textContent = 'Results for "' + query + '"';
    } catch (err) {
      renderResults(container, []);
      container._opensearchQuery.textContent = 'Results for "' + query + '"';
      var errP = document.createElement("p");
      errP.className = "opensearch-error";
      errP.textContent = "Search failed: " + err.message;
      container.appendChild(errP);
    }

    // Scroll the main content to the top so the header is visible.
    article.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function restoreContent() {
    var article = getMainContent();
    if (!article || !savedContent) return;
    article.innerHTML = savedContent;
    savedContent = null;
  }

  document.addEventListener("DOMContentLoaded", function () {
    injectStyles();

    var form = document.querySelector("form.sidebar-search-container");
    if (!form) {
      // Not a page with the sidebar search box (e.g. the search.html page
      // itself). Fall back to the dedicated search page form if present.
      form = document.querySelector("form[role='search']");
    }
    if (!form) return;

    var input =
      form.querySelector("input.sidebar-search") ||
      form.querySelector("input[name='q']");
    if (!input) return;

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var q = input.value.trim();
      if (q) runSearch(q);
    });

    // Esc restores the original page content.
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") restoreContent();
    });
  });
})();

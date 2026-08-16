/* Phase 6: Custom Sphinx search override.
 *
 * Intercepts the canonical-sphinx sidebar search form (selector
 * `form.sidebar-search-container`, input `input.sidebar-search`) and routes
 * the query to the FastAPI `/api/search` endpoint instead of Sphinx's native
 * client-side searchindex.js mechanism.
 *
 * Results are rendered into the `#searchbox` div (already present in the
 * canonical-sphinx sidebar/search.html template) as `.opensearch-result-item`
 * nodes, which the Playwright test looks for.
 */
(function () {
  "use strict";

  function renderResults(container, results) {
    container.innerHTML = "";
    if (!results.length) {
      container.innerHTML =
        '<p class="opensearch-no-results">No results found.</p>';
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

  async function runSearch(query, container) {
    container.innerHTML =
      '<p class="opensearch-loading">Searching…</p>';
    try {
      var resp = await fetch(
        "/api/search?q=" + encodeURIComponent(query)
      );
      if (!resp.ok) {
        throw new Error("Search endpoint returned " + resp.status);
      }
      var results = await resp.json();
      renderResults(container, results);
    } catch (err) {
      container.innerHTML =
        '<p class="opensearch-error">Search failed: ' +
        err.message +
        "</p>";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.querySelector("form.sidebar-search-container");
    if (!form) {
      // Not a page with the sidebar search box (e.g. the search.html page
      // itself). Fall back to the dedicated search page form if present.
      form = document.querySelector("form[role='search']");
    }
    if (!form) return;

    var input = form.querySelector("input.sidebar-search") ||
      form.querySelector("input[name='q']");
    if (!input) return;

    // Ensure there is a container to render into.
    var container = document.getElementById("searchbox");
    if (!container) {
      container = document.createElement("div");
      container.id = "searchbox";
      form.parentNode.insertBefore(container, form.nextSibling);
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var q = input.value.trim();
      if (q) runSearch(q, container);
    });
  });
})();

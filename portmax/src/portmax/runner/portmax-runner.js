/*
 * PortMax runner: runs a college's fetch plan inside the student's own portal session.
 *
 * The Android app injects this file into its WebView after the student has logged in to the
 * portal themselves, then calls PortMaxRunner.run(settings) or PortMaxRunner.keepAlive(settings)
 * with the settings from GET /v1/connectors/{college}. Every request is a GET from the portal's
 * own page, so it carries the student's cookies, the WebView's User-Agent and a portal Referer,
 * exactly like the student clicking through. The result is a list of pages for POST /v1/pages.
 *
 * This is the twin of executor.py and must stay in step with it: GET only, links checked before
 * they are followed, the session checked on every page, and nothing parsed here.
 */
(function (global) {
  "use strict";

  var FORBIDDEN_PREFIXES = [
    "logout", "logoff", "signout", "save", "update", "submit", "delete", "remove", "pay",
    "edit", "change", "reset", "password", "register", "apply", "upload", "cancel",
  ];

  function PortMaxError(code, detail) {
    var error = new Error(code + ": " + detail);
    error.code = code;
    error.detail = detail;
    return error;
  }

  function pathTokens(path) {
    var spaced = path.replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase();
    return spaced.match(/[a-z]+|[0-9]+/g) || [];
  }

  function checkPath(path) {
    if (!path || path.length > 2048) throw PortMaxError("unsafe_plan", "empty or overlong path");
    if (/^[a-z][a-z0-9+.-]*:/i.test(path) || path.indexOf("//") === 0 || path.indexOf("\\") >= 0) {
      throw PortMaxError("unsafe_plan", "not a relative portal path: " + path);
    }
    var tokens = pathTokens(path);
    for (var i = 0; i < tokens.length; i++) {
      for (var j = 0; j < FORBIDDEN_PREFIXES.length; j++) {
        if (tokens[i].indexOf(FORBIDDEN_PREFIXES[j]) === 0) {
          throw PortMaxError("unsafe_plan", path + " contains " + tokens[i]);
        }
      }
    }
    return path;
  }

  function resolveLink(pageUrl, href) {
    var target = new URL(href.trim(), pageUrl);
    if (target.origin !== global.location.origin) {
      throw PortMaxError("unsafe_plan", "link leaves the portal: " + target.href);
    }
    return checkPath(target.pathname + target.search);
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  async function fetchPage(stepId, path, referrer, markers) {
    var url = new URL(checkPath(path), global.location.origin).href;
    var response;
    try {
      response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        redirect: "follow",
        referrer: referrer,
        cache: "no-store",
      });
    } catch (e) {
      throw PortMaxError("portal_unavailable", stepId + ": " + e.message);
    }
    if (new URL(response.url).origin !== global.location.origin) {
      throw PortMaxError("unsafe_plan", stepId + ": the portal redirected off-site");
    }
    if (response.status >= 500) {
      throw PortMaxError("portal_unavailable", stepId + ": HTTP " + response.status);
    }
    var html = await response.text();
    var doc = new DOMParser().parseFromString(html, "text/html");
    if (doc.querySelector(markers.login_page)) {
      throw PortMaxError("session_expired", stepId + ": the portal showed its login page");
    }
    if (!doc.querySelector(markers.logged_in)) {
      throw PortMaxError("portal_changed", stepId + ": neither logged in nor the login page");
    }
    return {
      page: {
        step: stepId,
        url: response.url,
        status: response.status,
        html: html,
        fetched_at: new Date().toISOString(),
      },
      doc: doc,
    };
  }

  function links(fetched, forEach) {
    var found = [];
    for (var i = 0; i < fetched.length; i++) {
      var nodes = fetched[i].doc.querySelectorAll(forEach.select);
      for (var j = 0; j < nodes.length; j++) {
        var href = nodes[j].getAttribute(forEach.attr || "href");
        if (!href) continue;
        found.push({ path: resolveLink(fetched[i].page.url, href), referrer: fetched[i].page.url });
      }
    }
    var unique = [];
    var seen = {};
    for (var k = 0; k < found.length; k++) {
      if (!seen[found[k].path]) {
        seen[found[k].path] = true;
        unique.push(found[k]);
      }
    }
    return unique.slice(0, forEach.max_items || 30);
  }

  async function run(settings, options) {
    options = options || {};
    var plan = settings.plan;
    var markers = settings.markers;
    var only = options.steps || null;
    var pace = options.paceMs !== undefined ? options.paceMs : plan.pace_ms;
    var fetched = {};
    var pages = [];
    var referrer = global.location.href;
    var first = true;
    for (var i = 0; i < plan.steps.length; i++) {
      var step = plan.steps[i];
      if (only && only.indexOf(step.id) < 0) continue;
      var targets = step.path
        ? [{ path: step.path, referrer: referrer }]
        : links(fetched[step.for_each.from] || [], step.for_each);
      for (var t = 0; t < targets.length; t++) {
        if (!first && pace) await sleep(pace);
        first = false;
        var result = await fetchPage(step.id, targets[t].path, targets[t].referrer, markers);
        (fetched[step.id] = fetched[step.id] || []).push(result);
        pages.push(result.page);
        referrer = result.page.url;
      }
    }
    return pages;
  }

  function keepAlive(settings) {
    return run(settings, { steps: [settings.plan.keepalive_step] });
  }

  function isLoggedIn(markers) {
    return !document.querySelector(markers.login_page) && !!document.querySelector(markers.logged_in);
  }

  global.PortMaxRunner = {
    version: "1",
    run: run,
    keepAlive: keepAlive,
    isLoggedIn: isLoggedIn,
    checkPath: checkPath,
    resolveLink: resolveLink,
  };
})(window);

// SPDX-License-Identifier: Apache-2.0
// Truncate the scenario-dot strip to one line and show +n when dots don't fit.
// Format <time datetime> elements in the viewer's timezone while keeping the UTC fallback.
(function () {
  function formatLocalTime(iso) {
    const ms = Date.parse(iso);
    if (!Number.isFinite(ms) || typeof Intl === "undefined" || !Intl.DateTimeFormat) {
      return "";
    }
    try {
      const date = new Date(ms);
      const dateFmt = new Intl.DateTimeFormat("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      });
      const parts = {};
      for (const part of dateFmt.formatToParts(date)) {
        parts[part.type] = part.value;
      }
      if (!parts.day || !parts.month || !parts.year || !parts.hour || !parts.minute) {
        return "";
      }
      let zone = "";
      try {
        const tzFmt = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" });
        const tzPart = tzFmt.formatToParts(date).find((p) => p.type === "timeZoneName");
        if (tzPart && tzPart.value) zone = tzPart.value;
      } catch {
        zone = "";
      }
      if (!zone) {
        const offsetMin = -date.getTimezoneOffset();
        if (offsetMin === 0) {
          zone = "UTC";
        } else {
          const sign = offsetMin >= 0 ? "+" : "-";
          const abs = Math.abs(offsetMin);
          const hh = String(Math.floor(abs / 60)).padStart(2, "0");
          const mm = String(abs % 60).padStart(2, "0");
          zone = mm === "00" ? "UTC" + sign + hh : "UTC" + sign + hh + ":" + mm;
        }
      }
      return (
        parts.day +
        " " +
        parts.month +
        " " +
        parts.year +
        ", " +
        parts.hour +
        ":" +
        parts.minute +
        " " +
        zone
      );
    } catch {
      return "";
    }
  }

  function updateTimeElement(el) {
    if (el.getAttribute("data-utc") === null) {
      el.setAttribute("data-utc", (el.textContent || "").trim());
    }
    const iso = el.getAttribute("datetime") || "";
    const formatted = formatLocalTime(iso);
    if (!formatted) return false;
    if ((el.textContent || "").trim() === formatted && el.getAttribute("title") === formatted) {
      return false;
    }
    el.textContent = formatted;
    el.setAttribute("title", formatted);
    return true;
  }

  function fitDots(strip) {
    const more = strip.querySelector(".pip-more");
    const pips = [...strip.querySelectorAll(".pip")];
    pips.forEach((p) => { p.hidden = false; });
    if (more) {
      more.hidden = true;
      more.textContent = "";
    }
    if (!pips.length || strip.clientWidth === 0) return;
    const fits = () => strip.scrollWidth <= strip.clientWidth + 1;
    if (fits()) return;
    if (!more) return;
    more.hidden = false;
    let hidden = 0;
    for (let i = pips.length - 1; i >= 1; i--) {
      pips[i].hidden = true;
      hidden += 1;
      more.textContent = "+" + hidden;
      if (fits()) return;
    }
  }

  function fitAll() {
    document.querySelectorAll(".dots").forEach(fitDots);
  }

  function updateTimes() {
    let changed = false;
    document.querySelectorAll("time[datetime]").forEach((el) => {
      if (updateTimeElement(el)) changed = true;
    });
    if (changed) fitAll();
  }

  function start() {
    updateTimes();
    fitAll();
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(fitAll);
    }
  }
  window.addEventListener("resize", fitAll);
  window.addEventListener("load", fitAll);
  document.addEventListener("DOMContentLoaded", start);
  if (document.readyState !== "loading") start();
})();

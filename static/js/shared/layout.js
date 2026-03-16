const appShell = document.getElementById("app-shell");
const sidebar = document.getElementById("sidebar");
const sidebarStorageKey = "dmt-sidebar-hidden";

const syncExpandableState = (button, container) => {
  button.setAttribute("aria-expanded", container.classList.contains("is-open") ? "true" : "false");
};

document.querySelectorAll("[data-nav-group]").forEach((button) => {
  const group = button.parentElement;
  syncExpandableState(button, group);

  button.addEventListener("click", () => {
    group.classList.toggle("is-open");
    syncExpandableState(button, group);
  });
});

document.querySelectorAll("[data-collapsible-section]").forEach((section) => {
  const button = section.querySelector("[data-section-toggle]");
  if (!button) {
    return;
  }

  syncExpandableState(button, section);

  button.addEventListener("click", () => {
    section.classList.toggle("is-open");
    syncExpandableState(button, section);
  });
});

const applySidebarState = (isHidden) => {
  if (!appShell || !sidebar) {
    return;
  }

  appShell.classList.toggle("sidebar-hidden", isHidden);
  sidebar.classList.toggle("is-open", !isHidden && window.innerWidth <= 1100);
  document.querySelectorAll("[data-sidebar-toggle]").forEach((button) => {
    button.setAttribute("aria-expanded", isHidden ? "false" : "true");
  });
};

const toggleSidebar = () => {
  if (!appShell) {
    return;
  }

  const isMobile = window.innerWidth <= 1100;
  if (isMobile) {
    sidebar?.classList.toggle("is-open");
    return;
  }

  const nextHiddenState = !appShell.classList.contains("sidebar-hidden");
  localStorage.setItem(sidebarStorageKey, nextHiddenState ? "1" : "0");
  applySidebarState(nextHiddenState);
};

const hideSidebarAfterNavigation = () => {
  if (!appShell) {
    return;
  }

  const isMobile = window.innerWidth <= 1100;
  if (isMobile) {
    sidebar?.classList.remove("is-open");
    return;
  }

  localStorage.setItem(sidebarStorageKey, "1");
  applySidebarState(true);
};

document.querySelectorAll("[data-sidebar-toggle]").forEach((button) => {
  button.addEventListener("click", toggleSidebar);
});

sidebar?.addEventListener(
  "click",
  (event) => {
    const link = event.target.closest("a");
    if (!link || !sidebar.contains(link)) {
      return;
    }
    hideSidebarAfterNavigation();
  },
  true,
);

const savedSidebarState = localStorage.getItem(sidebarStorageKey) === "1";
applySidebarState(savedSidebarState);

window.addEventListener("resize", () => {
  const isMobile = window.innerWidth <= 1100;
  if (isMobile) {
    appShell?.classList.remove("sidebar-hidden");
  } else {
    applySidebarState(localStorage.getItem(sidebarStorageKey) === "1");
    sidebar?.classList.remove("is-open");
  }
});

const updateTabInUrl = (tabName) => {
  if (!tabName) {
    return;
  }
  const url = new URL(window.location.href);
  url.searchParams.set("tab", tabName);
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
};

const buildTabStorageKey = (root) => {
  const customKey = root.dataset.tabKey || "default";
  return `dmt-tab:${window.location.pathname}:${customKey}`;
};

document.querySelectorAll("[data-tab-scope]").forEach((root) => {
  const storageKey = buildTabStorageKey(root);
  const urlTab = new URLSearchParams(window.location.search).get("tab");

  const customButtons = Array.from(root.querySelectorAll("[data-tab-target]"));
  const customPanels = Array.from(root.querySelectorAll("[data-tab-panel]"));

  if (customButtons.length && customPanels.length) {
    const availableTabs = new Set(customButtons.map((button) => button.dataset.tabTarget));
    const persistedTab = sessionStorage.getItem(storageKey);
    const initialTab = availableTabs.has(urlTab) ? urlTab : availableTabs.has(persistedTab) ? persistedTab : customButtons.find((button) => button.classList.contains("is-active"))?.dataset.tabTarget;

    const activateCustomTab = (tabName) => {
      customButtons.forEach((button) => {
        button.classList.toggle("is-active", button.dataset.tabTarget === tabName);
      });
      customPanels.forEach((panel) => {
        panel.classList.toggle("is-active", panel.dataset.tabPanel === tabName);
      });
      sessionStorage.setItem(storageKey, tabName);
      updateTabInUrl(tabName);
    };

    if (initialTab) {
      activateCustomTab(initialTab);
    }

    customButtons.forEach((button) => {
      button.addEventListener("click", () => {
        activateCustomTab(button.dataset.tabTarget);
      });
    });
    return;
  }

  const bootstrapButtons = Array.from(root.querySelectorAll('[data-bs-toggle="tab"][data-bs-target]'));
  if (!bootstrapButtons.length || !window.bootstrap?.Tab) {
    return;
  }

  const bootstrapTabMap = new Map(
    bootstrapButtons.map((button) => {
      const target = button.dataset.bsTarget || "";
      const tabName = target.startsWith("#") ? target.slice(1) : target;
      return [tabName, button];
    }),
  );
  const persistedTab = sessionStorage.getItem(storageKey);
  const initialTabButton = bootstrapTabMap.get(urlTab) || bootstrapTabMap.get(persistedTab);

  if (initialTabButton) {
    window.addEventListener(
      "load",
      () => {
        bootstrap.Tab.getOrCreateInstance(initialTabButton).show();
      },
      { once: true },
    );
  }

  bootstrapButtons.forEach((button) => {
    button.addEventListener("shown.bs.tab", (event) => {
      const target = event.target.dataset.bsTarget || "";
      const tabName = target.startsWith("#") ? target.slice(1) : target;
      if (!tabName) {
        return;
      }
      sessionStorage.setItem(storageKey, tabName);
      updateTabInUrl(tabName);
    });
  });
});

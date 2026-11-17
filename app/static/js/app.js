(() => {
  const sidebar = document.getElementById("sidebar");
  const toggle = document.getElementById("toggleSidebar");
  const wrapper = document.querySelector(".wrapper");
  if (!sidebar || !toggle || !wrapper) return;

  const mobile = window.matchMedia("(max-width: 768px)");
  const closeMobile = () => {
    sidebar.classList.remove("mobile-open");
    wrapper.classList.remove("sidebar-open");
    toggle.setAttribute("aria-expanded", "false");
  };

  toggle.setAttribute("aria-controls", "sidebar");
  toggle.setAttribute("aria-expanded", "false");
  toggle.addEventListener("click", () => {
    if (mobile.matches) {
      const abrir = !sidebar.classList.contains("mobile-open");
      sidebar.classList.toggle("mobile-open", abrir);
      wrapper.classList.toggle("sidebar-open", abrir);
      toggle.setAttribute("aria-expanded", String(abrir));
    } else {
      sidebar.classList.toggle("collapsed");
    }
  });

  wrapper.addEventListener("click", (event) => {
    if (!mobile.matches || !wrapper.classList.contains("sidebar-open")) return;
    const clickedLink = event.target.closest(".sidebar a");
    if (clickedLink) closeMobile();
    if (event.target === wrapper) closeMobile();
  });

  window.addEventListener("resize", () => {
    if (!mobile.matches) closeMobile();
  });
})();

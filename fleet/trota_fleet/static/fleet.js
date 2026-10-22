// Trota Fleet panel: confirmation of risky actions, select-all, the page
// field shown only for the kiosk command. The panel works without it.
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-confirm]");
  if (b && !confirm(b.dataset.confirm)) e.preventDefault();
});
for (const all of document.querySelectorAll("[data-all]")) {
  all.addEventListener("change", () => {
    for (const box of document.querySelectorAll('input[name="device"]')) box.checked = all.checked;
  });
}
for (const sel of document.querySelectorAll("[data-command]")) {
  const url = sel.form.querySelector("[data-url]");
  const sync = () => { url.hidden = sel.value !== "kiosk-url"; };
  sel.addEventListener("change", sync);
  sync();
}

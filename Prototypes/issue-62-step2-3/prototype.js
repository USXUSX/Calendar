document.addEventListener("click", (event) => {
  const plan = event.target.closest(".selectable");
  if (plan && !event.target.closest("a, button, input, textarea")) {
    document.querySelectorAll(".selectable").forEach((item) => item.classList.remove("selected-plan"));
    plan.classList.add("selected-plan");
  }
  if (event.target.closest(".edit-trigger")) {
    plan?.classList.add("editing");
    document.querySelector(".edit-sheet")?.classList.add("open");
    document.querySelector(".sheet-backdrop")?.classList.add("open");
  }
  if (event.target.closest(".cancel-edit")) plan?.classList.remove("editing");
  if (event.target.closest(".close-sheet")) {
    document.querySelector(".edit-sheet")?.classList.remove("open");
    document.querySelector(".sheet-backdrop")?.classList.remove("open");
  }
  const vote = event.target.closest(".vote");
  if (vote) {
    vote.parentElement.querySelectorAll(".vote").forEach((item) => item.classList.remove("selected", "ng"));
    vote.classList.add("selected");
    if (vote.textContent === "NG") vote.classList.add("ng");
  }
});

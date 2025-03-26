document.addEventListener("DOMContentLoaded", () => {
  const gradeSelect = document.getElementById("grade");
  const sectionSelect = document.getElementById("section");

  gradeSelect.addEventListener("change", () => {
      const selectedGrade = gradeSelect.value;

      // Show only sections matching the selected grade
      Array.from(sectionSelect.options).forEach(option => {
          const sectionGrade = option.getAttribute("data-grade");
          option.style.display = (sectionGrade === selectedGrade) ? "block" : "none";
      });

      // Reset section selection
      sectionSelect.value = "";
  });
});

document.addEventListener("DOMContentLoaded", () => {
    const updateDateTime = () => {
      const now = new Date();
      const dateTimeString = now.toLocaleString();
      document.getElementById("current-date-time").textContent = dateTimeString;
    };
  
    // Update every second
    setInterval(updateDateTime, 1000);
    updateDateTime();
  });


document.addEventListener("DOMContentLoaded", () => {
    const dateTimeElement = document.getElementById("date-time");
    const faceRecognitionCheckbox = document.getElementById("face-recognition");
    const timeInRadio = document.getElementById("time-in");
    const timeOutRadio = document.getElementById("time-out");
    const videoElement = document.getElementById("webcam-feed");

    // Update date and time
    const updateDateTime = () => {
        const now = new Date();
        dateTimeElement.textContent = now.toLocaleString();
    };
    setInterval(updateDateTime, 1000);
    updateDateTime();

    if (videoElement && !videoElement.srcObject) { 
        fetch("/webcam_feed/")
            .then((response) => {
                if (!response.ok) {
                    throw new Error("Unable to access the webcam.");
                }
                return response.blob();
            })
            .then((blob) => {
                const objectURL = URL.createObjectURL(blob);
                videoElement.src = objectURL;
            })
            .catch((error) => {
                console.error("Webcam Error:", error);
            });
    }
       
    // Retrieve the checkbox state from localStorage
    const storedState = localStorage.getItem("faceRecognitionEnabled");
    if (storedState !== null) {
        faceRecognitionCheckbox.checked = storedState === "true";
    }
    
    // Enable/disable radio buttons based on checkbox state
    const updateToggleState = () => {
        const isEnabled = faceRecognitionCheckbox.checked;
        timeInRadio.disabled = !isEnabled;
        timeOutRadio.disabled = !isEnabled;
        if (isEnabled) {
            timeInRadio.checked = true; // Set "Time In" as default when face recognition is enabled
        }
        // Persist the state in localStorage
        localStorage.setItem("faceRecognitionEnabled", isEnabled);
    };
    
    // Initialize state on page load
    updateToggleState();
    
    // Update state when checkbox is toggled
    faceRecognitionCheckbox.addEventListener("change", updateToggleState);
    
    // Continuously update the attendance database when a face match is detected
    const updateAttendance = (studentId) => {
        fetch(`/update_attendance/${studentId}/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken")
            },
            body: JSON.stringify({
                time_in: timeInRadio.checked,
                time_out: timeOutRadio.checked
            })
        })
        .then(response => response.json())
        .then(data => {
            console.log("Attendance updated successfully:", data);
        })
        .catch(error => {
            console.error("Error updating attendance:", error);
        });
    };

    // Get CSRF token from cookie
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                // Does this cookie string begin with the name we want?
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
});

// Open modal
function openModal() {
    const modal = document.getElementById("admin-modal");
    if (modal) {
        modal.style.display = "block";
    }
}

// Close modal
function closeModal() {
    const modal = document.getElementById("admin-modal");
    if (modal) {
        modal.style.display = "none";
    }
}

// Close the modal when clicking outside of it
window.onclick = function (event) {
    const modal = document.getElementById("admin-modal");
    if (event.target === modal) {
        closeModal();
    }
};

window.addEventListener("beforeunload", () => {
    fetch("/stop_webcam/", { method: "GET" })
        .catch((error) => console.error("Error stopping webcam:", error));
});

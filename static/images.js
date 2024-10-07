function openFullScreen(imageElement) {
    var modal = document.getElementById("fullscreen-modal");
    var fullscreenImg = document.getElementById("fullscreen-img");

    fullscreenImg.src = imageElement.src; // Set the source of the modal image
    modal.style.display = "flex"; // Show the modal
}

function closeFullScreen() {
    var modal = document.getElementById("fullscreen-modal");
    modal.style.display = "none"; // Hide the modal
}


// Function to open the modal
function openModal(actionUrl) {
    const modal = document.getElementById("confirmation-modal");
    const deleteForm = document.getElementById("delete-form");
    deleteForm.action = actionUrl; // Set the action of the form to the URL for deletion
    modal.style.display = "block"; // Show the modal
}

// Function to close the modal
function closeModal() {
    const modal = document.getElementById("confirmation-modal");
    modal.style.display = "none"; // Hide the modal
}

// Close the modal when clicking anywhere outside of it
window.onclick = function(event) {
    const modal = document.getElementById("confirmation-modal");
    if (event.target == modal) {
        modal.style.display = "none";
    }
}


function fetchDetectedPlates() {
    fetch('/detected_plates')
        .then(response => response.json())
        .then(data => {
            const platesContainer = document.getElementById('platesContainer');
            platesContainer.innerHTML = ''; // Clear current plates

            data.forEach(plate => {
                const plateElement = document.createElement('div');
                plateElement.innerText = plate.plate_number; // Customize as needed
                platesContainer.appendChild(plateElement);
            });
        })
        .catch(err => console.error('Error fetching plates:', err));
}

// Poll every 5 seconds
setInterval(fetchDetectedPlates, 5000);
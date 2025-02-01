function openModal(deleteUrl) {
    // Set the form action to the delete URL
    document.getElementById('delete-form').action = deleteUrl;
    
    // Display the modal
    document.getElementById('confirmation-modal').style.display = 'block';
}

function closeModal() {
    // Hide the modal
    document.getElementById('confirmation-modal').style.display = 'none';
}

// Handle form submission for deletion
document.getElementById('delete-form').addEventListener('submit', function (e) {
    e.preventDefault();  // Prevent default form submission
    
    fetch(this.action, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Reload the page to reflect changes
            window.location.reload();
        } else {
            alert('Error: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred while deleting the plate.');
    });
});

// Close modal when clicking outside of it
window.onclick = function (event) {
    const modal = document.getElementById('confirmation-modal');
    if (event.target === modal) {
        closeModal();
    }
};
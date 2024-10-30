document.addEventListener('DOMContentLoaded', function() {
    const startBtn = document.getElementById('start-btn');
    // Initialize last detection from localStorage if available
    let lastDetectedPlate = localStorage.getItem('lastDetectedPlate');
    let lastDetectionTime = localStorage.getItem('lastDetectionTime');
    let isScanning = true;
    
    // Initialize with stats fetch
    fetchStats();
    fetchDetectedPlates(); // Initial fetch of detected plates
    
    setInterval(fetchStats, 5000);
    setInterval(fetchDetectedPlates, 5000); // Poll for new plates every 5 seconds
    
    // Update initial button state
    startBtn.textContent = 'Stop Camera';
    
    // Image handling functions
    function openFullScreen(imageElement) {
        var modal = document.getElementById("fullscreen-modal");
        var fullscreenImg = document.getElementById("fullscreen-img");
        
        fullscreenImg.src = imageElement.src;
        modal.style.display = "flex";
    }
    
    function closeFullScreen() {
        var modal = document.getElementById("fullscreen-modal");
        modal.style.display = "none";
    }
    
    // Confirmation modal functions
    function openModal(actionUrl) {
        const modal = document.getElementById("confirmation-modal");
        const deleteForm = document.getElementById("delete-form");
        deleteForm.action = actionUrl;
        modal.style.display = "block";
    }
    
    function closeModal() {
        const modal = document.getElementById("confirmation-modal");
        modal.style.display = "none";
    }
    
    // Close modal on outside click
    window.onclick = function(event) {
        const modal = document.getElementById("confirmation-modal");
        const fullscreenModal = document.getElementById("fullscreen-modal");
        if (event.target == modal) {
            modal.style.display = "none";
        }
        if (event.target == fullscreenModal) {
            fullscreenModal.style.display = "none";
        }
    }
    
    // Fetch and display detected plates
    function fetchDetectedPlates() {
        fetch('/api/detected_plates') // Updated endpoint
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                const platesContainer = document.getElementById('platesContainer');
                if (!platesContainer) {
                    console.warn('Plates container not found');
                    return;
                }
                
                platesContainer.innerHTML = ''; // Clear current plates
                
                data.forEach(plate => {
                    const plateDiv = document.createElement('div');
                    plateDiv.className = 'plate-entry';
                    
                    // Create plate info section
                    const plateInfo = document.createElement('div');
                    plateInfo.className = 'plate-info';
                    plateInfo.innerHTML = `
                        <h3>Targa: ${plate.plate_number}</h3>
                        <p>Koha: ${new Date(plate.timestamp).toLocaleString()}</p>
                    `;
                    
                    // Create image if available
                    if (plate.image_path) {
                        const img = document.createElement('img');
                        img.src = plate.image_path;
                        img.alt = `Plate ${plate.plate_number}`;
                        img.className = 'plate-image';
                        img.onclick = () => openFullScreen(img);
                        plateDiv.appendChild(img);
                    }
                    
                    // Create delete button if needed
                    const deleteBtn = document.createElement('button');
                    deleteBtn.className = 'delete-btn';
                    deleteBtn.innerHTML = 'Fshi';
                    deleteBtn.onclick = () => openModal(`/delete_plate/${plate.id}`);
                    
                    plateDiv.appendChild(plateInfo);
                    plateDiv.appendChild(deleteBtn);
                    platesContainer.appendChild(plateDiv);
                });
            })
            .catch(err => {
                console.error('Error fetching plates:', err);
            });
    }
    
    // Immediately show the last detected plate if we have it in localStorage
    if (lastDetectedPlate && lastDetectionTime) {
        const plateInfoDiv = document.getElementById('plate-info');
        const notDetectedText = plateInfoDiv.querySelector('.not-detected');
        const plateNumberText = plateInfoDiv.querySelector('.plate-number');
        const timeStampText = plateInfoDiv.querySelector('.time-stamp');
        
        notDetectedText.style.display = 'none';
        plateNumberText.style.display = 'block';
        timeStampText.style.display = 'block';
        
        plateNumberText.textContent = `Targa e fundit e zbuluar: ${lastDetectedPlate}`;
        timeStampText.textContent = `Koha e zbulimit: ${lastDetectionTime}`;
    }
    
    // Camera control event listener
    startBtn.addEventListener('click', function() {
        if (!isScanning) {
            startCamera();
        } else {
            stopCamera();
        }
    });

    function startCamera() {
        fetch('/start_camera')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    startBtn.textContent = 'Stop Camera';
                    startBtn.disabled = false;
                    isScanning = true;
                }
            });
    }

    function stopCamera() {
        fetch('/stop_camera')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    startBtn.textContent = 'Start Camera';
                    startBtn.disabled = false;
                    isScanning = false;
                }
            });
    }

    // Check initial camera status
    fetch('/get_camera_status')
        .then(response => response.json())
        .then(data => {
            isScanning = data.is_running;
            startBtn.textContent = isScanning ? 'Stop Camera' : 'Start Camera';
        })
        .catch(error => {
            console.error('Error checking camera status:', error);
        });

    function fetchStats() {
        fetch('/get_stats')
            .then(response => response.json())
            .then(data => {
                document.getElementById('total-detections').textContent = data.total_detections;
                document.getElementById('unique-plates').textContent = data.unique_plates;
                
                const topPlatesList = document.getElementById('top-plates');
                topPlatesList.innerHTML = data.top_plates
                    .map(p => `<li>${p.plate_number}: ${p.count} herë</li>`)
                    .join('');
                
                const currentTimezoneOffset = new Date().getTimezoneOffset() / 60;
                const hourDist = document.getElementById('hour-distribution');
                hourDist.innerHTML = data.hour_distribution.map(h => {
                    let localHour = h.hour - currentTimezoneOffset;
                    if (localHour < 0) localHour += 24;
                    if (localHour >= 24) localHour -= 24;
                    return `${localHour}:00 - ${h.count} detektime`;
                }).join('<br>');
            });
    }

    function updatePlateInfo() {
        fetch('/get_last_detected_plate')
            .then(response => response.json())
            .then(data => {
                const plateInfoDiv = document.getElementById('plate-info');
                const notDetectedText = plateInfoDiv.querySelector('.not-detected');
                const plateNumberText = plateInfoDiv.querySelector('.plate-number');
                const timeStampText = plateInfoDiv.querySelector('.time-stamp');
                const scanningText = plateInfoDiv.querySelector('.scanning-status');

                // Update scanning status if it exists
                if (scanningText) {
                    if (isScanning) {
                        scanningText.textContent = 'Kamera është aktive - Duke skanuar targat...';
                        scanningText.style.color = '#28a745';  // Green color for active status
                        scanningText.style.backgroundColor = '#666'; 
                    } else {
                        scanningText.textContent = 'Kamera është ndalur';
                        scanningText.style.color = '#dc3545';  // Red color for stopped status
                    }
                }

                if (data.plate) {
                    // Only update if this is a new plate
                    if (data.plate !== lastDetectedPlate) {
                        lastDetectedPlate = data.plate;
                        lastDetectionTime = data.detection_time;
                        
                        // Store in localStorage
                        localStorage.setItem('lastDetectedPlate', lastDetectedPlate);
                        localStorage.setItem('lastDetectionTime', lastDetectionTime);
                        
                        notDetectedText.style.display = 'none';
                        plateNumberText.style.display = 'block';
                        timeStampText.style.display = 'block';
                        
                        plateNumberText.textContent = `Targa e zbuluar: ${data.plate}`;
                        timeStampText.textContent = `Koha e zbulimit: ${data.detection_time}`;
                        
                        plateNumberText.classList.add('highlight');
                        setTimeout(() => plateNumberText.classList.remove('highlight'), 1000);
                    }
                } else {
                    // No new plate detected - keep showing the last detected plate if we have one
                    if (lastDetectedPlate) {
                        notDetectedText.style.display = 'none';
                        plateNumberText.style.display = 'block';
                        timeStampText.style.display = 'block';
                        
                        plateNumberText.textContent = `Targa e fundit e zbuluar: ${lastDetectedPlate}`;
                        timeStampText.textContent = `Koha e zbulimit: ${lastDetectionTime}`;
                    } else {
                        notDetectedText.style.display = 'block';
                        notDetectedText.textContent = 'Asnjë targë nuk është zbuluar ende';
                        plateNumberText.style.display = 'none';
                        timeStampText.style.display = 'none';
                    }
                }
            })
            .catch(error => {
                console.error('Error:', error);
                const scanningText = document.getElementById('plate-info').querySelector('.scanning-status');
                if (scanningText) {
                    scanningText.textContent = 'Gabim në lidhjen me sistemin e kamerës';
                    scanningText.style.color = '#dc3545';
                }
            });
    }

    // Set up plate info updates
    setInterval(updatePlateInfo, 1000);
    updatePlateInfo(); // Initial update

    // Make functions available globally if needed
    window.openFullScreen = openFullScreen;
    window.closeFullScreen = closeFullScreen;
    window.openModal = openModal;
    window.closeModal = closeModal;
});

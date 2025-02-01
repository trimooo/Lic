document.addEventListener('DOMContentLoaded', function() {
    const startBtn = document.getElementById('start-btn');
    let lastDetectedPlate = localStorage.getItem('lastDetectedPlate');
    let lastDetectionTime = localStorage.getItem('lastDetectionTime');
    let isScanning = true;
    
    // Initialize intervals
    let statsInterval, platesInterval, plateInfoInterval;
    
    // Initial data fetch
    try {
        fetchStats();
        fetchDetectedPlates();
        updatePlateInfo();
        
        statsInterval = setInterval(fetchStats, 5000);
        platesInterval = setInterval(fetchDetectedPlates, 5000);
        plateInfoInterval = setInterval(updatePlateInfo, 1000);
    } catch (error) {
        console.error('Initialization error:', error);
    }

    if (startBtn) {
        startBtn.textContent = 'Stop Camera';
        startBtn.addEventListener('click', function() {
            if (!isScanning) startCamera();
            else stopCamera();
        });
    }

    // Image handling
    function openFullScreen(img) {
        try {
            const modal = document.getElementById("fullscreen-modal");
            const fullscreenImg = document.getElementById("fullscreen-img");
            if (modal && fullscreenImg) {
                fullscreenImg.src = img.src;
                modal.style.display = "flex";
            }
        } catch (error) {
            console.error('Fullscreen error:', error);
        }
    }

    function closeFullScreen() {
        try {
            const modal = document.getElementById("fullscreen-modal");
            if (modal) modal.style.display = "none";
        } catch (error) {
            console.error('Close fullscreen error:', error);
        }
    }

    // Confirmation modal
    function openModal(actionUrl) {
        try {
            const modal = document.getElementById("confirmation-modal");
            const deleteForm = document.getElementById("delete-form");
            if (modal && deleteForm) {
                deleteForm.action = actionUrl;
                modal.style.display = "block";
            }
        } catch (error) {
            console.error('Modal open error:', error);
        }
    }

    function closeModal() {
        try {
            const modal = document.getElementById("confirmation-modal");
            if (modal) modal.style.display = "none";
        } catch (error) {
            console.error('Modal close error:', error);
        }
    }

    // Event delegation for dynamic elements
    document.addEventListener('click', function(event) {
        try {
            if (event.target.matches('.plate-image')) {
                openFullScreen(event.target);
            }
            if (event.target.matches('.delete-btn')) {
                const plateId = event.target.dataset.plateId;
                if (plateId) openModal(`/delete_plate/${plateId}`);
            }
        } catch (error) {
            console.error('Event handling error:', error);
        }
    });

    // Data fetching functions
    async function fetchDetectedPlates() {
        try {
            const response = await fetch('/api/detected_plates');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const data = await response.json();
            const platesContainer = document.getElementById('platesContainer');
            
            if (!platesContainer) {
                console.warn('Plates container not found');
                return;
            }

            platesContainer.innerHTML = '';
            (data || []).forEach(plate => {
                const plateDiv = document.createElement('div');
                plateDiv.className = 'plate-entry';

                const plateInfo = document.createElement('div');
                plateInfo.className = 'plate-info';
                plateInfo.innerHTML = `
                    <h3>Targa: ${plate.plate_number || 'N/A'}</h3>
                    <p>Koha: ${plate.timestamp ? new Date(plate.timestamp).toLocaleString() : 'N/A'}</p>
                `;

                if (plate.image_path) {
                    const img = document.createElement('img');
                    img.src = plate.image_path;
                    img.alt = `Plate ${plate.plate_number || ''}`;
                    img.className = 'plate-image';
                    plateDiv.appendChild(img);
                }

                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'delete-btn';
                deleteBtn.textContent = 'Fshi';
                deleteBtn.dataset.plateId = plate.id || '';
                plateDiv.append(plateInfo, deleteBtn);
                platesContainer.appendChild(plateDiv);
            });
        } catch (error) {
            console.error('Plate fetch error:', error);
        }
    }

    async function fetchStats() {
        try {
            const response = await fetch('/get_stats');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            
            // Add null checks for all data properties
            const safeData = {
                total_detections: data.total_detections || 0,
                unique_plates: data.unique_plates || 0,
                top_plates: data.top_plates || [],
                hour_distribution: data.hour_distribution || []
            };
    
            // Update elements with safe data
            updateElement('total-detections', safeData.total_detections);
            updateElement('unique-plates', safeData.unique_plates);
            
            // Handle top plates
            const topPlatesList = document.getElementById('top-plates');
            if (topPlatesList) {
                topPlatesList.innerHTML = safeData.top_plates
                    .slice(0, 5) // Ensure only top 5
                    .map(p => `<li>${p.plate_number || 'Unknown'}: ${p.count || 0}</li>`)
                    .join('');
            }
    
            // Handle hour distribution
            const hourDist = document.getElementById('hour-distribution');
            if (hourDist) {
                hourDist.innerHTML = safeData.hour_distribution
                    .map(h => `${h.hour}:00 - ${h.count}`)
                    .join('<br>');
            }
        } catch (error) {
            console.error('Stats fetch error:', error);
            // Update UI to show error state
            updateElement('total-detections', 'Error');
            updateElement('unique-plates', 'Error');
        }
    }
    
    function updateElement(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }
    
    // Modify fetchDetectedPlates to check for container existence
    async function fetchDetectedPlates() {
        try {
            const platesContainer = document.getElementById('platesContainer');
            if (!platesContainer) {
                console.warn('Plates container not found - might be on wrong page');
                return;
            }
            
            // Rest of your plate fetching logic
        } catch (error) {
            console.error('Plate fetch error:', error);
        }
    }

        // Update camera status
        fetch('/get_camera_status')
            .then(response => {
                if (!response.ok) throw new Error('Camera status check failed');
                return response.json();
            })
            .then(data => {
                if (startBtn) {
                    isScanning = data.is_running;
                    startBtn.textContent = isScanning ? 'Stop Camera' : 'Start Camera';
                }
            })
            .catch(error => console.error('Camera status error:', error));
    }

    // Camera controls
    async function startCamera() {
        try {
            const response = await fetch('/start_camera');
            if (!response.ok) throw new Error('Start failed');
            const data = await response.json();
            isScanning = data.status === 'success';
            startBtn.textContent = 'Stop Camera';
        } catch (error) {
            console.error('Camera start error:', error);
            alert('Failed to start camera');
        }
    }

    async function stopCamera() {
        try {
            const response = await fetch('/stop_camera');
            if (!response.ok) throw new Error('Stop failed');
            const data = await response.json();
            isScanning = data.status !== 'success';
            startBtn.textContent = 'Start Camera';
        } catch (error) {
            console.error('Camera stop error:', error);
            alert('Failed to stop camera');
        }
    }

    // Update plate information display
    function updatePlateInfo() {
        fetch('/get_last_detected_plate')
            .then(response => {
                if (!response.ok) throw new Error('Plate info fetch failed');
                return response.json();
            })
            .then(data => {
                const plateInfoDiv = document.getElementById('plate-info');
                if (!plateInfoDiv) return;

                const elements = {
                    notDetected: plateInfoDiv.querySelector('.not-detected'),
                    plateNumber: plateInfoDiv.querySelector('.plate-number'),
                    timeStamp: plateInfoDiv.querySelector('.time-stamp'),
                    scanning: plateInfoDiv.querySelector('.scanning-status')
                };

                if (elements.scanning) {
                    elements.scanning.textContent = isScanning 
                        ? 'Kamera është aktive - Duke skanuar targat...'
                        : 'Kamera është ndalur';
                    elements.scanning.style.color = isScanning ? '#28a745' : '#dc3545';
                }

                // Update plate data only if changed
                if (data.plate && data.plate !== lastDetectedPlate) {
                    lastDetectedPlate = data.plate;
                    lastDetectionTime = data.detection_time;
                    
                    try {
                        localStorage.setItem('lastDetectedPlate', lastDetectedPlate);
                        localStorage.setItem('lastDetectionTime', lastDetectionTime);
                    } catch (e) {
                        console.error('LocalStorage error:', e);
                    }

                    if (elements.plateNumber && elements.timeStamp) {
                        elements.plateNumber.textContent = `Targa e zbuluar: ${lastDetectedPlate}`;
                        elements.timeStamp.textContent = `Koha e zbulimit: ${lastDetectionTime}`;
                        elements.plateNumber.classList.add('highlight');
                        setTimeout(() => elements.plateNumber.classList.remove('highlight'), 1000);
                    }
                }

                // Toggle visibility
                ['notDetected', 'plateNumber', 'timeStamp'].forEach(key => {
                    if (elements[key]) {
                        elements[key].style.display = lastDetectedPlate && key !== 'notDetected' 
                            ? 'block' 
                            : 'none';
                    }
                });
            })
            .catch(error => console.error('Plate info error:', error));
    }

    // Cleanup
    window.addEventListener('beforeunload', () => {
        clearInterval(statsInterval);
        clearInterval(platesInterval);
        clearInterval(plateInfoInterval);
    });

    // Global exposure
    window.openFullScreen = openFullScreen;
    window.closeFullScreen = closeFullScreen;
    window.openModal = openModal;
    window.closeModal = closeModal;
});
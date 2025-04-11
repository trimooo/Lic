const debounce = (func, wait) => {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
};

document.addEventListener('DOMContentLoaded', function() {
    // Cache DOM elements
    const elements = {
        startBtn: document.getElementById('start-btn'),
        plateInfo: document.getElementById('plate-info'),
        platesContainer: document.getElementById('platesContainer')
    };
    const startBtn = document.getElementById('start-btn');
    const plateInfoDiv = document.getElementById('plate-info');
    const platesContainer = document.getElementById('platesContainer');
    let isScanning = true;

    // Use more efficient intervals
    const STATS_INTERVAL = 10000;  // 10 seconds
    const PLATES_INTERVAL = 5000;  // 5 seconds
    const PLATE_INFO_INTERVAL = 2000;  // 2 seconds

    // Lazy load data
    setTimeout(() => {
        fetchStats();
        fetchDetectedPlates();
        updatePlateInfo();
    }, 100);

    // More efficient interval management
    let activeIntervals = {
        stats: setInterval(fetchStats, STATS_INTERVAL),
        plates: setInterval(fetchDetectedPlates, PLATES_INTERVAL),
        plateInfo: setInterval(updatePlateInfo, PLATE_INFO_INTERVAL)
    };

    // Image handling optimization
    function openFullScreen(img) {
        const modal = document.getElementById("fullscreen-modal");
        const fullscreenImg = document.getElementById("fullscreen-img");
        if (modal && fullscreenImg) {
            fullscreenImg.src = img.src;
            modal.style.display = "flex";
        }
    }

    function closeFullScreen() {
        const modal = document.getElementById("fullscreen-modal");
        if (modal) modal.style.display = "none";
    }

    // Optimized plate fetching
    async function fetchDetectedPlates() {
        if (!platesContainer) return;

        try {
            const response = await fetch('/api/detected_plates');
            if (!response.ok) return;

            const data = await response.json();
            platesContainer.innerHTML = '';

            data.forEach(plate => {
                const plateDiv = document.createElement('div');
                plateDiv.className = 'plate-entry';
                plateDiv.innerHTML = `
                    <div class="plate-info">
                        <h3>Plate: ${plate.plate_number || 'N/A'}</h3>
                        <p>Time: ${plate.timestamp ? new Date(plate.timestamp).toLocaleString() : 'N/A'}</p>
                    </div>
                    ${plate.image_path ? `<img src="${plate.image_path}" alt="Plate ${plate.plate_number || ''}" class="plate-image" loading="lazy">` : ''}
                    <button class="delete-btn" data-plate-id="${plate.id || ''}">Delete</button>
                `;
                platesContainer.appendChild(plateDiv);
            });
        } catch (error) {
            console.error('Plate fetch error:', error);
        }
    }

    // Event delegation
    document.addEventListener('click', function(event) {
        if (event.target.matches('.plate-image')) {
            openFullScreen(event.target);
        }
        if (event.target.matches('.delete-btn')) {
            const plateId = event.target.dataset.plateId;
            if (plateId) openModal(`/delete_plate/${plateId}`);
        }
    });

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        Object.values(activeIntervals).forEach(interval => clearInterval(interval));
    });

    // Expose necessary functions
    window.openFullScreen = openFullScreen;
    window.closeFullScreen = closeFullScreen;


    //The rest of the original code that was not modified in the edited snippet
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

    if (startBtn) {
        startBtn.textContent = 'Stop Camera';
        startBtn.addEventListener('click', function() {
            if (!isScanning) startCamera();
            else stopCamera();
        });
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

    //Global exposure of functions that are not modified
    window.openModal = openModal;
    window.closeModal = closeModal;
});
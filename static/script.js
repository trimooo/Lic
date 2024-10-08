document.addEventListener('DOMContentLoaded', function() {
  const startBtn = document.getElementById('start-btn');
  
  // Fetch initial stats
  fetchStats();

  // Set up periodic stats update
  setInterval(fetchStats, 5000); // Update every minute

  startBtn.addEventListener('click', function() {
      if (startBtn.textContent === 'Camera Start Automatically') {
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
              }
          });
  }

  function fetchStats() {
    fetch('/get_stats')
        .then(response => response.json())
        .then(data => {
            document.getElementById('total-detections').textContent = data.total_detections;
            document.getElementById('unique-plates').textContent = data.unique_plates;
            
            const topPlatesList = document.getElementById('top-plates');
            topPlatesList.innerHTML = data.top_plates.map(p => 
                `<li>${p.plate_number}: ${p.count} herë</li>`
            ).join('');
            
            const hourDist = document.getElementById('hour-distribution');

// Marrim zonën kohore të klientit (shfletuesit) dhe konvertojmë orët në kohën lokale
const currentTimezoneOffset = new Date().getTimezoneOffset() / 60; // Zona kohore në orë

// Krijo HTML-n për orët me detektimet
hourDist.innerHTML = data.hour_distribution.map(h => {
    // Konverto orën sipas zonës kohore
    let localHour = h.hour - currentTimezoneOffset;
    
    // Sigurohemi që ora lokale është brenda intervalit 0-23
    if (localHour < 0) localHour += 24;
    if (localHour >= 24) localHour -= 24;

    return `${localHour}:00 - ${h.count} detektime`;
}).join('<br>');

            

        });

        function fetchPlateStatus() {
            const plateInfo = document.getElementById('plate-info');
            const notDetected = plateInfo.querySelector('.not-detected');
            const plateNumber = plateInfo.querySelector('.plate-number');
            const timeStamp = plateInfo.querySelector('.time-stamp');
    
            if (isScanning) {
                notDetected.textContent = 'Scanning for plates...';
                notDetected.style.display = 'block';
                plateNumber.style.display = 'none';
                timeStamp.style.display = 'none';
            }
    
            fetch('/get_last_detected_plate')
                .then(response => response.json())
                .then(data => {
                    isScanning = false; // Scanning is complete
    
                    if (data && data.plate) {
                        notDetected.style.display = 'none';
                        plateNumber.style.display = 'block';
                        timeStamp.style.display = 'block';
    
                        // Update plate number and timestamp
                        plateNumber.textContent = data.plate;
                        timeStamp.textContent = `Last detected at: ${new Date().toLocaleTimeString()}`;
                    } else {
                        notDetected.textContent = 'Plate not detected';
                        notDetected.style.display = 'block';
                        plateNumber.style.display = 'none';
                        timeStamp.style.display = 'none';
                    }
                })
                .catch(error => {
                    console.error("Error fetching plate status:", error);
                    notDetected.textContent = 'Plate not detected';
                    notDetected.style.display = 'block';
                    plateNumber.style.display = 'none';
                    timeStamp.style.display = 'none';
                });
        }
    
        // Fetch plate status every 5 seconds to check for updates
        setInterval(() => {
            isScanning = true; // Reset scanning state before fetching
            fetchPlateStatus();
        }, 5000); // Change interval to your desired time (5000 ms = 5 seconds)
}})